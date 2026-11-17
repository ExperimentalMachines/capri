# Tool decision report

Greedy decoding, one turn, no tool is run. Each suite's rows: `search` 160 (needs_tool 75, no_tool 60, no_target 25).

## search


| Metric | LFM3-1.7B-8da4w-gptq-4k.pte@phone |
|---|---|
| Called when needed | 74/75 |
| Called when not needed | 39/60 |
| Called, either fine | 22/25 |
| Wrong tool | 0/74 |
| Bad arguments | 0/135 |
| Claimed use, no call | 0/160 |
| Malformed call | 0/160 |
| Hit token limit | 2/160 |
| Correct without a call | 19/23 |
| Mean p(call), needed | None |
| Mean p(call), not needed | None |
| Median s | 10.27 |

## Per tool

Needed: called that tool, of the rows that need it. Near miss: called anything, of the paired rows that need nothing. Unasked: calls to it on rows that wanted another tool or none.

| Tool | LFM3-1.7B-8da4w-gptq-4k.pte@phone: needed | LFM3-1.7B-8da4w-gptq-4k.pte@phone: near miss | LFM3-1.7B-8da4w-gptq-4k.pte@phone: unasked |
|---|---|---|---|
| web_search | 74/75 | 39/60 | 39 |

p(call) is the probability of the call-opening token at the first reply token after any think block. Bad arguments: a call whose arguments fail the tool's JSON schema (unknown argument names included) or miss what the case requires. Correct is graded only on replies that answered without a call.
