"""tool-decision-eval: does a quantised or exported model still decide to call its tools?

    tool-decision-eval --reference LiquidAI/LFM2.5-1.2B-Instruct --file model-Q4_K_M.gguf --limit 40
"""
import argparse, hashlib, json, os, sys, time

from pathlib import Path

from . import grade, suites
from .parse import CALL_OPENERS, parse_calls, started

STOP_STRINGS = ("<|im_end|>", "<|endoftext|>", "<|eot_id|>", "<|end|>")


def render(tok, template, q, kwargs):
    return tok.apply_chat_template(q["messages"], tools=q["tools"], add_generation_prompt=True, tokenize=False,
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
    ap.add_argument("--suite", action="append", help=f"shipped suite ({', '.join(suites.SHIPPED)}), 'all', or a "
                    "suite folder (repeatable; default: search)")
    ap.add_argument("--cases", help="your own cases .jsonl, with --tools (and optionally --prompt)")
    ap.add_argument("--tools", help="OpenAI function schema list for --cases")
    ap.add_argument("--prompt", help='{"system": str, "preamble": [messages]} for --cases')
    ap.add_argument("--template", help="Jinja chat template file (default: the reference's)")
    ap.add_argument("--template-kwargs", default="{}", help='e.g. \'{"enable_thinking": false}\'')
    ap.add_argument("--call-token", help="token that opens a call (default: the one in the chat template, of %s)" % (CALL_OPENERS,))
    ap.add_argument("--limit", type=int, help="evenly spaced subset of this many rows per suite")
    ap.add_argument("--max-tokens", type=int, default=384)
    ap.add_argument("--n-ctx", type=int, default=8192)
    ap.add_argument("--device", default="auto", help="reference device: auto, cpu, mps, cuda")
    ap.add_argument("--dtype", default="float32", help="reference dtype")
    ap.add_argument("--no-reference-run", action="store_true", help="use the reference for template only")
    ap.add_argument("--phone", action="append", default=[], metavar="FILE.jsonl",
                    help="rows the phone runner wrote (eval-results/tde/<model>.jsonl), graded as engine <model>@phone")
    ap.add_argument("--phone-export", metavar="DIR", help="write DIR/cases.jsonl for the phone runner and stop")
    ap.add_argument("--out", default="tde-out")
    a = ap.parse_args(argv)

    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(a.reference)
    template = Path(a.template).read_text() if a.template else None
    names = [n for s in (a.suite or ([] if a.cases else ["search"])) for n in (suites.SHIPPED if s == "all" else [s])]
    by_suite = {}
    for n in names:
        rows = suites.load(n, a.limit)
        by_suite[rows[0]["suite"]] = rows
    if a.cases:
        rows = suites.load(a.cases, a.limit, a.tools, a.prompt)
        by_suite[rows[0]["suite"]] = rows
    questions = [q for rows in by_suite.values() for q in rows]
    kwargs = json.loads(a.template_kwargs)
    if a.phone_export:
        return phone_export(Path(a.phone_export), questions, a.max_tokens, kwargs.get("enable_thinking", True))
    # The opener the template writes calls with. Vocab presence is not enough: LFM3 keeps LFM2's
    # <|tool_call_start|> token in its vocabulary but writes <tool_call>.
    source = template or tok.chat_template or ""
    a.call_token = a.call_token or next((o for o in CALL_OPENERS if o in source), None)
    prompts = {q["id"]: render(tok, template, q, kwargs) for q in questions}

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
    if not todo and not a.phone:
        sys.exit("nothing to run: give --file or --phone, or drop --no-reference-run")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    keys = {i: row_key(p, a.max_tokens, a.call_token, a.dtype) for i, p in prompts.items()}
    results = {}
    for name, make in todo:
        results[name] = _cached_run(out / f"{name}.jsonl", keys, make, questions, prompts, a, (*STOP_STRINGS, tok.eos_token))
    for f in a.phone:
        results[Path(f).stem + "@phone"] = phone_rows(Path(f), questions)

    report = {
        "suites": {s: {"rows": len(rows), "label_counts": {lab: sum(q["label"] == lab for q in rows) for lab in grade.LABELS}}
                   for s, rows in by_suite.items()},
        "settings": {"reference": a.reference, "files": [Path(f).name for f in a.file], "max_tokens": a.max_tokens,
                     "template_kwargs": kwargs, "template": a.template or "reference", "call_token": a.call_token,
                     "limit": a.limit, "decoding": "greedy"},
        "summary": {s: {n: grade.summarize(rows, r) for n, r in results.items()} for s, rows in by_suite.items()},
        "diff": {s: {n: grade.diff(rows, results["reference"], r) for n, r in results.items() if n != "reference"}
                 for s, rows in by_suite.items()} if "reference" in results else {},
        "per_tool": {n: grade.per_tool(questions, r) for n, r in results.items()},
        "rows_by_engine": {n: [{**r[q["id"]], **grade.grade_row(q, r[q["id"]])} for q in questions] for n, r in results.items()},
    }
    md = grade.markdown(report)
    (out / "report.json").write_text(json.dumps(report, indent=1, ensure_ascii=False))
    (out / "report.md").write_text(md)
    print(md)
    print(f"Wrote {out / 'report.md'} and {out / 'report.json'}", file=sys.stderr)


def phone_export(out, questions, max_tokens, thinking):
    """The cases as the phone runner reads them: messages and tools, rendered there by the app's template."""
    out.mkdir(parents=True, exist_ok=True)
    with (out / "cases.jsonl").open("w") as f:
        for q in questions:
            f.write(json.dumps({"id": q["id"], "messages": q["messages"], "tools": q["tools"], "max_tokens": max_tokens,
                                "thinking": thinking}, ensure_ascii=False) + "\n")
    print(f"Wrote {len(questions)} cases to {out / 'cases.jsonl'}", file=sys.stderr)


def phone_rows(path, questions):
    """The phone runner's lines as engine rows. Calls are parsed from the raw stream with the laptop's
    parsers; the app's own parsed calls stand in only when the stream carries no call markup."""
    have = {}
    for line in path.read_text().splitlines():
        if line.strip():
            r = json.loads(line)
            have[r["id"]] = r
    missing = [q["id"] for q in questions if q["id"] not in have]
    if missing:
        sys.exit(f"{path}: {len(missing)} cases have no phone row (first: {missing[0]}); run the phone again, it resumes")
    rows = {}
    for q in questions:
        r = have[q["id"]]
        text = r.get("raw") or r.get("content", "")
        reply = text.rsplit("</think>", 1)[-1].strip()
        calls = parse_calls(reply)
        if not calls and not started(reply):
            calls = [{"name": c["name"], "arguments": _json_or(c["arguments"])} for c in r.get("app_calls", [])]
        rows[q["id"]] = {"id": q["id"], "calls": calls, "started": started(reply) or bool(calls), "reply": reply,
                         "raw": text, "p_call": None, "truncated": r.get("stop") == "MAX_TOKENS",
                         "prompt_tokens": r.get("prompt_tokens", 0), "new_tokens": r.get("new_tokens", 0),
                         "seconds": r.get("seconds", 0), "error": r.get("error")}
    return rows


def _json_or(s):
    try:
        v = json.loads(s)
        return v if isinstance(v, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


def row_key(prompt, max_tokens, call_token, dtype):
    return hashlib.sha1(json.dumps([prompt, max_tokens, call_token, dtype]).encode()).hexdigest()


def _cached_run(path, keys, make, questions, prompts, a, stop_strings):
    """Rows already on disk for the same prompt and settings are reused; the rest are run and appended."""
    have = {}
    if path.exists():
        for line in path.read_text().splitlines():
            r = json.loads(line) if line.strip() else {}
            if r.get("id") in keys and r.get("key") == keys[r["id"]]:
                have[r["id"]] = r
    missing = [q for q in questions if q["id"] not in have]
    if missing:
        print(f"{path.stem}: running {len(missing)} rows ({len(questions) - len(missing)} cached)", file=sys.stderr, flush=True)
        engine = make()
        with path.open("a") as f:
            for q, r in zip(missing, run_engine(engine, missing, prompts, a.max_tokens, a.call_token, stop_strings)):
                r["key"] = keys[q["id"]]
                have[r["id"]] = r
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                f.flush()
                print(f"  {q['id'][:40]:<40} {','.join(c['name'] for c in r['calls']) or '-':<14} p={_p(r['p_call'])} "
                      f"{q['question'][:60]!r}", file=sys.stderr, flush=True)
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
