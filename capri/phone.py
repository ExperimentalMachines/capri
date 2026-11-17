"""The phone: OpenWeights' ToolDecisionEval, driven over adb, optionally through an SSH tunnel.

A phone run has four moving parts, and only one of them is on the phone:

  1. the cases (this tool's export: `messages`, `tools`, `max_tokens`, `thinking`),
  2. OpenWeights' `engine-debug-androidTest.apk`, whose `ToolDecisionEval` answers them with the
     app's own template, its own engines and the state it carries from one conversation to the next,
  3. adb, which is often a server on another machine, reached through `ssh -L local:remote:5037`
     (Qualcomm's device cloud, a lab rack, a phone plugged into a colleague's laptop),
  4. the grading, which happens back here, on the rows the phone wrote.

`tunnel` opens the third for you and `run` does the pushing and polling, because every one of
those steps is a command a developer would otherwise retype, in the wrong order, from a shell
that dies when the wireless session drops. The runner is started detached and writes a row as
each case lands, so a dropped connection costs one case and a rerun resumes where it stopped.
"""
import hashlib, json, os, shlex, socket, subprocess, tempfile, time
from contextlib import contextmanager
from pathlib import Path

PKG = "io.github.alpharomercoma.openweights.core.engine.test"
KLASS = "io.github.alpharomercoma.openweights.core.engine.eval.ToolDecisionEval"
RUNNER = f"{PKG}/androidx.test.runner.AndroidJUnitRunner"
DIR = "/data/local/tmp/openweights/eval/tde"  # what the test reads; see ToolDecisionEval.DIR
APK = "/data/local/tmp/capri-phone.apk"
LOG = "/data/local/tmp/capri-phone.log"
STAMP = f"{DIR}/.capri-stamp"  # which cases and settings the rows on the phone came from
RESULTS = f"/sdcard/Android/data/{PKG}/files/eval-results/tde"


class Adb:
    """One adb command line, wherever its server is: `ADB=adb`, `--adb-host host:port`, `-s serial`."""

    def __init__(self, serial=None, host=None, port=None, binary=None):
        self.binary = binary or os.environ.get("ADB") or "adb"
        self.host, self.port = (host, port) if host else (None, None)
        self.serial = serial

    def argv(self, *args):
        a = [self.binary]
        if self.host:
            a += ["-H", self.host, "-P", str(self.port or 5037)]
        if self.serial:
            a += ["-s", self.serial]
        return a + [str(x) for x in args]

    def run(self, *args, check=True, timeout=None):
        p = subprocess.run(self.argv(*args), capture_output=True, text=True, timeout=timeout)
        if check and p.returncode != 0:
            raise RuntimeError(f"{' '.join(self.argv(*args))}: {p.returncode}\n{(p.stderr or p.stdout).strip()}")
        return p

    def shell(self, command, check=True, timeout=None):
        return self.run("shell", command, check=check, timeout=timeout).stdout.strip()

    def devices(self):
        """The online serials, so a run with one phone need not name it."""
        out = self.run("devices").stdout.splitlines()[1:]
        return [line.split("\t")[0].strip() for line in out if "\tdevice" in line]

    def serial_or_only(self):
        if self.serial:
            return self.serial
        found = self.devices()
        if len(found) == 1:
            return found[0]
        raise RuntimeError(f"want one device, found {found or 'none'}: pass --phone-serial")

    def push(self, local, remote, log=print):
        size = Path(local).stat().st_size
        log(f"  push {Path(local).name} ({size / 1e6:,.0f} MB)")
        self.run("push", local, remote, timeout=None)

    def pull(self, remote, local, check=True):
        self.run("pull", remote, local, check=check)


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _tail(handle, chars=400):
    handle.seek(0)
    return handle.read().strip()[-chars:]


