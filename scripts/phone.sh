#!/bin/sh
# Run exported cases on an Android phone through OpenWeights' own engines, and pull the rows.
#
#   capri --reference R --suite all --limit 40 --max-tokens 1024 --phone-export capri-phone
#   scripts/phone.sh <adb-serial> <engine-debug-androidTest.apk> capri-phone model.gguf model.pte ...
#   capri --reference R --file model.gguf ... --phone capri-phone/results/model.gguf.jsonl
#
# A .pte needs its tokenizer beside it as <stem>.tokenizer.json. The APK is OpenWeights'
# core/engine test APK with ToolDecisionEval in it. Install is by push and pm install, which
# also works on ROMs that refuse adb install. The run is started detached and polled, so a
# dropped wireless session does not kill it; rerunning resumes where the rows stop.
set -eu
SERIAL=$1; APK=$2; CASES=$3; shift 3
ADB="${ADB:-adb} -s $SERIAL"
PKG=io.github.alpharomercoma.openweights.core.engine.test
DIR=/data/local/tmp/openweights/eval/tde
$ADB shell mkdir -p $DIR
$ADB push "$CASES/cases.jsonl" $DIR/cases.jsonl >/dev/null
for m in "$@"; do
  name=$(basename "$m")
  $ADB shell "[ -f $DIR/$name ]" 2>/dev/null || $ADB push "$m" "$DIR/$name"
  tok="${m%.*}.tokenizer.json"
  [ -f "$tok" ] && $ADB push "$tok" "$DIR/$(basename "$tok")" >/dev/null
done
$ADB push "$APK" /data/local/tmp/tde-test.apk >/dev/null
$ADB shell pm install -r -t --user 0 /data/local/tmp/tde-test.apk
# A dozing phone runs two to five times slower; keep it awake and unlocked for the run.
$ADB shell "input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard" >/dev/null 2>&1 || true
$ADB shell "nohup am instrument -r -e class io.github.alpharomercoma.openweights.core.engine.eval.ToolDecisionEval \
  $PKG/androidx.test.runner.AndroidJUnitRunner >/data/local/tmp/tde.log 2>&1 &"
n=0; until $ADB shell pidof $PKG >/dev/null 2>&1 || [ $n -ge 12 ]; do sleep 5; n=$((n + 1)); done
while $ADB shell pidof $PKG >/dev/null 2>&1; do sleep 30; done
$ADB shell "grep -E 'INSTRUMENTATION_(RESULT|STATUS: stack)|AssumptionViolated' /data/local/tmp/tde.log | head -3" || true
mkdir -p "$CASES/results"
$ADB pull /sdcard/Android/data/$PKG/files/eval-results/tde/. "$CASES/results/" >/dev/null
ls "$CASES/results"
