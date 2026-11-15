"""tool-decision-eval: does a quantised or exported model still decide to call its tools?

    tool-decision-eval --reference LiquidAI/LFM2.5-1.2B-Instruct --file model-Q4_K_M.gguf --limit 40
"""
import argparse, hashlib, json, os, sys, time

from pathlib import Path

from . import grade
from .parse import CALL_OPENERS, parse_calls, started

DATA = Path(__file__).parent / "data"
STOP_STRINGS = ("<|im_end|>", "<|endoftext|>", "<|eot_id|>", "<|end|>")


def load_questions(path, limit):
    rows = [json.loads(l) for l in Path(path).read_text().splitlines() if l.strip()]
    for r in rows:
        if r.get("label") not in grade.LABELS:
            sys.exit(f"{path}: row {r.get('id')} has label {r.get('label')!r}, expected one of {grade.LABELS}")
        r.setdefault("answers", [])
    if limit and limit < len(rows):  # evenly spaced, so every stratum of an ordered set is in
        rows = [rows[i * len(rows) // limit] for i in range(limit)]
    return rows


def render(tok, template, prompt, tools, question, kwargs):
    messages = [{"role": "system", "content": prompt["system"]}] if prompt.get("system") else []
    messages += prompt.get("preamble", []) + [{"role": "user", "content": question}]
    return tok.apply_chat_template(messages, tools=tools, add_generation_prompt=True, tokenize=False,
                                   chat_template=template, **kwargs)


def decision_p(pieces, p, in_think):
    """p(call) at the first reply token that is not inside a think block and not whitespace."""
    for piece, prob in zip(pieces, p):
        if "<think>" in piece:
            in_think = True
        elif "</think>" in piece:
            in_think = False
        elif not in_think and piece.strip():
            return prob
    return None


def run_engine(engine, questions, prompts, max_new, call_token, stop_strings):
    call_id = engine.token_id(call_token) if call_token else next(
        (i for o in CALL_OPENERS if (i := engine.token_id(o)) is not None), None)
    stop_ids = {i for s in stop_strings if s and (i := engine.token_id(s)) is not None}
    for q in questions:
        prompt = prompts[q["id"]]
        ids = engine.tokenize(prompt)
        t0 = time.time()
        out, p = engine.generate(ids, max_new, stop_ids, call_id)
        seconds = time.time() - t0
        tail = prompt[prompt.rfind(q["question"]):]
        pieces = [engine.decode([i]) for i in out]
        text = engine.decode([i for i in out if i not in stop_ids])
        reply = text.rsplit("</think>", 1)[-1].strip()
        calls = parse_calls(reply)
        yield {
            "id": q["id"], "calls": calls, "started": started(reply), "reply": reply, "raw": text,
            "p_call": decision_p(pieces, p, tail.rfind("<think>") > tail.rfind("</think>")),
            "truncated": bool(out) and out[-1] not in stop_ids, "prompt_tokens": len(ids),
            "new_tokens": len(out), "seconds": round(seconds, 2),
        }


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tool-decision-eval", description=__doc__.split("\n")[0])
    ap.add_argument("--reference", required=True, help="HF repo or local dir of the unquantised source model; "
                    "its chat template and tokenizer render every prompt")
    ap.add_argument("--file", action="append", default=[], help=".gguf or .pte to compare (repeatable)")
    ap.add_argument("--pte-tokenizer", help="tokenizer.json for .pte files (default: the reference's)")
    ap.add_argument("--questions", default=str(DATA / "decisions.jsonl"))
    ap.add_argument("--tools", default=str(DATA / "tools.json"), help="OpenAI function schema list")
    ap.add_argument("--prompt", default=str(DATA / "prompt.json"), help='{"system": str, "preamble": [messages]}')
    ap.add_argument("--template", help="Jinja chat template file (default: the reference's)")
    ap.add_argument("--template-kwargs", default="{}", help='e.g. \'{"enable_thinking": false}\'')
    ap.add_argument("--call-token", help="token that opens a call (default: the first of %s in the vocab)" % (CALL_OPENERS,))
    ap.add_argument("--limit", type=int, help="evenly spaced subset of this many rows")
    ap.add_argument("--max-tokens", type=int, default=384)
    ap.add_argument("--n-ctx", type=int, default=4096)
    ap.add_argument("--device", default="auto", help="reference device: auto, cpu, mps, cuda")
    ap.add_argument("--dtype", default="float32", help="reference dtype")
    ap.add_argument("--no-reference-run", action="store_true", help="use the reference for template only")
    ap.add_argument("--out", default="tde-out")
    a = ap.parse_args(argv)

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(a.reference)
    template = Path(a.template).read_text() if a.template else None
    questions = load_questions(a.questions, a.limit)
    tools = json.loads(Path(a.tools).read_text())
    prompt = json.loads(Path(a.prompt).read_text())
    kwargs = json.loads(a.template_kwargs)
    # The opener the template writes calls with. Vocab presence is not enough: LFM3 keeps LFM2's
    # <|tool_call_start|> token in its vocabulary but writes <tool_call>.
    source = template or tok.chat_template or ""
    a.call_token = a.call_token or next((o for o in CALL_OPENERS if o in source), None)
    prompts = {q["id"]: render(tok, template, prompt, tools, q["question"], kwargs) for q in questions}

    from . import engines
    todo = [] if a.no_reference_run else [("reference", lambda: engines.HF(a.reference, tok, a.device, a.dtype))]
    for f in a.file:
        if f.endswith(".gguf"):
            todo.append((Path(f).name, lambda f=f: engines.GGUF(f, a.n_ctx)))
        elif f.endswith(".pte"):
            tj = a.pte_tokenizer or _tokenizer_json(a.reference)
            todo.append((Path(f).name, lambda f=f, tj=tj: engines.PTE(f, tj)))
        else:
            sys.exit(f"{f}: expected .gguf or .pte")
    if not todo:
        sys.exit("nothing to run: give --file, or drop --no-reference-run")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(json.dumps([prompts, a.max_tokens, a.call_token, a.dtype]).encode()).hexdigest()
    results = {}
    for name, make in todo:
        results[name] = _cached_run(out / f"{name}.jsonl", key, make, questions, prompts, a, (*STOP_STRINGS, tok.eos_token))

    first = next(iter(results))
    report = {
        "questions": a.questions, "rows": len(questions),
        "label_counts": {lab: sum(q["label"] == lab for q in questions) for lab in grade.LABELS},
        "settings": {"reference": a.reference, "files": a.file, "max_tokens": a.max_tokens, "template_kwargs": kwargs,
                     "template": a.template or "reference", "call_token": a.call_token, "decoding": "greedy"},
        "summary": {n: grade.summarize(questions, r) for n, r in results.items()},
        "diff": {n: grade.diff(questions, results["reference"], r) for n, r in results.items() if n != "reference"}
        if "reference" in results else {},
        "rows_by_engine": {n: [{**r[q["id"]], **grade.grade_row(q, r[q["id"]])} for q in questions] for n, r in results.items()},
    }
    md = grade.markdown(report)
    (out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    (out / "report.md").write_text(md)
    print(md)
    print(f"Wrote {out / 'report.md'} and {out / 'report.json'}", file=sys.stderr)


def _cached_run(path, key, make, questions, prompts, a, stop_strings):
    """Rows already on disk under the same prompts and settings are reused; the rest are run."""
    have = {}
    if path.exists():
        lines = [json.loads(l) for l in path.read_text().splitlines() if l.strip()]
        if lines and lines[0].get("key") == key:
            have = {r["id"]: r for r in lines[1:]}
    missing = [q for q in questions if q["id"] not in have]
    if missing:
        print(f"{path.stem}: running {len(missing)} rows ({len(have)} cached)", file=sys.stderr, flush=True)
        engine = make()
        with path.open("w") as f:
            f.write(json.dumps({"key": key}) + "\n")
            for r in have.values():
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
            for q, r in zip(missing, run_engine(engine, missing, prompts, a.max_tokens, a.call_token, stop_strings)):
                have[r["id"]] = r
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                f.flush()
                print(f"  {q['label']:<10} {'call' if r['calls'] else '    '} p={_p(r['p_call'])} {q['question'][:70]}",
                      file=sys.stderr, flush=True)
    return have


def _p(v):
    return "  n/a" if v is None else f"{v:.3f}"


def _tokenizer_json(ref):
    if os.path.isdir(ref):
        return str(Path(ref) / "tokenizer.json")
    from huggingface_hub import hf_hub_download
    return hf_hub_download(ref, "tokenizer.json")


if __name__ == "__main__":
    main()
