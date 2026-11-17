---
name: capri
description: Check whether a quantised or exported model (.gguf or .pte) still decides to call its tools the way the original Hugging Face model does, on the laptop and on an Android phone. Use when someone quantises or exports a tool-calling model, asks "did quantisation break tool calling?", wants to compare GGUF or ExecuTorch files against the reference, writes tool-calling test cases, or reads a capri report.
---

# capri

capri runs the same tool-calling cases through the reference model (Transformers) and one or
more files (`.gguf` via llama.cpp, `.pte` via ExecuTorch), greedy, one turn, no tool executed,
and reports where their decisions differ: call or no call, which tool, valid arguments.

## Install

```bash
pip install "capri-eval[gguf]"          # add ,pte for ExecuTorch; from a checkout: pip install -e ".[gguf,pte]"
```

Python 3.10+. Pulls in PyTorch and Transformers (1 to 2 GB). `llama-cpp-python` may compile
from source. The PyPI name is `capri-eval`; plain `capri` is an unrelated package.

## Run

```bash
capri --reference LiquidAI/LFM3-1.7B --file LFM3-1.7B-Q4_K_M.gguf --file lfm3.pte \
  --suite all --limit 40 --max-tokens 1024 --out capri-out
```

- `--reference` is the HF repo or local folder of the unquantised model. Its chat template and
  tokenizer render every prompt, so all engines see the same text.
- `--file` repeats. A `.pte` uses the reference's `tokenizer.json` unless `--pte-tokenizer` is given.
- `--suite`: `search` (default), `openweights`, `bfcl_relevance`, `bfcl_irrelevance`,
  `bfcl_live_irrelevance`, `all`, or a folder of your own. Repeatable.
- `--limit N` takes N evenly spaced cases per suite. Start with 40 to check things work.
- `--max-tokens`: use 1024 or more for thinking models. The default 384 cuts them off mid-thought.
- `--template-kwargs '{"enable_thinking": false}'` turns thinking off where the template allows.
- Rows are cached in `--out`, keyed by prompt and settings. Rerunning with an extra file or suite
  only runs what is new; changing `--max-tokens` reruns everything.
- The reference is slow (float32 by default). `--device mps` or `cuda` helps.

Output: `<out>/report.md` (read this), `<out>/report.json` (every reply and grade, for scripts or CI).

## Your own cases

A folder with `cases.jsonl`, plus optional `tools.json` (OpenAI function schemas),
`prompt.json` (`{"system": str, "preamble": [messages]}`) and `suite.json` (`{"claim": regex}`):

```json
{"id": "calc-needs", "question": "What is 48731 multiplied by 9277?", "expect": "run_script"}
{"id": "calc-near-miss", "question": "Who invented calculus?", "expect": "none", "pair": "run_script"}
{"id": "w1", "messages": [{"role": "user", "content": "Weather in Manila?"}], "expect": "web_search", "args": {"query": "manila"}}
```

`expect` is a tool name, a list of names, `"any"`, `"none"` or `"either"` (reported, not scored).
`args` values must appear in the call (case and punctuation ignored; `null` means any value).
Write each tool a case that needs it and a near miss that sounds like it but does not.
Pass the folder with `--suite path/`, or one file with `--cases f.jsonl --tools t.json`.

## Reading the report

Per suite, engines are columns:

- **Called when needed / not needed**: under-calling and over-calling.
- **Wrong tool, Bad arguments, Malformed call**: should be 0. Malformed calls are often the first
  sign of quantisation damage.
- **Hit token limit**: if this is high, the decision rows are unreliable. Raise `--max-tokens`
  before blaming the file.
- **Same decision as reference**, plus lists of lost, gained and changed-tool rows: open those
  rows in `report.json` and read the replies before drawing conclusions.
- **Per tool**: needed, near miss (called anything) and unasked calls for each tool.

One greedy run on 40 cases: a difference of one or two rows is noise. Report counts, not
percentages, and say how many disagreements were truncation.

## On the phone (Android)

The phone runs the same cases through OpenWeights' own engines (`ToolDecisionEval`
instrumented test, OpenWeights branch `test/tool-decision-eval`). Build its APK with
`./gradlew :core:engine:assembleDebugAndroidTest` (one Gradle build at a time).

```bash
capri --reference R --suite all --limit 40 --max-tokens 1024 --phone-export capri-phone
ADB=~/Library/Android/sdk/platform-tools/adb scripts/phone.sh <ip:port> engine-debug-androidTest.apk capri-phone model.gguf model.pte
capri --reference R --file model.gguf --file model.pte --suite all --limit 40 --max-tokens 1024 \
  --phone capri-phone/results/model.gguf.jsonl --phone capri-phone/results/model.pte.jsonl
```

- Export and grade with the same `--suite`, `--limit` and `--max-tokens`, or grading stops on missing rows.
- The phone needs wireless debugging on and paired; if `adb devices` is empty, stop and ask the
  user to open Wireless debugging (some phones only advertise while that screen is open).
- A dropped connection loses one case: rerun `phone.sh` and it resumes.
- Phone columns show `<model>@phone`. A drop only on the phone points at the runtime, a drop on the
  laptop file too points at the quantisation. The phone uses the app's template and reports no p(call).

## Limits

One turn, no tool runs: it measures the decision, not whether the result is used. Results depend
on the system prompt; the `search` and `openweights` suites use the OpenWeights app's text.
