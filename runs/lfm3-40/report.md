# Tool decision report

Question set: `tool_decision_eval/data/decisions.jsonl`, 40 rows (needs_tool 19, no_tool 14, no_target 7). Greedy decoding, one turn, no tool is run.

- **LFM3-1.7B-Q4_K_M.gguf lost 2 of 34 calls against its source** (0 on rows that need a tool), and gained 1 it did not make (1 on rows that do not). Same decision on 37 of 40 rows. Mean p(call) on the reference's calling rows: 1.0 reference, 0.97 file.
- **lfm_3_1_7b_xnnpack_8da4w.pte lost 0 of 34 calls against its source** (0 on rows that need a tool), and gained 1 it did not make (0 on rows that do not). Same decision on 39 of 40 rows. Mean p(call) on the reference's calling rows: 1.0 reference, 0.999 file.

| Engine | Called when needed | Called when not needed | Called, no target | Claimed a search, no call | Malformed call | Hit token limit | Correct without a call | Abstained | Mean p(call), needed | Mean p(call), not needed | Median s |
|---|---|---|---|---|---|---|---|---|---|---|---|
| reference | 19/19 | 9/14 | 6/7 | 0/40 | 0/40 | 1/40 | 5/5 | 0/40 | 1.0 | 0.643 | 51.77 |
| LFM3-1.7B-Q4_K_M.gguf | 19/19 | 8/14 | 6/7 | 0/40 | 0/40 | 2/40 | 4/6 | 1/40 | 1.0 | 0.615 | 7.99 |
| lfm_3_1_7b_xnnpack_8da4w.pte | 19/19 | 9/14 | 7/7 | 0/40 | 0/40 | 0/40 | 4/5 | 0/40 | 0.999 | 0.642 | 11.55 |

LFM3-1.7B-Q4_K_M.gguf, calls lost:

- `no_tool` How long do NFL football teams have to get a play off (the play clock)?
- `no_tool` Who is Elrond's father in J. R. R. Tolkien's Middle Earth stories?

LFM3-1.7B-Q4_K_M.gguf, calls gained:

- `no_tool` What sport does 2009 Atlantic Coast Conference Baseball Tournament play?

lfm_3_1_7b_xnnpack_8da4w.pte, calls gained:

- `no_target` Which is the oldest still-running university in the world?

p(call) is the probability of the call-opening token at the first reply token after any think block. Correct is graded only on replies that answered without a call, rows whose answer may have moved excluded.
