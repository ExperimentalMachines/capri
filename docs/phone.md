# On the phone

The phone is where a file ships, so it is the only column that measures what a user gets. This
page records how a phone run is set up, how the first one was done on Qualcomm's device cloud,
and what it found. [`../README.md`](../README.md) has the metrics.

## What runs where

| Piece | Where | Why |
|---|---|---|
| The cases | exported on the laptop, answered on the phone | the phone renders the prompt with the app's own template |
| The reference model | laptop (Transformers) | it is the unquantised baseline; `--no-reference-run` drops it |
| The file | laptop (llama.cpp / ExecuTorch host) and phone (`--phone-model`) | a drop on the laptop points at the recipe, one only on the phone points at the runtime |
| Grading | laptop, on the rows the phone wrote | one grader for every engine; the phone's raw stream is re-parsed here |

capri itself never runs on the phone. What runs there is OpenWeights' `ToolDecisionEval`
instrumented test, reading `/data/local/tmp/openweights/eval/tde/cases.jsonl` and answering each
case with the app's engine, its sampler and the state it carries between conversations.

## One command

```bash
capri --reference LiquidAI/LFM3-1.7B --suite search --max-tokens 1024 \
  --phone-serial ac41dea9 --phone-apk engine-debug-androidTest.apk \
  --phone-model LFM3-1.7B-8da4w-gptq-4k.pte --no-reference-run
```

That exports the cases, pushes them with the file and the tokenizer, installs the APK, starts
the runner detached, polls until it stops, pulls `eval-results/tde/<model>.jsonl` and writes
`capri-out/report.md` with a `<model>@phone` column.

| Flag | What it does |
|---|---|
| `--phone-serial` | the adb device; required for a phone run, and the only flag that turns it on |
| `--phone-model` | a `.gguf` or `.pte` to push and answer on the phone (repeatable). A `.pte` brings `<stem>.tokenizer.json` with it; omit it to answer and grade what the device already holds |
| `--phone-apk` | the test APK to install first; omit it when the phone already has the build you want |
| `--adb` | the adb binary (default `$ADB`, then `adb`) |
| `--adb-host HOST:PORT` | an adb server you forwarded yourself |
| `--ssh USER@HOST` | capri opens `ssh -N -L <free port>:--ssh-remote` and closes it at the end, so nothing is left running |
| `--ssh-key`, `--ssh-remote`, `--ssh-port` | the private key, the far side's adbd (`127.0.0.1:5037`), and a local port if you want to pin one |
| `--phone-timeout`, `--phone-poll` | give up after N seconds (a rerun resumes), and how often to look at progress (default 20 s) |

`--file` stays on the laptop, so the one command can also hold the fp32 reference and the file's
laptop kernels beside the phone's. Export and grade with the same `--suite`, `--limit` and
`--max-tokens`, or grading stops on the rows the phone was never asked; change them and the
cases file changes, so the rows already on the phone are cleared and re-answered rather than
graded as if they answered today's question.

`--ssh` runs with `BatchMode=yes` and `StrictHostKeyChecking=accept-new`: a key that wants a
passphrase fails at once rather than waiting at a prompt nothing can answer, so unlock it in your
agent first, and a host key seen for the first time is trusted on sight.

## Building the APK

The runner lives on OpenWeights' `test/tool-decision-eval` branch, which carries the LFM3 engine
work; `main` does not have it.

```bash
cd openweights && git switch test/tool-decision-eval
./gradlew :core:engine:assembleDebugAndroidTest      # one Gradle build at a time
# core/engine/build/outputs/apk/androidTest/debug/engine-debug-androidTest.apk, 232 MB
```

It is installed with `pm install -r -t --user 0`, not `adb install`, because some ROMs refuse the
latter for a test-only APK.

## A device-cloud session (Qualcomm QDC)

The device is behind a jump host, and adb on its far side listens on 5037:

```bash
ssh -i qdc_id.pem -L 5038:sa991483.sa.svc.cluster.local:5037 -N sshtunnel@ssh.qdc.qualcomm.com
adb -H 127.0.0.1 -P 5038 devices -l          # ac41dea9  device  product:art model:Art_for_arm64
```

Reproduced by the flags instead:

```bash
capri ... --phone-serial ac41dea9 --ssh sshtunnel@ssh.qdc.qualcomm.com --ssh-key qdc_id.pem
```

- **Pick a local port that is free.** 5037 on the laptop is usually taken by the local adb
  server, and forwarding onto it makes `adb` talk to the wrong daemon. `--ssh` picks a free one;
  `-L 5038:...` by hand does the same.