@contextmanager
def tunnel(target, key=None, local_port=None, remote="127.0.0.1:5037", binary="ssh", wait=30, log=print):
    """`ssh -N -L` to a machine that serves adb, and yield the local port it forwards to.

    The local port is chosen free unless you name one, so this never fights an adb server already
    listening on 5037 on your laptop. `BatchMode` is on: a key that wants a passphrase fails here
    with a message instead of sitting at a prompt nothing can answer. Nothing is left running on
    the way out.
    """
    port = local_port or free_port()
    cmd = [binary, "-o", "ExitOnForwardFailure=yes", "-o", "StrictHostKeyChecking=accept-new",
           "-o", "ServerAliveInterval=15", "-o", "ServerAliveCountMax=3", "-o", "TCPKeepAlive=yes",
           "-o", "BatchMode=yes", "-o", "ConnectTimeout=20"]
    if key:
        cmd += ["-i", str(Path(key).expanduser())]
    cmd += ["-N", "-L", f"{port}:{remote}", target]
    log(f"tunnel 127.0.0.1:{port} -> {target} {remote}")
    # ssh talks to a file, not a pipe: a long session that prints per-channel failures would
    # otherwise fill the pipe nobody drains and wedge the forward.
    err = tempfile.TemporaryFile(mode="w+")
    proc = subprocess.Popen(cmd, stdout=err, stderr=subprocess.STDOUT, text=True)
    try:
        deadline = time.time() + wait
        while True:
            if proc.poll() is not None:
                raise RuntimeError(f"ssh exited {proc.returncode}: {_tail(err)}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=1):
                    break
            except OSError:
                if time.time() > deadline:
                    raise RuntimeError(f"ssh -L {port}:{remote} {target} did not open port {port} in {wait}s: "
                                       f"{_tail(err)}")
                time.sleep(0.3)
        yield port
    finally:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(5)
        err.close()


def run(adb, cases, apk=None, models=(), timeout=None, interval=20, log=print):
    """Push the cases and the files, install, answer every case, pull the rows. Returns {name: rowfile}.

    `cases` is the folder `--phone-export` wrote (its `cases.jsonl` is what the test reads).
    A model is pushed only when the phone's copy differs in size, and a case already in the
    results file is skipped on the phone, so this can be rerun after any interruption. A run
    already going on the phone is waited for rather than started twice. With no `models`,
    whatever the device already holds is answered and graded.
    """
    cases = Path(cases)
    adb.serial = adb.serial_or_only()
    models = [Path(m) for m in models]
    names = [m.name for m in models]
    dup = sorted({n for n in names if names.count(n) > 1})
    if dup:
        raise RuntimeError(f"two files named {dup[0]} would overwrite each other on the device")
    stamp = hashlib.sha1((cases / "cases.jsonl").read_bytes()).hexdigest()
    adb.shell(f"mkdir -p {DIR}")
    adb.push(cases / "cases.jsonl", f"{DIR}/cases.jsonl", log=log)
    # The ids alone do not say which settings answered them, and a case id is the same at 384
    # tokens as at 1024. A different cases.jsonl means the rows on the phone answer a different
    # question, so they go.
    was = adb.shell(f"cat {STAMP} 2>/dev/null || true").strip()
    if was and was != stamp:
        log("  the cases or settings changed since the rows on the phone: clearing them")
        adb.shell(f"rm -f {shlex.quote(RESULTS)}/*.jsonl", check=False)
    adb.shell(f"echo {stamp} > {STAMP}")
    for model in models:
        remote = f"{DIR}/{model.name}"
        size = adb.shell(f"stat -c %s {shlex.quote(remote)} 2>/dev/null || echo 0").strip()
        if size != str(model.stat().st_size):
            adb.push(model, remote, log=log)
        tokenizer = model.with_suffix(".tokenizer.json") if model.suffix == ".pte" else None
        if tokenizer and tokenizer.exists():
            adb.push(tokenizer, f"{DIR}/{tokenizer.name}", log=log)
    if not models:  # nothing new to push: grade what the device already holds, and say what that is
        found = adb.shell(f'ls -1 {DIR} 2>/dev/null | grep -E "[.](gguf|pte)$" || true').split()
        log(f"no --phone-model: the device already holds {', '.join(found) or 'nothing'}")
        names = found
        models = [Path(DIR) / n for n in found]  # only their names are read below
    if not names:
        raise RuntimeError(f"no .gguf or .pte on the device in {DIR}: pass --phone-model")
    if apk:
        adb.push(apk, APK, log=log)
        log(f"  install {Path(apk).name}")
        out = adb.shell(f"pm install -r -t --user 0 {APK}")
        if "Success" not in out:
            raise RuntimeError(f"pm install: {out}")

    poll = max(60, interval * 3)  # a half-open tunnel must not hang the loop past --phone-timeout

    def running():
        return bool(adb.shell(f"pidof {PKG} 2>/dev/null || true", timeout=poll))

    def ended():
        return adb.shell(f"grep -c INSTRUMENTATION_CODE {LOG} 2>/dev/null || true", timeout=poll).strip() not in ("", "0")

    # A dozing phone runs two to five times slower, and the run is long: keep the screen on.
    adb.shell("input keyevent KEYCODE_WAKEUP; wm dismiss-keyguard; svc power stayon true", check=False, timeout=poll)
    if running():
        log("a run is already going on the phone: waiting for it, nothing new is started")
    else:
        log(f"run     {len(names)} file(s) over {len(_case_ids(cases))} cases")
        # One file is named for the runner, so a stale .gguf or .pte left in DIR from an earlier
        # session is not answered again and does not land in the report as a column nobody asked for.
        only = f" -e model {shlex.quote(names[0])}" if len(names) == 1 else ""
        adb.shell(f": > {LOG}", check=False, timeout=poll)  # a stale log must not pass for this run's
        adb.shell(f"nohup am instrument -r -e class {KLASS}{only} {RUNNER} >{LOG} 2>&1 &", timeout=poll)
        # A resumed rerun can answer every case and exit before the first look; that is a finished
        # run, not one that never started.
        deadline = time.time() + 60
        while not running():
            if ended():
                break
            if time.time() > deadline:
                raise RuntimeError(f"the runner never started; {LOG}:\n" + adb.shell(f"tail -20 {LOG}", check=False))
            time.sleep(5)

    counts, t0, until = {n: 0 for n in names}, time.time(), timeout and time.time() + timeout
    while running():
        time.sleep(interval)
        if until and time.time() > until:
            raise RuntimeError(f"still running after {timeout}s; rerun to resume from where it stopped")
        for n in names:
            now = _rows(adb, n, poll)
            if now != counts[n]:
                counts[n] = now
                log(f"  {n}: {now} rows, {time.time() - t0:,.0f}s")

    time.sleep(2)  # the last row lands just before the process goes away, not after
    results = cases / "results"
    results.mkdir(parents=True, exist_ok=True)
    adb.pull(f"{RESULTS}/.", str(results) + "/", check=False)  # a runner that wrote nothing is reported below
    wanted = set(_case_ids(cases))
    pulled = {}
    for n in names:
        path = results / f"{n}.jsonl"
        if not path.exists():
            log(f"  {n}: no rows written; {LOG}:\n" + adb.shell(f"tail -20 {LOG}", check=False, timeout=poll))
            continue
        have = _ids_in(path)
        if wanted - have:
            log(f"  {n}: {len(have)}/{len(wanted)} cases (rerun the same command to resume the rest)")
        pulled[n] = path
    return pulled


def _rows(adb, name, timeout=None):
    out = adb.shell(f"wc -l {shlex.quote(f'{RESULTS}/{name}.jsonl')} 2>/dev/null || true", timeout=timeout)
    return int(out.split()[0]) if out.split() and out.split()[0].isdigit() else 0


def _case_ids(cases):
    return [json.loads(l)["id"] for l in (Path(cases) / "cases.jsonl").read_text().splitlines() if l.strip()]


def _ids_in(path):
    """The ids a rows file already holds, read as JSON: the phone writes no space after the colon."""
    ids = set()
    for line in Path(path).read_text().splitlines():
        try:
            ids.add(json.loads(line)["id"])
        except (ValueError, KeyError, TypeError):
            pass
    return ids
