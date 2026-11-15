"""Grading rules and the report.

Answer matching is ported from OpenWeights' `tools/eval/bench/grade_decisions.py`: SQuAD
normalisation, aliases matched as whole words (plain substring containment credited "ca" in
"located" and "us" in "focus", 276 wrong replies counted right over 9,060 rows), a token-F1
of 0.5 for short replies, and a fifteen character floor so a bare word is not credited unless
it is the alias.
"""
import collections, functools, re, statistics, string, unicodedata

ARTICLES = re.compile(r"\b(a|an|the)\b")
CANNOT = re.compile(
    r"\b(i (do not|don't|cannot|can't) (know|have|find|access|provide)|no (information|data) (on|about)|"
    r"not (sure|aware|able to)|unable to)\b", re.I)
UNSPACED_SCRIPTS = ("CJK UNIFIED", "CJK COMPATIBILITY IDEOGRAPH", "HIRAGANA", "KATAKANA", "THAI", "LAO",
                    "KHMER", "MYANMAR", "TIBETAN")
LABELS = ("needs_tool", "no_tool", "no_target")


def plain(text):
    return text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')


def normalize(text):
    text = plain(text).lower()
    text = "".join(c for c in text if c not in string.punctuation)
    return " ".join(ARTICLES.sub(" ", text).split())


def token_f1(pred, gold):
    p, g = normalize(pred).split(), normalize(gold).split()
    hits = sum((collections.Counter(p) & collections.Counter(g)).values()) if p and g else 0
    if not hits:
        return 0.0
    precision, recall = hits / len(p), hits / len(g)
    return 2 * precision * recall / (precision + recall)


def contains(text, alias):
    """Normalised `alias` in normalised `text` as whole words; plain containment for unspaced scripts."""
    if not alias:
        return False
    if any(unicodedata.name(c, "").startswith(UNSPACED_SCRIPTS) for c in alias if c.isalpha()):
        return alias in text
    return re.search(r"(?<![^\W_])" + re.escape(alias) + r"(?![^\W_])", text) is not None


def correct(answer, aliases):
    if len(answer.strip()) < 15 and not any(normalize(answer) == normalize(a) for a in aliases):
        return False
    text = normalize(answer)
    if any(contains(text, normalize(a)) for a in aliases):
        return True
    return len(text.split()) <= 12 and any(token_f1(answer, a) >= 0.5 for a in aliases)


DEFAULT_CLAIM = (r"\b(i (have |'ve )?(searched|looked (it )?up|ran|run|executed|called|saved|deleted|read|opened)\b|"
                 r"according to (the )?(search|sources?|results?|tool|output)|based on (my|the) (search|tool|results?))")


def expected(q):
    """The tool names a case accepts: a set, None for any offered tool, or empty for none."""
    e = q["expect"]
    if e in ("none", "either"):
        return set()
    return None if e == "any" else {e} if isinstance(e, str) else set(e)


def label(expect):
    return "no_tool" if expect == "none" else "no_target" if expect == "either" else "needs_tool"


@functools.lru_cache(maxsize=None)
def _claim(pattern):
    return re.compile(pattern, re.I)


def _strict(schema):
    """Tool schemas rarely say additionalProperties; an argument name the tool does not have is still wrong."""
    if not isinstance(schema, dict):
        return schema
    out = {k: ({n: _strict(v) for n, v in s.items()} if k == "properties" else _strict(s) if k == "items" else s)
           for k, s in schema.items()}
    if "properties" in out:
        out.setdefault("additionalProperties", False)
    return out


def args_ok(args, schema):
    import jsonschema
    props = (schema or {}).get("properties", {})
    # XML-parameter calls carry every value as text; "2024" for a string field is not an error.
    args = {k: str(v) if props.get(k, {}).get("type") == "string" and isinstance(v, (int, float, bool)) else v
            for k, v in args.items()}
    try:
        jsonschema.validate(args, _strict(schema or {"type": "object"}))
        return True
    except jsonschema.ValidationError:
        return False


def args_match(args, want):
    """Every argument the case names is present, and contains the case's value when one is given."""
    return all(k in args and (v is None or normalize(str(v)) in normalize(str(args[k]))) for k, v in want.items())