- **Forward to the far side's adbd, not to a device serial.** The tunnel carries the adb server
  protocol; `adb -H 127.0.0.1 -P <port>` then sees the rack's phones as its own.
- **These sessions drop.** Three closes in under an hour on 2026-11-17, at 20:14, 20:57 and
  21:07, each mid-push or mid-run. A rerun resumes: the runner skips ids already in its results
  file, capri skips a model whose size is already on the device, and a run still going on the
  phone is waited for instead of started a second time. A supervisor loop
  (`while true; do ssh ...; sleep 3; done`) keeps a hand-run tunnel up across the drops.
- **"This account is not available"** on the command channel means the reservation has ended and
  the device is gone, even though the jump host still answers and still prints its banner. Pull
  the rows before the session is due to end; nothing on the device survives it.

## Grading after the fact

The rows are the measurement, so they are worth pulling and keeping:

```bash
adb -H 127.0.0.1 -P 5038 pull /sdcard/Android/data/io.github.alpharomercoma.openweights.core.engine.test/files/eval-results/tde/. capri-phone/results/
capri --reference LiquidAI/LFM3-1.7B --suite search --max-tokens 1024 --no-reference-run \
  --phone capri-phone/results/LFM3-1.7B-8da4w-gptq-4k.pte.jsonl
```

## First session: LFM3 1.7B 8da4w, 160 search cases

2026-11-17, QDC. Device `ac41dea9`: "Art for arm64", Qualcomm SM8975 (Snapdragon 8 Elite Gen 5),
Android 17, 43 GB free. APK from `test/tool-decision-eval`; file `LFM3-1.7B-8da4w-gptq-4k.pte`
(1.24 GB) with its `tokenizer.json`. The 160 `search` cases (75 `needs_tool`, 60 `no_tool`, 25
`no_target`), greedy, thinking on, at most 1,024 new tokens each. Rows and report:
[`../runs/lfm3-phone-160/`](../runs/lfm3-phone-160/).

| Metric | Phone, 8da4w `.pte` |
|---|---|
| Called when needed | 74/75 |
| Called when not needed | 39/60 |
| Called, either fine | 22/25 |
| Wrong tool / bad arguments | 0/74, 0/135 |
| Claimed use, no call / malformed | 0/160, 0/160 |
| Hit token limit | 2/160 |
| Correct without a call | 19/23 |
| Median per case | 10.3 s (p90 24 s, max 33 s) |

- **The over-searching is the model's, not the phone's.** 39 of 60 questions it could answer
  from memory still went to `web_search` (65%). The fp32 reference over a 40-row sample of the
  same suite did the same thing (9 of 14, 64%), so the export and the phone's kernels add
  nothing here. This answers the question the README left open: the phone's "52 to 55 of 60"
  was not the compiled file's doing.
- **Nothing looked damaged.** No wrong tools, no bad arguments, no claimed-but-skipped calls, no
  malformed calls. When it did answer without searching it was right 19 of 23 times.
- **The one missed needed case** was FreshQA "What season is it in the northern hemisphere?",
  answered from memory in 377 tokens — defensible, but graded as a lost call by the label.
- **Both truncations were `no_tool` rows**, so the token limit cost nothing in the counts. 1,024
  is a fine setting for this model on this prompt; 2 rows reached it in 300-token-average replies.

Timing and transport, for planning the next one: the 160 cases took 33 minutes of answering,
about 7 cases a minute early on and slower as the think blocks grew. Pushing cost 45 s for the 232 MB
APK (4.9 MB/s) and 122 s for the 1.24 GB `.pte` (9.7 MB/s) through the tunnel; the pull was 2 s.
Mean 556 prompt tokens and 300 new tokens per case, and `cached_tokens` was 0 on all 160: a hybrid
model cannot roll back its cache, so every case paid a full prefill.

## Pitfalls this session found

- The local adb server on 5037 fights a tunnel forwarded onto 5037 (see above).
- A dozing phone runs two to five times slower: wake it and `svc power stayon true`, which capri
  does before starting the runner.
- Files left in `tde/` from an earlier session get answered again by the runner. capri passes
  `-e model <name>` when it pushes a single file, so stale columns cannot appear in the report.
- The phone reports no p(call): its engine streams only the chosen token's log-probability, so
  the sharper laptop signal is absent and the counts carry the finding.
- Detect `MAX_TOKENS` in the report before reading anything into a lost call: a cut-off reply is
  not a decision against searching.
