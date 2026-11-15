# tool-decision-eval

Does your quantised or exported model still decide to call its tools when it should, and not
when it shouldn't?

A model can keep its perplexity and its benchmark scores through quantisation and still stop
calling tools. In the OpenWeights study that started this tool, LFM2.5 1.2B's compiled 8da4w
ExecuTorch file stopped calling `web_search` (0 of 16 calls on a laptop probe against 16 of 16
unquantised) while the GGUF of the same model kept calling. LFM3 1.7B's compiled file went the
other way and searched on 52 to 55 of 60 questions it could answer from memory. Nothing in the
usual pipeline flagged either: the public on-device harnesses run llama.cpp only and score
quality off-device, and BFCL asks whether the model picks the right tool and declines when none
fits, not whether a fitting tool is needed, and not of the exact file you ship.

This tool runs labelled cases through the unquantised reference (transformers) and through the
file you ship (GGUF via llama.cpp, `.pte` via ExecuTorch), with the same prompt bytes and greedy
decoding, and reports the difference. With the phone runner it adds the same file on an Android
phone, through the app's own engines, as a third column.

## Install and run

```bash
pip install -e ".[gguf]"        # add ,pte for ExecuTorch files
```

```bash
tool-decision-eval --reference LiquidAI/LFM2.5-1.2B-Instruct --file LFM2.5-1.2B-Instruct-Q4_K_M.gguf --limit 40
```

`--reference` is the Hugging Face repo (or local directory) of the source model. Its chat
template renders every prompt once, and each engine tokenises that same string, so the
reference and the file see the same bytes; the report warns if their token counts differ.
Repeat `--file` to compare several files in one report. Results go to `tde-out/report.md` and
`tde-out/report.json`; each engine's rows are cached in `tde-out/<name>.jsonl`, keyed by prompt
and settings, and reused, so adding a file or a suite does not rerun what is done.

Suites: `--suite search` (the default), `openweights`, `bfcl_relevance`, `bfcl_irrelevance`,
`bfcl_live_irrelevance`, or `--suite all`; repeatable. `--limit N` takes N evenly spaced cases
per suite. Bring your own with `--cases my.jsonl --tools my_tools.json [--prompt p.json]`, or a
folder laid out like the shipped ones and passed to `--suite`.

