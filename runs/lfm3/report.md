# Tool decision report

Greedy decoding, one turn, no tool is run. Each suite's rows: `bfcl_irrelevance` 40 (no_tool 40); `bfcl_live_irrelevance` 40 (no_tool 40); `bfcl_relevance` 16 (needs_tool 16); `openweights` 34 (needs_tool 17, no_tool 17); `search` 40 (needs_tool 19, no_tool 14, no_target 7).

## bfcl_irrelevance

- **LFM3-1.7B-Q4_K_M.gguf lost 1 of 2 calls against its source** (0 on rows that need a tool), gained 2 (2 on rows that do not), and switched tool on 0. Same decision on 37 of 40 rows. Mean p(call) on the reference's calling rows: 1.0 reference, 1.0 file.
- **lfm_3_1_7b_xnnpack_8da4w.pte lost 1 of 2 calls against its source** (0 on rows that need a tool), gained 1 (1 on rows that do not), and switched tool on 0. Same decision on 38 of 40 rows. Mean p(call) on the reference's calling rows: 1.0 reference, 1.0 file.

| Metric | reference | LFM3-1.7B-Q4_K_M.gguf | lfm_3_1_7b_xnnpack_8da4w.pte |
|---|---|---|---|
| Called when needed | n/a | n/a | n/a |
| Called when not needed | 2/40 | 3/40 | 2/40 |
| Called, either fine | n/a | n/a | n/a |
| Wrong tool | n/a | n/a | n/a |
| Bad arguments | 0/2 | 0/3 | 0/2 |
| Claimed use, no call | 0/40 | 1/40 | 0/40 |
| Malformed call | 0/40 | 0/40 | 0/40 |
| Hit token limit | 1/40 | 1/40 | 2/40 |
| Correct without a call | n/a | n/a | n/a |
| Mean p(call), needed | None | None | None |
| Mean p(call), not needed | 0.05 | 0.077 | 0.051 |
| Median s | 31.75 | 18.63 | 11.46 |

LFM3-1.7B-Q4_K_M.gguf, calls lost:

- `no_tool` Who are in the cricket matches scheduled for today?

LFM3-1.7B-Q4_K_M.gguf, calls gained:

- `no_tool` What is the external rate of return for a project with cash flows of -$100, $40, $60, $80, $120?
- `no_tool` What is a holy book?

lfm_3_1_7b_xnnpack_8da4w.pte, calls lost:

- `no_tool` Who are in the cricket matches scheduled for today?

lfm_3_1_7b_xnnpack_8da4w.pte, calls gained:

- `no_tool` What is the external rate of return for a project with cash flows of -$100, $40, $60, $80, $120?

## bfcl_live_irrelevance

- **LFM3-1.7B-Q4_K_M.gguf lost 0 of 2 calls against its source** (0 on rows that need a tool), gained 1 (1 on rows that do not), and switched tool on 0. Same decision on 39 of 40 rows. Mean p(call) on the reference's calling rows: 1.0 reference, 1.0 file.
- **lfm_3_1_7b_xnnpack_8da4w.pte lost 0 of 2 calls against its source** (0 on rows that need a tool), gained 0 (0 on rows that do not), and switched tool on 0. Same decision on 40 of 40 rows. Mean p(call) on the reference's calling rows: 1.0 reference, 1.0 file.

| Metric | reference | LFM3-1.7B-Q4_K_M.gguf | lfm_3_1_7b_xnnpack_8da4w.pte |
|---|---|---|---|
| Called when needed | n/a | n/a | n/a |
| Called when not needed | 2/40 | 3/40 | 2/40 |
| Called, either fine | n/a | n/a | n/a |
| Wrong tool | n/a | n/a | n/a |
| Bad arguments | 0/2 | 0/3 | 0/2 |
| Claimed use, no call | 0/40 | 0/40 | 0/40 |
| Malformed call | 1/40 | 0/40 | 0/40 |
| Hit token limit | 6/40 | 5/40 | 4/40 |
| Correct without a call | n/a | n/a | n/a |
| Mean p(call), needed | None | None | None |
| Mean p(call), not needed | 0.083 | 0.083 | 0.054 |
| Median s | 55.0 | 13.38 | 18.34 |

LFM3-1.7B-Q4_K_M.gguf, calls gained:

- `no_tool` fn_responses

## bfcl_relevance

