"""Convert BFCL v4's relevance and irrelevance sets into capri suites.

    python scripts/convert_bfcl.py <dir with BFCL_v4_{live_relevance,irrelevance,live_irrelevance}.json>

Source: ShishirPatil/gorilla, berkeley-function-call-leaderboard/bfcl_eval/data, Apache-2.0.
BFCL writes parameter types in Python terms (dict, float, tuple, any); they become JSON Schema.
Only the first turn of each question is kept; these sets are single turn.
"""
import json, sys
from pathlib import Path

TYPES = {"dict": "object", "float": "number", "tuple": "array", "list": "array", "int": "integer", "str": "string",
         "bool": "boolean"}
OUT = Path(__file__).resolve().parent.parent / "capri" / "data" / "suites"


def schema(s):
    if isinstance(s, list):
        return [schema(x) for x in s]
    if not isinstance(s, dict):
        return s
    s = {k: ({n: schema(v) for n, v in val.items()} if k == "properties" else schema(val)) for k, val in s.items()}
    if s.get("type") == "any":
        del s["type"]
    elif "type" in s:
        s["type"] = TYPES.get(s["type"], s["type"])
    return s


def convert(src, name, expect, title):
    rows = [json.loads(l) for l in src.read_text().splitlines() if l.strip()]
    d = OUT / name
    d.mkdir(parents=True, exist_ok=True)
    with (d / "cases.jsonl").open("w") as f:
        for r in rows:
            tools = [{"type": "function", "function": {**fn, "parameters": schema(fn.get("parameters", {}))}}
                     for fn in r["function"]]
            f.write(json.dumps({"id": r["id"], "messages": r["question"][0], "tools": tools, "expect": expect},
                               ensure_ascii=False) + "\n")
    (d / "suite.json").write_text(json.dumps({"title": title, "source": "BFCL v4 (gorilla, Apache-2.0)"}, indent=1) + "\n")
    print(name, len(rows))


src = Path(sys.argv[1])
convert(src / "BFCL_v4_live_relevance.json", "bfcl_relevance", "any",
        "BFCL live relevance: user-contributed requests where at least one offered function fits")
convert(src / "BFCL_v4_irrelevance.json", "bfcl_irrelevance", "none",
        "BFCL irrelevance: no offered function fits the request")
convert(src / "BFCL_v4_live_irrelevance.json", "bfcl_live_irrelevance", "none",
        "BFCL live irrelevance: user-contributed requests no offered function fits")
