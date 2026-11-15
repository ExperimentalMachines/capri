"""Grading rules and the report.

Answer matching is ported from OpenWeights' `tools/eval/bench/grade_decisions.py`: SQuAD
normalisation, aliases matched as whole words (plain substring containment credited "ca" in
"located" and "us" in "focus", 276 wrong replies counted right over 9,060 rows), a token-F1
of 0.5 for short replies, and a fifteen character floor so a bare word is not credited unless
it is the alias.
"""
import collections, re, statistics, string, unicodedata

ARTICLES = re.compile(r"\b(a|an|the)\b")
# OpenWeights' pattern without its bare "web search", which also matched offers ("I can look it
# up for you using a web search") on the first laptop run; an offer is not a claim.
SEARCH_TALK = re.compile(
    r"\b(search results?|according to (the )?(search|sources?|results?)|"
    r"the sources? (say|indicate|show)|based on (my|the|a) search|i (searched|looked (it )?up))\b", re.I)
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


def grade_row(q, r):
    """One question and one engine's reply -> the flags the report counts."""
    called = bool(r["calls"])
    reply = plain(r["reply"])
    return {
        "label": q["label"],
        "called": called,
        "malformed": r["started"] and not called,
        "truncated": r.get("truncated", False),
        "fabricated": not called and bool(SEARCH_TALK.search(reply)),
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
    graded = [x for x in g if x["correct"] is not None]
    p = lambda xs: round(statistics.mean(v), 3) if (v := [x["p_call"] for x in xs if x["p_call"] is not None]) else None
    return {
        "rows": len(g),
        "called_when_needed": frac(sum(x["called"] for x in by["needs_tool"]), len(by["needs_tool"])),
        "called_when_not_needed": frac(sum(x["called"] for x in by["no_tool"]), len(by["no_tool"])),
        "called_no_target": frac(sum(x["called"] for x in by["no_target"]), len(by["no_target"])),
        "claimed_search_without_calling": frac(sum(x["fabricated"] for x in g), len(g)),
        "malformed_calls": frac(sum(x["malformed"] for x in g), len(g)),
        "hit_token_limit": frac(sum(x["truncated"] for x in g), len(g)),
        "correct_without_call": frac(sum(x["correct"] for x in graded), len(graded)),
        "abstained": frac(sum(x["abstained"] for x in g), len(g)),
        "mean_p_call_needs_tool": p(by["needs_tool"]),
        "mean_p_call_no_tool": p(by["no_tool"]),
        "median_seconds": round(statistics.median(rows[q["id"]]["seconds"] for q in questions), 2),
        "median_prompt_tokens": statistics.median(rows[q["id"]]["prompt_tokens"] for q in questions),
    }


def diff(questions, ref, rows):
    """Row by row against the reference: calls lost, calls gained, and where the decision token went."""
    ref_called = [q for q in questions if ref[q["id"]]["calls"]]
    lost = [q for q in ref_called if not rows[q["id"]]["calls"]]
    gained = [q for q in questions if rows[q["id"]]["calls"] and not ref[q["id"]]["calls"]]
    p = lambda src: [src[q["id"]]["p_call"] for q in ref_called if src[q["id"]]["p_call"] is not None]
    tok_mismatch = [q["id"] for q in questions if ref[q["id"]]["prompt_tokens"] != rows[q["id"]]["prompt_tokens"]]
    return {
        "reference_calls": len(ref_called),
        "lost": len(lost), "gained": len(gained),
        "lost_needs_tool": sum(q["label"] == "needs_tool" for q in lost),
        "gained_no_tool": sum(q["label"] == "no_tool" for q in gained),
        "agree": sum(bool(ref[q["id"]]["calls"]) == bool(rows[q["id"]]["calls"]) for q in questions),
        "rows": len(questions),
        "mean_p_call_on_reference_calls": {"reference": _mean(p(ref)), "file": _mean(p(rows))},
        "lost_rows": [{"id": q["id"], "label": q["label"], "question": q["question"]} for q in lost],
        "gained_rows": [{"id": q["id"], "label": q["label"], "question": q["question"]} for q in gained],
        "prompt_token_count_differs": tok_mismatch,
    }


def _mean(v):
    return round(statistics.mean(v), 3) if v else "n/a"


SUMMARY_COLUMNS = [
    ("called_when_needed", "Called when needed"), ("called_when_not_needed", "Called when not needed"),
    ("called_no_target", "Called, no target"), ("claimed_search_without_calling", "Claimed a search, no call"),
    ("malformed_calls", "Malformed call"), ("hit_token_limit", "Hit token limit"), ("correct_without_call", "Correct without a call"),
    ("abstained", "Abstained"), ("mean_p_call_needs_tool", "Mean p(call), needed"),
    ("mean_p_call_no_tool", "Mean p(call), not needed"), ("median_seconds", "Median s"),
]


def markdown(report):
    out = [f"# Tool decision report", "", f"Question set: `{report['questions']}`, {report['rows']} rows "
           f"({', '.join(f'{k} {v}' for k, v in report['label_counts'].items())}). Greedy decoding, one turn, no tool is run.", ""]
    for name, d in report["diff"].items():
        lost = f"**{name} lost {d['lost']} of {d['reference_calls']} calls against its source**"
        out.append(f"- {lost} ({d['lost_needs_tool']} on rows that need a tool), and gained {d['gained']} it did not make "
                   f"({d['gained_no_tool']} on rows that do not). Same decision on {d['agree']} of {d['rows']} rows. "
                   f"Mean p(call) on the reference's calling rows: {d['mean_p_call_on_reference_calls']['reference']} "
                   f"reference, {d['mean_p_call_on_reference_calls']['file']} file.")
        if d["prompt_token_count_differs"]:
            out.append(f"  - Prompt tokenised differently from the reference on {len(d['prompt_token_count_differs'])} rows; "
                       "check the tokenizer before reading the diff.")
    out += ["", "| Engine | " + " | ".join(t for _, t in SUMMARY_COLUMNS) + " |", "|---|" + "---|" * len(SUMMARY_COLUMNS)]
    for name, s in report["summary"].items():
        out.append(f"| {name} | " + " | ".join(str(s[k]) for k, _ in SUMMARY_COLUMNS) + " |")
    for name, d in report["diff"].items():
        for kind in ("lost", "gained"):
            if d[f"{kind}_rows"]:
                out += ["", f"{name}, calls {kind}:", ""] + [f"- `{r['label']}` {r['question']}" for r in d[f"{kind}_rows"]]
    out += ["", "p(call) is the probability of the call-opening token at the first reply token after any think block. "
            "Correct is graded only on replies that answered without a call, rows whose answer may have moved excluded."]
    return "\n".join(out) + "\n"