- **LFM3-1.7B-Q4_K_M.gguf lost 1 of 9 calls against its source** (1 on rows that need a tool), gained 2 (0 on rows that do not), and switched tool on 0. Same decision on 13 of 16 rows. Mean p(call) on the reference's calling rows: 1.0 reference, 1.0 file.
- **lfm_3_1_7b_xnnpack_8da4w.pte lost 0 of 9 calls against its source** (0 on rows that need a tool), gained 3 (0 on rows that do not), and switched tool on 0. Same decision on 13 of 16 rows. Mean p(call) on the reference's calling rows: 1.0 reference, 1.0 file.

| Metric | reference | LFM3-1.7B-Q4_K_M.gguf | lfm_3_1_7b_xnnpack_8da4w.pte |
|---|---|---|---|
| Called when needed | 9/16 | 10/16 | 12/16 |
| Called when not needed | n/a | n/a | n/a |
| Called, either fine | n/a | n/a | n/a |
| Wrong tool | 0/9 | 0/10 | 0/12 |
| Bad arguments | 0/9 | 0/10 | 0/12 |
| Claimed use, no call | 0/16 | 0/16 | 0/16 |
| Malformed call | 0/16 | 0/16 | 0/16 |
| Hit token limit | 4/16 | 5/16 | 3/16 |
| Correct without a call | n/a | n/a | n/a |
| Mean p(call), needed | 0.75 | 0.909 | 0.923 |
| Mean p(call), not needed | None | None | None |
| Median s | 92.18 | 18.23 | 29.34 |

LFM3-1.7B-Q4_K_M.gguf, calls lost:

- `needs_tool` I'd like to have a digital painting created. The image should be a detailed portrait of a masked woman, including bright peacock feathers, with an elegant and h

LFM3-1.7B-Q4_K_M.gguf, calls gained:

- `needs_tool` Can you generate a digital image of a woman wearing a mask with bright peacock feathers around her? The style should be reminiscent of Alphonse Mucha's art nouv
- `needs_tool` I would like to buy a movie ticket in Concord on the Apr 9th for four people.

lfm_3_1_7b_xnnpack_8da4w.pte, calls gained:

- `needs_tool` Can you generate a digital image of a woman wearing a mask with bright peacock feathers around her? The style should be reminiscent of Alphonse Mucha's art nouv
- `needs_tool` Hi, could you get me a house to stay for 4 in London
- `needs_tool` I would like to buy a movie ticket in Concord on the Apr 9th for four people.

## openweights

- **LFM3-1.7B-Q4_K_M.gguf lost 0 of 15 calls against its source** (0 on rows that need a tool), gained 2 (0 on rows that do not), and switched tool on 0. Same decision on 32 of 34 rows. Mean p(call) on the reference's calling rows: 0.999 reference, 1.0 file.
- **lfm_3_1_7b_xnnpack_8da4w.pte lost 1 of 15 calls against its source** (1 on rows that need a tool), gained 2 (0 on rows that do not), and switched tool on 0. Same decision on 31 of 34 rows. Mean p(call) on the reference's calling rows: 0.999 reference, 0.936 file.

| Metric | reference | LFM3-1.7B-Q4_K_M.gguf | lfm_3_1_7b_xnnpack_8da4w.pte |
|---|---|---|---|
| Called when needed | 14/17 | 16/17 | 15/17 |
| Called when not needed | 1/17 | 1/17 | 1/17 |
| Called, either fine | n/a | n/a | n/a |
| Wrong tool | 0/14 | 0/16 | 0/15 |
| Bad arguments | 0/15 | 0/17 | 0/16 |
| Claimed use, no call | 0/34 | 0/34 | 1/34 |
| Malformed call | 0/34 | 0/34 | 0/34 |
| Hit token limit | 4/34 | 0/34 | 0/34 |
| Correct without a call | n/a | n/a | n/a |
| Mean p(call), needed | 0.999 | 0.941 | 0.884 |
| Mean p(call), not needed | 0.063 | 0.067 | 0.059 |
| Median s | 34.25 | 12.5 | 22.0 |

LFM3-1.7B-Q4_K_M.gguf, calls gained:

- `needs_tool` What's the weather forecast for Manila tomorrow?
- `needs_tool` Summarise this page for me: https://www.python.org/downloads/release/python-3130/

lfm_3_1_7b_xnnpack_8da4w.pte, calls lost:

- `needs_tool` Convert the file for me.

