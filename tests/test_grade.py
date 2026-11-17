"""Answer matching cases carried over from OpenWeights' test_grade_decisions.py, plus the decision grades."""
from tool_decision_eval import suites
from tool_decision_eval.cli import decision_p
from tool_decision_eval.grade import contains, correct, diff, grade_row, normalize, per_tool, summarize


def test_an_alias_inside_a_word_is_not_credited():
    assert not correct("Zec Petawaga is located in the Democratic Republic of the Congo.", ["CA", "ca"])
    assert not correct("Monitor House is located in the United Kingdom, specifically London.", ["US", "U.S."])
    assert not correct("Columbia is not a capital; Bogota serves as its capital city.", ["S. C."])
    assert not correct("Sheep with eight teeth are aged, typically over 2024 standards here.", ["2"])


def test_whole_words_are_still_credited():
    assert correct("Zec Petawaga is in Canada, in the province of Quebec.", ["Canada", "CA"])
    assert correct("The USS Constitution is a ship of the US Navy.", ["US"])
    assert correct("Columbia is the capital of South Carolina.", ["South Carolina", "SC"])


def test_numbers_and_punctuation():
    assert correct("The answer is 3.5 percent according to the report.", ["3.5"])
    assert not correct("The answer is 13.5 percent according to the report.", ["3.5"])
    assert correct("Jean-Luc Godard directed the film in 1960.", ["Jean-Luc Godard"])
    assert correct("It is written in C++ for speed, mostly.", ["C++"])


def test_scripts():
    assert contains(normalize("答えは東京都です"), normalize("東京"))
    assert contains(normalize("수도는 서울 입니다"), normalize("서울"))
    assert not contains(normalize("수도는 서울특별시 입니다"), normalize("서울"))


def test_short_replies_must_be_the_alias():
    assert correct("Canada", ["Canada"]) and not correct("Congo", ["Canada"])


