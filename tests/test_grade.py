"""Answer matching cases carried over from OpenWeights' test_grade_decisions.py, plus the decision grades."""
from tool_decision_eval.cli import decision_p, load_questions
from tool_decision_eval.grade import contains, correct, diff, grade_row, normalize, summarize


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


def row(calls=False, reply="Rome.", p=0.1, started=None, tokens=10):
    c = [{"name": "web_search", "arguments": {"query": "x"}}] if calls else []
    return {"calls": c, "started": bool(calls) if started is None else started, "reply": reply,
            "p_call": p, "seconds": 1.0, "prompt_tokens": tokens}


def test_row_flags():
    need = {"id": "a", "label": "needs_tool", "question": "q", "answers": ["Lazio"]}
    assert grade_row(need, row(calls=True))["called"]
    g = grade_row(need, row(reply="Based on my search, it is the capital of Lazio."))
    assert g["fabricated"] and g["correct"] and not g["called"]
    assert not grade_row(need, row(reply="I don't know. If you'd like, I can look it up using a web search."))["fabricated"]
    assert grade_row(need, row(reply="According to the search results, it is Lazio."))["fabricated"]
    assert grade_row(need, row(reply="<|tool_call_start|>[web_search(", started=True))["malformed"]
    assert grade_row(need, row(calls=True))["correct"] is None  # nothing ran, so nothing to grade
    assert grade_row({**need, "stale_risk": True}, row(reply="It is the capital of Lazio."))["correct"] is None


def test_summary_and_diff_count_lost_calls():
    qs = [{"id": str(i), "label": lab, "question": f"q{i}", "answers": []}
          for i, lab in enumerate(["needs_tool"] * 3 + ["no_tool"] * 2 + ["no_target"])]
    ref = {q["id"]: row(calls=q["label"] == "needs_tool", p=0.8 if q["label"] == "needs_tool" else 0.05) for q in qs}
    quant = {q["id"]: row(calls=q["id"] == "3", p=0.6 if q["id"] == "3" else 0.1) for q in qs}
    s = summarize(qs, quant)
    assert s["called_when_needed"] == "0/3" and s["called_when_not_needed"] == "1/2" and s["called_no_target"] == "0/1"
    d = diff(qs, ref, quant)
    assert (d["reference_calls"], d["lost"], d["gained"], d["agree"]) == (3, 3, 1, 2)
    assert d["mean_p_call_on_reference_calls"] == {"reference": 0.8, "file": 0.1}


def test_decision_token_skips_think_and_whitespace():
    assert decision_p(["<think>", "hmm", "</think>", "\n\n", "<tool_call>"], [0, 0, 0, 0.2, 0.9], False) == 0.9
    assert decision_p(["hmm", "</think>", "Rome"], [0.5, 0, 0.3], True) == 0.3  # template opened the think block
    assert decision_p(["<think>", "hmm"], [0, 0], False) is None  # never left the think block


def test_default_set_and_even_subset():
    rows = load_questions(__import__("tool_decision_eval.cli").cli.DATA / "decisions.jsonl", 40)
    assert len(rows) == 40 and len({r["id"] for r in rows}) == 40
    assert {r["label"] for r in rows} == {"needs_tool", "no_tool", "no_target"}
