"""Tool calls out of a model's raw reply, in the three formats small models emit.

- Hermes / Qwen3: `<tool_call>{"name": "f", "arguments": {...}}</tool_call>`
- LFM2 / LFM2.5 pythonic: `<|tool_call_start|>[f(a=1, b="x")]<|tool_call_end|>`
- Qwen3.5 / LFM3 XML parameters:
  `<tool_call><function=f><parameter=a>1</parameter></function></tool_call>`

Named formats only. A parser that guesses at unknown syntax turns damage into calls, and
damage is what this tool is looking for: a call that was started and could not be read is
reported as malformed, not silently dropped or silently accepted.
"""
import ast, json, re

# The token a call opens with, per format. Its probability at the decision step is the
# number the quantisation probe tracked.
CALL_OPENERS = ("<|tool_call_start|>", "<tool_call>")

PYTHONIC = re.compile(r"<\|tool_call_start\|>(.*?)<\|tool_call_end\|>", re.S)
TAGGED = re.compile(r"<tool_call>(.*?)</tool_call>", re.S)
FUNCTION = re.compile(r"<function=([^>\s]+)\s*>")
PARAMETER = re.compile(r"<parameter=([^>\s]+)\s*>(.*?)</parameter>", re.S)


def parse_calls(text):
    """Every readable call in `text`, as [{"name": str, "arguments": dict}]."""
    return _pythonic(text) + _tagged(text)


def started(text):
    """Whether the reply opened a call at all, readable or not."""
    return any(o in text for o in CALL_OPENERS)


def _pythonic(text):
    calls = []
    for body in PYTHONIC.findall(text):
        try:
            tree = ast.parse(body.strip(), mode="eval").body
        except SyntaxError:
            continue
        for node in tree.elts if isinstance(tree, (ast.List, ast.Tuple)) else [tree]:
            if not (isinstance(node, ast.Call) and isinstance(node.func, (ast.Name, ast.Attribute))) or node.args:
                continue
            try:
                args = {k.arg: ast.literal_eval(k.value) for k in node.keywords}
            except (ValueError, SyntaxError):
                continue
            calls.append({"name": ast.unparse(node.func), "arguments": args})  # BFCL names have dots
    return calls


def _tagged(text):
    calls = []
    for body in TAGGED.findall(text):
        body = body.strip()
        fn = FUNCTION.search(body)
        if fn:
            calls.append({"name": fn.group(1), "arguments": {k: _value(v.strip()) for k, v in PARAMETER.findall(body)}})
            continue
        try:
            obj = json.loads(body)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("name"), str):
            args = obj.get("arguments", obj.get("parameters", {}))
            if isinstance(args, str):  # some models double-encode the arguments
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    continue
            if isinstance(args, dict):
                calls.append({"name": obj["name"], "arguments": args})
    return calls


def _value(raw):
    """XML parameters are strings unless the template wrote JSON (numbers, lists, objects)."""
    if raw[:1] in "[{" or raw in ("true", "false", "null") or re.fullmatch(r"-?\d+(\.\d+)?", raw):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
    return raw