SEARCH = {"type": "function", "function": {"name": "web_search", "parameters": {
    "type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}
CALC = {"type": "function", "function": {"name": "calc", "parameters": {
    "type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}}}
CLAIM = suites.load("search")[0]["claim"]


def case(expect="web_search", **kw):
    return {"id": "a", "question": "q", "answers": [], "tools": [SEARCH, CALC], "expect": expect,
            "label": "no_tool" if expect == "none" else "no_target" if expect == "either" else "needs_tool", "claim": CLAIM, **kw}


def row(calls=False, reply="Rome.", p=0.1, started=None, tokens=10, name="web_search", args=None):
    c = [{"name": name, "arguments": {"query": "x"} if args is None else args}] if calls else []
    return {"calls": c, "started": bool(calls) if started is None else started, "reply": reply,
            "p_call": p, "seconds": 1.0, "prompt_tokens": tokens}


def test_row_flags():
    need = case(answers=["Lazio"])
    assert grade_row(need, row(calls=True))["called"]
    g = grade_row(need, row(reply="Based on my search, it is the capital of Lazio."))
    assert g["claimed"] and g["correct"] and not g["called"]
    assert not grade_row(need, row(reply="I don't know. If you'd like, I can look it up using a web search."))["claimed"]
    assert grade_row(need, row(reply="According to the search results, it is Lazio."))["claimed"]
    assert grade_row(need, row(reply="<|tool_call_start|>[web_search(", started=True))["malformed"]
    assert grade_row(need, row(calls=True))["correct"] is None  # nothing ran, so nothing to grade
    assert grade_row({**need, "stale_risk": True}, row(reply="It is the capital of Lazio."))["correct"] is None


def test_wrong_tool_and_bad_arguments():
    need = case()
    assert grade_row(need, row(calls=True, name="calc", args={"n": 1}))["wrong_tool"]
    assert not grade_row(case("any"), row(calls=True, name="calc", args={"n": 1}))["wrong_tool"]
    assert grade_row(need, row(calls=True, name="websearch"))["unknown_tool"]
    assert grade_row(need, row(calls=True, args={}))["bad_arguments"]  # required query missing
    assert grade_row(need, row(calls=True, args={"query": "x", "qeury": "y"}))["bad_arguments"]  # not its argument
    assert grade_row(need, row(calls=True, name="calc", args={"n": "three"}))["bad_arguments"]
    assert not grade_row(need, row(calls=True, args={"query": 2024}))["bad_arguments"]  # XML values arrive as text
    assert grade_row(case(args={"query": "rome"}), row(calls=True))["bad_arguments"]
    assert not grade_row(case(args={"query": "rome"}), row(calls=True, args={"query": "Rome weather"}))["bad_arguments"]
    assert not grade_row(case(["calc", "web_search"]), row(calls=True, name="calc", args={"n": 2}))["wrong_tool"]


def test_summary_and_diff_count_lost_calls():
    qs = [case(e, id=str(i), question=f"q{i}") for i, e in enumerate(["web_search"] * 3 + ["none"] * 2 + ["either"])]
    ref = {q["id"]: row(calls=q["label"] == "needs_tool", p=0.8 if q["label"] == "needs_tool" else 0.05) for q in qs}
    quant = {q["id"]: row(calls=q["id"] == "3", p=0.6 if q["id"] == "3" else 0.1) for q in qs}
    s = summarize(qs, quant)
    assert s["called_when_needed"] == "0/3" and s["called_when_not_needed"] == "1/2" and s["called_either_fine"] == "0/1"
    d = diff(qs, ref, quant)
    assert (d["reference_calls"], d["lost"], d["gained"], d["agree"]) == (3, 3, 1, 2)
    assert d["mean_p_call_on_reference_calls"] == {"reference": 0.8, "file": 0.1}
    swapped = {**ref, "0": row(calls=True, name="calc", args={"n": 1})}
    assert diff(qs, ref, swapped)["changed_tool"] == 1


def test_per_tool_pairs():
    qs = [case("calc", id="n"), case("none", id="m", pair="calc"), case("none", id="o"), case("either", id="p")]
    rows = {i: row(calls=True, name="calc", args={"n": 1}) for i in "nmop"}  # an either-fine call is not unasked
    assert per_tool(qs, rows)["calc"] == {"called_when_needed": "1/1", "near_miss_called_anything": "1/1", "called_unasked": 2}


def test_decision_token_skips_think_and_whitespace():
    assert decision_p(["<think>", "hmm", "</think>", "\n\n", "<tool_call>"], [0, 0, 0, 0.2, 0.9], False) == 0.9
    assert decision_p(["hmm", "</think>", "Rome"], [0.5, 0, 0.3], True) == 0.3  # template opened the think block
    assert decision_p(["<think>", "hmm"], [0, 0], False) is None  # never left the think block


def test_shipped_suites_load():
    for name in suites.SHIPPED:
        rows = suites.load(name, 40)
        assert rows and len({r["id"] for r in rows}) == len(rows)
        assert all(r["tools"] and r["messages"][-1]["role"] == "user" for r in rows)
    search = suites.load("search", 40)
    assert {r["label"] for r in search} == {"needs_tool", "no_tool", "no_target"}
    ow = suites.load("openweights")
    assert len(ow) == 34 and {r["pair"] for r in ow if r.get("pair")} == {t["function"]["name"] for t in ow[0]["tools"]}


def test_v01_question_sets_still_load(tmp_path):
    (tmp_path / "q.jsonl").write_text('{"id": "x", "question": "q", "label": "needs_tool"}\n')
    (tmp_path / "t.json").write_text('[' + __import__("json").dumps(SEARCH) + ']')
    [r] = suites.load(str(tmp_path / "q.jsonl"), tools=str(tmp_path / "t.json"))
    assert r["expect"] == "any" and r["id"] == "q/x" and r["messages"] == [{"role": "user", "content": "q"}]


def test_phone_rows(tmp_path):
    from tool_decision_eval.cli import phone_rows
    qs = [case(id="a"), case("none", id="b"), case(id="c")]
    lines = [{"id": "a", "raw": "<think>x</think><tool_call>\n<function=web_search>\n<parameter=query>\nRome\n</parameter>\n"
                                "</function>\n</tool_call>", "stop": "END_OF_TURN", "prompt_tokens": 9},
             {"id": "b", "raw": "Rome.", "stop": "MAX_TOKENS"},
             {"id": "c", "raw": "", "content": "", "app_calls": [{"name": "web_search", "arguments": '{"query": "x"}'}]}]
    (tmp_path / "m.jsonl").write_text("".join(__import__("json").dumps(l) + "\n" for l in lines))
    rows = phone_rows(tmp_path / "m.jsonl", qs)
    assert rows["a"]["calls"] == [{"name": "web_search", "arguments": {"query": "Rome"}}] and rows["a"]["p_call"] is None
    assert not rows["b"]["calls"] and rows["b"]["truncated"]
    assert rows["c"]["calls"] == [{"name": "web_search", "arguments": {"query": "x"}}]  # the app's parse stands in


def test_every_shipped_suite_loads_in_full():
    from tool_decision_eval import suites
    for n in suites.SHIPPED:
        assert suites.load(n, None)