def grade_row(q, r):
    """One case and one engine's reply -> the flags the report counts."""
    calls = r["calls"]
    called = bool(calls)
    reply = plain(r["reply"])
    offered = {t["function"]["name"]: t["function"].get("parameters") for t in q["tools"]}
    want = expected(q)
    right = [c for c in calls if c["name"] in offered and (want is None or c["name"] in want)]
    return {
        "label": q["label"],
        "called": called,
        "tools_called": sorted({c["name"] for c in calls}),
        "wrong_tool": q["label"] == "needs_tool" and called and not right,
        "unknown_tool": any(c["name"] not in offered for c in calls),
        "bad_arguments": any(c["name"] in offered and not args_ok(c["arguments"], offered[c["name"]]) for c in calls)
        or bool(right and q.get("args") and not any(args_match(c["arguments"], q["args"]) for c in right)),
        "malformed": r["started"] and not called,
        "truncated": r.get("truncated", False),
        "claimed": not called and bool(_claim(q.get("claim") or DEFAULT_CLAIM).search(reply)),
        # Only replies that answered without a call can be graded: no tool is run here.
        "correct": correct(reply, q["answers"]) if q.get("answers") and not called and not q.get("stale_risk") else None,
        "abstained": not called and bool(CANNOT.search(reply)),
        "p_call": r["p_call"],
    }


def frac(n, d):
    return f"{n}/{d}" if d else "n/a"


def summarize(questions, rows):
    g = [grade_row(q, rows[q["id"]]) for q in questions]
    by = {lab: [x for x in g if x["label"] == lab] for lab in LABELS}
    with_call = [x for x in g if x["called"]]
    graded = [x for x in g if x["correct"] is not None]
    p = lambda xs: round(statistics.mean(v), 3) if (v := [x["p_call"] for x in xs if x["p_call"] is not None]) else None
    count = lambda key, xs: frac(sum(x[key] for x in xs), len(xs))
    return {
        "rows": len(g),
        "called_when_needed": count("called", by["needs_tool"]),
        "called_when_not_needed": count("called", by["no_tool"]),
        "called_either_fine": count("called", by["no_target"]),
        "wrong_tool": count("wrong_tool", [x for x in by["needs_tool"] if x["called"]]),
        "bad_arguments": count("bad_arguments", with_call),
        "unknown_tool": count("unknown_tool", with_call),
        "claimed_use_without_calling": count("claimed", g),
        "malformed_calls": count("malformed", g),
        "hit_token_limit": count("truncated", g),
        "correct_without_call": count("correct", graded),
        "abstained": count("abstained", g),
        "mean_p_call_needs_tool": p(by["needs_tool"]),
        "mean_p_call_no_tool": p(by["no_tool"]),
        "median_seconds": round(statistics.median(rows[q["id"]]["seconds"] for q in questions), 2),
        "median_prompt_tokens": statistics.median(rows[q["id"]]["prompt_tokens"] for q in questions),
    }


def per_tool(questions, rows):
    """For each tool a case names: needed and called, its near misses called, and calls nobody asked for."""
    g = {q["id"]: grade_row(q, rows[q["id"]]) for q in questions}
    names = sorted({n for q in questions for n in (expected(q) or ())} | {q["pair"] for q in questions if q.get("pair")})
    out = {}
    for n in names:
        need = [q for q in questions if n in (expected(q) or ())]
        near = [q for q in questions if q.get("pair") == n and q["label"] == "no_tool"]
        out[n] = {
            "called_when_needed": frac(sum(n in g[q["id"]]["tools_called"] for q in need), len(need)),
            "near_miss_called_anything": frac(sum(g[q["id"]]["called"] for q in near), len(near)),
            "called_unasked": sum(n in g[q["id"]]["tools_called"] and n not in (expected(q) or ()) and q["expect"] != "any"
                                  for q in questions),
        }
    return out


def diff(questions, ref, rows):
    """Row by row against the reference: calls lost, calls gained, and where the decision token went."""
    ref_called = [q for q in questions if ref[q["id"]]["calls"]]
    lost = [q for q in ref_called if not rows[q["id"]]["calls"]]
    gained = [q for q in questions if rows[q["id"]]["calls"] and not ref[q["id"]]["calls"]]
    names = lambda src, q: {c["name"] for c in src[q["id"]]["calls"]}
    changed = [q for q in ref_called if rows[q["id"]]["calls"] and names(ref, q) != names(rows, q)]
    p = lambda src: [src[q["id"]]["p_call"] for q in ref_called if src[q["id"]]["p_call"] is not None]
    tok_mismatch = [q["id"] for q in questions if ref[q["id"]]["prompt_tokens"] != rows[q["id"]]["prompt_tokens"]]
    row = lambda q: {"id": q["id"], "label": q["label"], "question": q["question"]}
    return {
        "reference_calls": len(ref_called),
        "lost": len(lost), "gained": len(gained), "changed_tool": len(changed),
        "lost_needs_tool": sum(q["label"] == "needs_tool" for q in lost),
        "gained_no_tool": sum(q["label"] == "no_tool" for q in gained),
        "agree": sum(bool(ref[q["id"]]["calls"]) == bool(rows[q["id"]]["calls"]) for q in questions),
        "rows": len(questions),
        "mean_p_call_on_reference_calls": {"reference": _mean(p(ref)), "file": _mean(p(rows))},
        "lost_rows": [row(q) for q in lost], "gained_rows": [row(q) for q in gained],
        "changed_tool_rows": [row(q) for q in changed],
        "prompt_token_count_differs": tok_mismatch,
    }