lfm_3_1_7b_xnnpack_8da4w.pte, calls gained:

- `needs_tool` What's the weather forecast for Manila tomorrow?
- `needs_tool` Summarise this page for me: https://www.python.org/downloads/release/python-3130/

## search

- **LFM3-1.7B-Q4_K_M.gguf lost 2 of 34 calls against its source** (0 on rows that need a tool), gained 1 (1 on rows that do not), and switched tool on 0. Same decision on 37 of 40 rows. Mean p(call) on the reference's calling rows: 1.0 reference, 0.97 file.
- **lfm_3_1_7b_xnnpack_8da4w.pte lost 0 of 34 calls against its source** (0 on rows that need a tool), gained 1 (0 on rows that do not), and switched tool on 0. Same decision on 39 of 40 rows. Mean p(call) on the reference's calling rows: 1.0 reference, 0.999 file.

| Metric | reference | LFM3-1.7B-Q4_K_M.gguf | lfm_3_1_7b_xnnpack_8da4w.pte |
|---|---|---|---|
| Called when needed | 19/19 | 19/19 | 19/19 |
| Called when not needed | 9/14 | 8/14 | 9/14 |
| Called, either fine | 6/7 | 6/7 | 7/7 |
| Wrong tool | 0/19 | 0/19 | 0/19 |
| Bad arguments | 0/34 | 0/33 | 0/35 |
| Claimed use, no call | 0/40 | 0/40 | 0/40 |
| Malformed call | 0/40 | 0/40 | 0/40 |
| Hit token limit | 1/40 | 2/40 | 0/40 |
| Correct without a call | 5/5 | 4/6 | 4/5 |
| Mean p(call), needed | 1.0 | 1.0 | 0.999 |
| Mean p(call), not needed | 0.643 | 0.615 | 0.642 |
| Median s | 51.77 | 7.99 | 11.55 |

LFM3-1.7B-Q4_K_M.gguf, calls lost:

- `no_tool` How long do NFL football teams have to get a play off (the play clock)?
- `no_tool` Who is Elrond's father in J. R. R. Tolkien's Middle Earth stories?

LFM3-1.7B-Q4_K_M.gguf, calls gained:

- `no_tool` What sport does 2009 Atlantic Coast Conference Baseball Tournament play?

lfm_3_1_7b_xnnpack_8da4w.pte, calls gained:

- `no_target` Which is the oldest still-running university in the world?

## Per tool

Needed: called that tool, of the rows that need it. Near miss: called anything, of the paired rows that need nothing. Unasked: calls to it on rows that wanted another tool or none.

| Tool | reference: needed | reference: near miss | reference: unasked | LFM3-1.7B-Q4_K_M.gguf: needed | LFM3-1.7B-Q4_K_M.gguf: near miss | LFM3-1.7B-Q4_K_M.gguf: unasked | lfm_3_1_7b_xnnpack_8da4w.pte: needed | lfm_3_1_7b_xnnpack_8da4w.pte: near miss | lfm_3_1_7b_xnnpack_8da4w.pte: unasked |
|---|---|---|---|---|---|---|---|---|---|
| advance | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 |
| ask_user | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 | 0/1 | 0/1 | 0 |
| delete_file | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 |
| fetch_url | 0/1 | 0/1 | 0 | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 |
| find_files | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 |
| forget_memory | 0/1 | 0/1 | 0 | 0/1 | 0/1 | 0 | 0/1 | 0/1 | 0 |
| read_file | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 |
| read_memory | 3/3 | 0/1 | 0 | 3/3 | 0/1 | 0 | 3/3 | 0/1 | 0 |
| run_script | 0/1 | 0/1 | 0 | 0/1 | 0/1 | 0 | 0/1 | 0/1 | 0 |
| save_memory | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 |
| show_document | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 |
| show_pictures | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 |
| show_slides | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 |
| show_website | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 |
| update_memory | 0/1 | 1/1 | 0 | 0/1 | 1/1 | 0 | 0/1 | 1/1 | 0 |
| web_search | 19/20 | 9/15 | 10 | 20/20 | 8/15 | 9 | 20/20 | 9/15 | 10 |
| write_file | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 | 1/1 | 0/1 | 0 |

p(call) is the probability of the call-opening token at the first reply token after any think block. Bad arguments: a call whose arguments fail the tool's JSON schema (unknown argument names included) or miss what the case requires. Correct is graded only on replies that answered without a call.
