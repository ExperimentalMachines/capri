from tool_decision_eval.parse import parse_calls, started

Q = {"name": "web_search", "arguments": {"query": "Manila weather"}}


def test_hermes_json():
    assert parse_calls('<tool_call>\n{"name": "web_search", "arguments": {"query": "Manila weather"}}\n</tool_call>') == [Q]


def test_hermes_parameters_key_and_string_arguments():
    assert parse_calls('<tool_call>{"name": "web_search", "parameters": {"query": "Manila weather"}}</tool_call>') == [Q]
    assert parse_calls('<tool_call>{"name": "web_search", "arguments": "{\\"query\\": \\"Manila weather\\"}"}</tool_call>') == [Q]


def test_two_hermes_calls():
    two = ('<tool_call>{"name": "a", "arguments": {}}</tool_call>\n'
           '<tool_call>{"name": "b", "arguments": {"x": 1}}</tool_call>')
    assert [c["name"] for c in parse_calls(two)] == ["a", "b"]


def test_lfm_pythonic():
    assert parse_calls('<|tool_call_start|>[web_search(query="Manila weather")]<|tool_call_end|>') == [Q]
    two = "<|tool_call_start|>[a(n=1, f=2.5, ok=True), b(xs=['p', 'q'])]<|tool_call_end|>Checking."
    assert parse_calls(two) == [{"name": "a", "arguments": {"n": 1, "f": 2.5, "ok": True}},
                                {"name": "b", "arguments": {"xs": ["p", "q"]}}]


def test_dotted_names():
    assert parse_calls('<|tool_call_start|>[math.sum(xs=[1, 2])]<|tool_call_end|>') == [{"name": "math.sum", "arguments": {"xs": [1, 2]}}]


def test_xml_parameters_qwen35_and_lfm3():
    xml = ("<tool_call>\n<function=web_search>\n<parameter=query>\nManila weather\n</parameter>\n"
           "</function>\n</tool_call>")
    assert parse_calls(xml) == [Q]
    typed = "<tool_call><function=f><parameter=n>3</parameter><parameter=xs>[1, 2]</parameter></function></tool_call>"
    assert parse_calls(typed) == [{"name": "f", "arguments": {"n": 3, "xs": [1, 2]}}]


def test_prose_is_not_a_call():
    for text in ["Rome is the capital of Lazio.", 'Here is JSON: {"name": "web_search"}', "web_search(query='x')"]:
        assert parse_calls(text) == [] and not started(text)


def test_damaged_calls_are_started_but_not_read():
    for text in ["<|tool_call_start|>[web_search(query=\"Manila]<|tool_call_end|>",
                 "<|tool_call_start|>[web_search(query=\"Manila weather\")",  # cut off before the end marker
                 "<tool_call>\n{\"name\": \"web_search\", \"arguments\": {\"query\": </tool_call>",
                 "<|tool_call_start|>[web_search(f(x))]<|tool_call_end|>"]:  # not a literal, not run
        assert started(text) and parse_calls(text) == []