def _mean(v):
    return round(statistics.mean(v), 3) if v else "n/a"


SUMMARY_COLUMNS = [
    ("called_when_needed", "Called when needed"), ("called_when_not_needed", "Called when not needed"),
    ("called_either_fine", "Called, either fine"), ("wrong_tool", "Wrong tool"), ("bad_arguments", "Bad arguments"),
    ("claimed_use_without_calling", "Claimed use, no call"), ("malformed_calls", "Malformed call"),
    ("hit_token_limit", "Hit token limit"), ("correct_without_call", "Correct without a call"),
    ("mean_p_call_needs_tool", "Mean p(call), needed"), ("mean_p_call_no_tool", "Mean p(call), not needed"),
    ("median_seconds", "Median s"),
]


PER_TOOL = ("called_when_needed", "near_miss_called_anything", "called_unasked")


def _table(header, rows):
    return ["| " + " | ".join(header) + " |", "|---|" + "---|" * (len(header) - 1)] + \
           ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]


def markdown(report):
    out = ["# Tool decision report", "", "Greedy decoding, one turn, no tool is run. Each suite's rows: "
           + "; ".join(f"`{s}` {n['rows']} ({', '.join(f'{k} {v}' for k, v in n['label_counts'].items() if v)})"
                       for s, n in report["suites"].items()) + ".", ""]
    for suite, by_engine in report["summary"].items():
        out += [f"## {suite}", ""]
        for name, d in report["diff"].get(suite, {}).items():
            out.append(f"- **{name} lost {d['lost']} of {d['reference_calls']} calls against its source** "
                       f"({d['lost_needs_tool']} on rows that need a tool), gained {d['gained']} "
                       f"({d['gained_no_tool']} on rows that do not), and switched tool on {d['changed_tool']}. "
                       f"Same decision on {d['agree']} of {d['rows']} rows. Mean p(call) on the reference's calling rows: "
                       f"{d['mean_p_call_on_reference_calls']['reference']} reference, "
                       f"{d['mean_p_call_on_reference_calls']['file']} file.")
            if d["prompt_token_count_differs"]:
                out.append(f"  - Prompt tokenised differently from the reference on {len(d['prompt_token_count_differs'])} "
                           "rows; check the tokenizer before reading the diff.")
        # One column per engine, so reference, file on the laptop and file on the phone sit side by side.
        out += [""] + _table(["Metric"] + list(by_engine), [[t] + [s[k] for s in by_engine.values()]
                                                            for k, t in SUMMARY_COLUMNS]) + [""]
        for name, d in report["diff"].get(suite, {}).items():
            for kind in ("lost", "gained", "changed_tool"):
                if d[f"{kind}_rows"]:
                    out += [f"{name}, calls {kind.replace('_', ' ')}:", ""] + \
                           [f"- `{r['label']}` {r['question'][:160]}" for r in d[f"{kind}_rows"]] + [""]
    tools = report.get("per_tool", {})
    if any(tools.values()):
        engines = list(tools)
        names = sorted({n for t in tools.values() for n in t})
        out += ["## Per tool", "", "Needed: called that tool, of the rows that need it. Near miss: called anything, "
                "of the paired rows that need nothing. Unasked: calls to it on rows that wanted another tool or none.", ""]
        out += _table(["Tool"] + [f"{e}: {c}" for e in engines for c in ("needed", "near miss", "unasked")],
                      [[n] + [tools[e].get(n, {}).get(c, "") for e in engines for c in PER_TOOL] for n in names]) + [""]
    out += ["p(call) is the probability of the call-opening token at the first reply token after any think block. "
            "Bad arguments: a call whose arguments fail the tool's JSON schema (unknown argument names included) or "
            "miss what the case requires. Correct is graded only on replies that answered without a call."]
    return "\n".join(out) + "\n"