Other options: `--template` (a Jinja file to use instead of the reference's),
`--template-kwargs '{"enable_thinking": false}'`, `--pte-tokenizer`, `--max-tokens` (default
384), `--device`, `--dtype` (reference, default float32), `--no-reference-run` (use the
reference for its template and tokenizer only).

## Cases

One JSON object per line:

```json
{"id": "run_script-needs", "question": "What is 48731 multiplied by 9277?", "expect": "run_script"}
{"id": "run_script-near-miss", "question": "Who invented calculus?", "expect": "none", "pair": "run_script"}
{"id": "w1", "messages": [{"role": "user", "content": "Weather in Manila?"}], "expect": "web_search",
 "args": {"query": "manila"}, "tools": [{"type": "function", "function": {...}}]}
```

- `expect`: a tool name, a list of acceptable names, `"any"` (any offered tool), `"none"`, or
  `"either"` (both decisions defensible: reported, not scored).
- `args` (optional): arguments the expected call must carry, each with a value it must contain
  (case and punctuation ignored) or `null` for any value.
- `tools` (optional): the case's own tool list; otherwise the suite's `tools.json` or `--tools`.
- `pair` (optional): marks a near miss, a case that sounds like it needs that tool and does not.
- `answers`, `stale_risk` (optional): gold aliases, graded on replies that answered without a call.

A suite folder holds `cases.jsonl`, and optionally `tools.json`, `prompt.json`
(`{"system": ..., "preamble": [messages]}`) and `suite.json` (`{"claim": regex}`, the phrases
that count as claiming a tool was used). v0.1 question sets (`label` of `needs_tool`,
`no_tool`, `no_target`) still load.

## What it measures

Per case and engine: whether a tool call was emitted, the parsed call, the reply text, and
p(call), the probability of the call-opening token (`<tool_call>` or `<|tool_call_start|>`) at
the first reply token after any think block. Then, per suite and per tool:

- **Called when needed**: on cases that expect a tool, the share with a call.
- **Called when not needed**: on `none` cases, the share with a call (over-calling).
- **Called, either fine**: on `either` cases, reported and not scored.
- **Wrong tool**: of the needed cases that called, those that called none of the expected tools.
- **Bad arguments**: of the cases with a call, those whose arguments fail the tool's JSON schema
  (an argument name the tool does not have counts, as does a wrong type) or miss the case's
  `args`. XML-parameter calls carry numbers as text, so a number is accepted for a string field.
- **Claimed use, no call**: the reply talks as if a tool ran (the suite's claim phrases) and no
  call was made.
- **Malformed call**: a call was opened and could not be parsed. Quantisation damage can show
  up here before it shows up as a lost call.
- **Correct without a call**: on suites with gold answers, whether a reply that answered
  without a call contains a gold alias as whole words (rules ported from OpenWeights' grader).
- **Per tool**: for each tool a case names, how often it was called when needed, how often
  its near misses called anything, and how often it was called unasked.
- **Against the reference**: calls lost, calls gained, calls that switched tool, rows with the
  same decision, and mean p(call) on the rows where the reference called.

Tool-call formats parsed: Hermes / Qwen3 `<tool_call>{json}</tool_call>`, LFM2 / LFM2.5
pythonic `<|tool_call_start|>[f(a=1)]<|tool_call_end|>`, and Qwen3.5 / LFM3 XML parameters
`<tool_call><function=f><parameter=a>1</parameter></function></tool_call>`. Unknown syntax is
not guessed at.

## On the phone

`scripts/phone.sh` runs the cases on an Android phone through OpenWeights' `:core:engine`
(llama.cpp and ExecuTorch as the app ships them, including the prefix reuse and state the
engine carries from one conversation to the next), using the `ToolDecisionEval` instrumented
test on OpenWeights' `test/tool-decision-eval` branch:

```bash
tool-decision-eval --reference LiquidAI/LFM3-1.7B --suite all --limit 40 --max-tokens 1024 --phone-export tde-phone
scripts/phone.sh <adb-serial> engine-debug-androidTest.apk tde-phone LFM3-1.7B-Q4_K_M.gguf lfm3.pte
tool-decision-eval --reference LiquidAI/LFM3-1.7B --file LFM3-1.7B-Q4_K_M.gguf --file lfm3.pte \
  --phone tde-phone/results/LFM3-1.7B-Q4_K_M.gguf.jsonl --phone tde-phone/results/lfm3.pte.jsonl --suite all --limit 40 --max-tokens 1024
```

The report then has a column per engine: reference, file on the laptop, file on the phone. A
drop on the laptop points at the recipe; a drop only on the phone points at the runtime. Two
differences from the laptop engines: the phone renders the prompt with the app's own template
(the report flags rows whose prompt token count differs from the reference), and the engine
streams only the chosen token's log-probability, so p(call) is not reported for the phone.

## What it does not measure

- **One turn, no tool is run.** It measures the decision, not the loop. Whether the model uses
  the result, or answers right after searching, is out of scope.
- **No phone by default.** Without `--phone`, everything runs on the laptop: the file is the
  shipped file, but the kernels are the laptop's (llama.cpp Metal or CPU, ExecuTorch's host
  XNNPACK), not the phone's.
- **Your app's prompt is not the default.** The `search` and `openweights` suites use the
  OpenWeights app's system text; the BFCL suites use their own messages and no system text.
  Results depend on the prompt; pass your own.
- **One greedy run.** Differences of a few rows on 40 or 160 questions are not established
  differences. p(call) is the more sensitive signal; read it alongside the counts.
- **Correct is a containment check**, not a judge. It can credit a reply that names the alias
  in a wrong sentence and miss a right reply phrased differently.
- No KL or perplexity, no speed claims (the seconds column is the laptop's, for orientation).

## First runs (2026-11-16, Apple silicon laptop, 40 evenly spaced rows)

Full reports: [runs/lfm25-q4km-40/report.md](runs/lfm25-q4km-40/report.md) and
[runs/lfm3-40/report.md](runs/lfm3-40/report.md).

| Model, engine | Called when needed (of 19) | Called when not needed (of 14) | Calls lost / gained against reference | Mean p(call) on reference's calls |
|---|---:|---:|---|---|
| LFM2.5 1.2B, reference fp32 | 0 | 0 | | 0.484 |
| LFM2.5 1.2B, GGUF Q4_K_M | 1 | 0 | 0 of 1 lost, 2 gained | 0.634 |
| LFM3 1.7B, reference fp32, thinking on | 19 | 9 | | 1.0 |
| LFM3 1.7B, GGUF Q4_K_M | 19 | 8 | 2 of 34 lost (both unneeded), 1 gained | 0.97 |
| LFM3 1.7B, `.pte` 8da4w round to nearest | 19 | 9 | 0 of 34 lost, 1 gained | 0.999 |

How to read them:

- Under this single-turn prompt, unquantised LFM2.5 almost never calls (1 of 40), so there is
  little for a quantised file to lose. The OpenWeights laptop probe that measured 16 of 16
  attached the app's note on the named subject to each question; the default prompt here
  does not. A diff is only as informative as the reference's calling rate: check that first.
- LFM3's over-searching is already in the unquantised model here (9 of 14 unneeded questions),
  and the round-to-nearest `.pte` matches its source on 39 of 40 rows. So on this prompt, on
  the laptop, the phone's 55 of 60 is not something the export added. Whether the phone's
  kernels or the app's loop add to it is what the v2 phone runner is for.
- With thinking on, LFM3 decides inside the think block, so p(call) after it is near 0 or 1.
  For a graded signal, run with thinking off (`--template-kwargs '{"enable_thinking": false}'`
  where the template supports it) or read the calls.
- LFM2.5's prompt through its HF template matches the OpenWeights app's bytes except for
  whitespace inside the tool JSON (the app indents it, the template writes it compact).

## Suites

| Suite | Cases | Expect | Tools |
|---|---:|---|---|
| `search` | 160 | 75 `web_search`, 60 `none`, 25 `either` | `web_search` |
| `openweights` | 34 | 17 tools, each needed once and paired with one near miss | the app's 17 tools |
| `bfcl_relevance` | 16 | `any` | each case's own |
| `bfcl_irrelevance` | 240 | `none` | each case's own, none fitting |
| `bfcl_live_irrelevance` | 884 | `none` | each case's own, none fitting |

### search

OpenWeights' 160-row decision set (`tools/eval/bench/decisions.json`, seed 7), converted.

| Label | Rows | From |
|---|---:|---|
| needs_tool | 75 | RetrievalQA rows its authors label as needing retrieval, PopQA least popular quartiles, FreshQA fast-changing |
| no_tool | 60 | RetrievalQA answerable rows, PopQA most popular quartile, FreshQA never-changing |
| no_target | 25 | PopQA third quartile, FreshQA slow-changing and false-premise |

Sources, sampled and relabelled, not modified in content:

- RetrievalQA, Zhang et al. 2024, [hyintell/RetrievalQA](https://github.com/hyintell/RetrievalQA), MIT. Its rows draw on
  PopQA, TriviaQA (Apache-2.0), RealTimeQA, FreshQA and ToolQA (Apache-2.0). The RealTimeQA
  repository ([realtimeqa/realtimeqa_public](https://github.com/realtimeqa/realtimeqa_public)) states no licence; its 8 rows reach
  this set through RetrievalQA's MIT release.
- PopQA, Mallen et al. 2023, [AlexTMallen/adaptive-retrieval](https://github.com/AlexTMallen/adaptive-retrieval), MIT.
- FreshQA, Vu et al. 2023, [freshllms/freshqa](https://github.com/freshllms/freshqa), Apache-2.0.

### openweights

The 17 tool definitions of the OpenWeights app (`core/tools`, Apache-2.0), word for word, all
offered on every case, with the app's system text. Each tool has one request that needs it and
one near miss that sounds like it and does not ("What is 48731 multiplied by 9277?" against
"Who invented calculus?"). The memory tools accept `read_memory` first, and `advance` is asked
after a plan in the conversation. 34 cases is a smoke test per tool, not a measurement.

### BFCL

From the Berkeley Function Calling Leaderboard v4, Patil et al., "The Berkeley Function Calling
Leaderboard (BFCL): From Tool Use to Agentic Evaluation of Large Language Models", ICML 2025,
[ShishirPatil/gorilla](https://github.com/ShishirPatil/gorilla) (`berkeley-function-call-leaderboard/bfcl_eval/data`,
commit 6ea5797), Apache-2.0. `BFCL_v4_live_relevance.json`, `BFCL_v4_irrelevance.json` and
`BFCL_v4_live_irrelevance.json`, first turn of each, with parameter types rewritten from BFCL's
Python names (`dict`, `float`, `tuple`, `any`) to JSON Schema; `scripts/convert_bfcl.py` redoes
it. Relevance cases accept any offered function, as BFCL scores them.

## Tests

```bash
pip install -e ".[test]" && pytest -q
```

## Licence

Apache-2.0. No telemetry, no accounts. The only network access is Hugging Face downloads you
ask for, which read `HF_TOKEN` from your environment if it is set.
