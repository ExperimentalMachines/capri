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

This tool runs one labelled question set through the unquantised reference (transformers) and
through the file you ship (GGUF via llama.cpp, `.pte` via ExecuTorch), with the same prompt
bytes and greedy decoding, and reports the difference.

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
`tde-out/report.json`; each engine's rows are cached in `tde-out/<name>.jsonl` and reused when
the prompts and settings are unchanged, so adding a file does not rerun the reference.

Other options: `--questions`, `--tools` (OpenAI function schema list), `--prompt`
(`{"system": ..., "preamble": [messages]}`), `--template` (a Jinja file to use instead of the
reference's), `--template-kwargs '{"enable_thinking": false}'`, `--pte-tokenizer`,
`--max-tokens` (default 384), `--device`, `--dtype` (reference, default float32),
`--no-reference-run` (use the reference for its template and tokenizer only).

## What it measures

Per row and engine: whether a tool call was emitted, the parsed call, the reply text, and
p(call), the probability of the call-opening token (`<tool_call>` or `<|tool_call_start|>`) at
the first reply token after any think block. Then:

- **Called when needed**: on `needs_tool` rows, the share with a call.
- **Called when not needed**: on `no_tool` rows, the share with a call (over-searching).
- **Called, no target**: on `no_target` rows, reported and not scored. These are the set's
  boundary rows (PopQA's third popularity quartile, slow-changing and false-premise FreshQA
  questions), where either decision is defensible.
- **Claimed a search, no call**: the reply talks of search results ("based on my search...")
  and no call was made.
- **Malformed call**: a call was opened and could not be parsed. Quantisation damage can show
  up here before it shows up as a lost call.
- **Correct without a call**: on rows answered without a call, whether the reply contains a
  gold alias as whole words (rules ported from OpenWeights' grader: SQuAD normalisation, word
  bounded aliases, token F1 of 0.5 for short replies, a 15 character floor). Rows whose answer
  may have moved since the set was built are left out.
- **Against the reference**: calls lost, calls gained, rows with the same decision, and mean
  p(call) on the rows where the reference called, for the reference and for the file.

Tool-call formats parsed: Hermes / Qwen3 `<tool_call>{json}</tool_call>`, LFM2 / LFM2.5
pythonic `<|tool_call_start|>[f(a=1)]<|tool_call_end|>`, and Qwen3.5 / LFM3 XML parameters
`<tool_call><function=f><parameter=a>1</parameter></function></tool_call>`. Unknown syntax is
not guessed at.

## What it does not measure

- **No phone.** Everything runs on the laptop. The file is the shipped file, but the kernels
  are the laptop's (llama.cpp Metal or CPU, ExecuTorch's host XNNPACK), not the phone's. A phone
  runner for llama.cpp and ExecuTorch on Android is v2.
- **One turn, no tool is run.** It measures the decision, not the loop. Whether the model uses
  the result, or answers right after searching, is out of scope.
- **Your app's prompt is not the default.** The default prompt is the OpenWeights app's system
  text and one `web_search` tool. Results depend on the prompt; pass your own with `--prompt`
  and `--tools`.
- **One greedy run.** Differences of a few rows on 40 or 160 questions are not established
  differences. p(call) is the more sensitive signal; read it alongside the counts.
- **Correct is a containment check**, not a judge. It can credit a reply that names the alias
  in a wrong sentence and miss a right reply phrased differently.
- No KL or perplexity, no speed claims (the seconds column is the laptop's, for orientation).

## Question set

`tool_decision_eval/data/decisions.jsonl` is OpenWeights' 160-row decision set
(`tools/eval/bench/decisions.json`, seed 7), converted. Each row has `id`, `question`,
`label` (`needs_tool`, `no_tool`, `no_target`), `answers` (gold aliases), and its source
stratum. `--limit N` takes N evenly spaced rows, which keeps every stratum in. Use your own
set in the same JSONL shape with `--questions`.

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

## Tests

```bash
pip install -e ".[test]" && pytest -q
```

## Licence

Apache-2.0. No telemetry, no accounts. The only network access is Hugging Face downloads you
ask for, which read `HF_TOKEN` from your environment if it is set.
