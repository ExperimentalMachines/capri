# Tool decision report

Question set: `tool_decision_eval/data/decisions.jsonl`, 40 rows (needs_tool 19, no_tool 14, no_target 7). Greedy decoding, one turn, no tool is run.

- **LFM2.5-1.2B-Instruct-Q4_K_M.gguf lost 0 of 1 calls against its source** (0 on rows that need a tool), and gained 2 it did not make (0 on rows that do not). Same decision on 38 of 40 rows. Mean p(call) on the reference's calling rows: 0.484 reference, 0.634 file.

| Engine | Called when needed | Called when not needed | Called, no target | Claimed a search, no call | Malformed call | Hit token limit | Correct without a call | Abstained | Mean p(call), needed | Mean p(call), not needed | Median s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| reference | 0/19 | 0/14 | 1/7 | 0/40 | 0/40 | 0/40 | 10/29 | 10/40 | 0.061 | 0.04 | 5.02 |
| LFM2.5-1.2B-Instruct-Q4_K_M.gguf | 1/19 | 0/14 | 2/7 | 0/40 | 0/40 | 0/40 | 7/28 | 7/40 | 0.101 | 0.055 | 1.66 |

LFM2.5-1.2B-Instruct-Q4_K_M.gguf, calls gained:

- `no_target` Who was the screenwriter for Hell of the Living Dead?
- `needs_tool` The longest winning streak in the last season of the Premier League consisted of how many matches?

p(call) is the probability of the call-opening token at the first reply token after any think block. Correct is graded only on replies that answered without a call, rows whose answer may have moved excluded.
