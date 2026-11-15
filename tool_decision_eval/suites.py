"""Suites: a folder with cases.jsonl, and optionally tools.json, prompt.json and suite.json.

A case is one conversation, the tools offered, and the decision expected:

    {"id": "...", "question": "..." | "messages": [...], "tools": [...]?,
     "expect": "<tool name>" | ["a", "b"] | "any" | "none" | "either", "args": {"query": null}?,
     "pair": "<tool>"?, "answers": [...]?, "stale_risk": bool?}

`tools` on a case overrides the suite's tools.json. `args` names arguments the expected call
must carry (with a value it must contain, or null for any). `pair` marks a near miss: a case
that sounds like it needs that tool and does not. `answers` are gold aliases, graded only on
replies that answered without a call.
"""
import json, sys
from pathlib import Path

from .grade import label

DATA = Path(__file__).parent / "data" / "suites"
SHIPPED = sorted(p.name for p in DATA.iterdir() if (p / "cases.jsonl").exists())
OLD_LABELS = {"needs_tool": "any", "no_tool": "none", "no_target": "either"}  # v0.1 question sets


def _json(path, default):
    return json.loads(path.read_text()) if path and path.exists() else default


def load(spec, limit=None, tools=None, prompt=None):
    """`spec` is a shipped suite name, a suite folder, or a cases .jsonl (then pass `tools`)."""
    p = Path(spec)
    if not p.exists() and (DATA / spec).is_dir():
        p = DATA / spec
    folder = p if p.is_dir() else None
    cases_path = folder / "cases.jsonl" if folder else p
    if not cases_path.exists():
        sys.exit(f"{spec}: not a shipped suite ({', '.join(SHIPPED)}), a suite folder, or a cases file")
    name = p.name if folder else p.stem
    meta = _json(folder and folder / "suite.json", {})
    tools = _json(Path(tools), None) if tools else _json(folder and folder / "tools.json", None)
    prompt = _json(Path(prompt), {}) if prompt else _json(folder and folder / "prompt.json", {})

    rows = [json.loads(l) for l in cases_path.read_text().splitlines() if l.strip()]
    if limit and limit < len(rows):  # evenly spaced, so every stratum of an ordered set is in
        rows = [rows[i * len(rows) // limit] for i in range(limit)]
    for r in rows:
        r.setdefault("expect", OLD_LABELS.get(r.pop("label", None)))
        if not r["expect"] or not (r.get("tools") or tools):
            sys.exit(f"{cases_path}: case {r.get('id')} needs an expect and tools (on the case, tools.json or --tools)")
        msgs = r.get("messages") or [{"role": "user", "content": r["question"]}]
        if msgs[0]["role"] == "system":
            head, msgs = msgs[:1], msgs[1:]
        else:
            head = [{"role": "system", "content": prompt["system"]}] if prompt.get("system") else []
        r.update(id=f"{name}/{r['id']}", suite=name, label=label(r["expect"]), tools=r.get("tools") or tools,
                 question=r.get("question") or next(m["content"] for m in reversed(msgs) if m["role"] == "user"),
                 messages=head + prompt.get("preamble", []) + msgs, claim=meta.get("claim"))
        r.setdefault("answers", [])
    return rows
