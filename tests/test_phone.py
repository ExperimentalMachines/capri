import json, os, shutil, subprocess, sys, time
from pathlib import Path

import pytest

from capri import phone

FAKE = Path(__file__).parent / "fake"


@pytest.fixture
def adb_state(tmp_path, monkeypatch):
    state = tmp_path / "state"
    (state / "rows").mkdir(parents=True)
    monkeypatch.setenv("FAKE_ADB_STATE", str(state))
    return state


def rows(state, model, ids):
    (state / "rows" / f"{model}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in [
        {"id": i, "raw": "<tool_call><function=web_search><parameter=query>x</parameter></function></tool_call>",
         "content": "", "app_calls": [{"name": "web_search", "arguments": "{\"query\": \"x\"}"}],
         "stop": "END_OF_TURN", "prompt_tokens": 600, "cached_tokens": 0, "new_tokens": 40, "seconds": 3.0}
        for i in ids]))


def test_adb_argv_and_devices(adb_state):
    a = phone.Adb(serial="s1", host="127.0.0.1", port=5038, binary=str(FAKE / "adb"))
    assert a.argv("shell", "ls")[:9] == [str(FAKE / "adb"), "-H", "127.0.0.1", "-P", "5038", "-s", "s1", "shell", "ls"]
    assert a.devices() == ["fake1"]
    assert phone.Adb(binary=str(FAKE / "adb")).serial_or_only() == "fake1"


def test_two_devices_must_be_named(adb_state, monkeypatch):
    (adb_state / "calls.log").write_text("")
    a = phone.Adb(binary=str(FAKE / "adb"))
    monkeypatch.setattr(phone.Adb, "devices", lambda self: ["a", "b"])
    with pytest.raises(RuntimeError, match="want one device"):
        a.serial_or_only()


def test_run_pushes_installs_answers_and_pulls(adb_state, tmp_path):
    cases = tmp_path / "cases"
    cases.mkdir()
    ids = ["search/a", "search/b"]
    (cases / "cases.jsonl").write_text("".join(json.dumps({"id": i}) + "\n" for i in ids))
    model = tmp_path / "LFM3-1.7B-8da4w-gptq-4k.pte"
    model.write_bytes(b"x" * 10)
    model.with_suffix(".tokenizer.json").write_text("{}")
    apk = tmp_path / "engine-debug-androidTest.apk"
    apk.write_bytes(b"apk")
    rows(adb_state, model.name, ids)

    logs = []
    got = phone.run(phone.Adb(binary=str(FAKE / "adb")), cases, apk=apk, models=[model], interval=0, log=logs.append)

    assert got == {model.name: cases / "results" / f"{model.name}.jsonl"}
    assert [json.loads(l)["id"] for l in got[model.name].read_text().splitlines()] == ids
    calls = (adb_state / "calls.log").read_text()
    assert "push" in calls and "pm install -r -t --user 0" in calls and "pull" in calls
    instrument = (adb_state / "instrument.txt").read_text()
    assert phone.KLASS in instrument and f"-e model {model.name}" in instrument
    assert (adb_state / "pushed" / "LFM3-1.7B-8da4w-gptq-4k.tokenizer.json").exists()
    assert any("rows," in line for line in logs if line.strip())


def test_run_says_so_when_a_file_wrote_no_rows(adb_state, tmp_path):
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "cases.jsonl").write_text(json.dumps({"id": "search/a"}) + "\n")
    model = tmp_path / "m.gguf"
    model.write_bytes(b"x")
    logs = []
    assert phone.run(phone.Adb(binary=str(FAKE / "adb")), cases, models=[model], interval=0, log=logs.append) == {}
    assert any("no rows written" in line for line in logs)


def test_no_model_grades_what_the_device_already_has(adb_state, tmp_path):
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "cases.jsonl").write_text(json.dumps({"id": "search/a"}) + "\n")
    rows(adb_state, "m.gguf", ["search/a"])
    logs = []
    got = phone.run(phone.Adb(binary=str(FAKE / "adb")), cases, interval=0, log=logs.append)
    assert list(got) == ["m.gguf"]
    assert any("already holds m.gguf" in line for line in logs)
    calls = (adb_state / "calls.log").read_text().splitlines()
    assert not any(" push " in c and "m.gguf" in c for c in calls)  # nothing new pushed, just answered


def _cases(tmp_path, ids=("search/a",)):
    cases = tmp_path / "cases"
    cases.mkdir()
    (cases / "cases.jsonl").write_text("".join(json.dumps({"id": i}) + "\n" for i in ids))
    return cases


def test_a_run_that_finishes_before_the_first_look_is_not_a_start_failure(adb_state, tmp_path, monkeypatch):
    """A resumed rerun answers nothing and exits at once; the earlier rows are the answer."""
    cases = _cases(tmp_path)
    model = tmp_path / "m.gguf"
    model.write_bytes(b"x")
    rows(adb_state, model.name, ["search/a"])
    monkeypatch.setenv("FAKE_ADB_POLLS", "0")  # already finished by the time anyone looks
    pulled = phone.run(phone.Adb(binary=str(FAKE / "adb")), cases, models=[model], interval=0, log=lambda *_: None)
    assert pulled and pulled[model.name].exists()


def test_a_run_already_on_the_phone_is_waited_for_not_started_twice(adb_state, tmp_path):
    cases = _cases(tmp_path)
    model = tmp_path / "m.gguf"
    model.write_bytes(b"x")
    rows(adb_state, model.name, ["search/a"])
    (adb_state / "instrument.txt").write_text("nohup am instrument -r -e class earlier")
    (adb_state / "launched").touch()
    (adb_state / "polls").write_text("0")
    logs = []
    phone.run(phone.Adb(binary=str(FAKE / "adb")), cases, models=[model], interval=0, log=logs.append)
    assert (adb_state / "instrument.txt").read_text() == "nohup am instrument -r -e class earlier"
    assert any("already going" in line for line in logs)


def test_changed_cases_clear_rows_answered_under_the_old_ones(adb_state, tmp_path):
    cases = _cases(tmp_path)
    model = tmp_path / "m.gguf"
    model.write_bytes(b"x")
    rows(adb_state, model.name, ["search/a"])
    (adb_state / "stamp").write_text("a-stamp-from-an-older-settings-set")
    logs = []
    pulled = phone.run(phone.Adb(binary=str(FAKE / "adb")), cases, models=[model], interval=0, log=logs.append)
    assert any("clearing them" in line for line in logs)
    assert pulled == {}  # the old rows are gone, so nothing is graded against today's cases


def test_a_file_already_on_the_phone_is_not_pushed_again(adb_state, tmp_path, monkeypatch):
    cases = _cases(tmp_path)
    model = tmp_path / "m.gguf"
    model.write_bytes(b"0123456789")
    rows(adb_state, model.name, ["search/a"])
    monkeypatch.setenv("FAKE_ADB_SIZES", json.dumps({model.name: 10}))
    phone.run(phone.Adb(binary=str(FAKE / "adb")), cases, models=[model], interval=0, log=lambda *_: None)
    calls = (adb_state / "calls.log").read_text().splitlines()
    assert not any(" push " in c and model.name in c for c in calls)


def test_tunnel_forwards_and_is_killed(tmp_path, monkeypatch):
    log = tmp_path / "ssh.log"
    monkeypatch.setenv("FAKE_SSH_LOG", str(log))
    with phone.tunnel("user@host", key="~/.ssh/qdc.pem", binary=str(FAKE / "ssh"), log=lambda *_: None) as port:
        assert port > 0
        assert subprocess.run([sys.executable, "-c",
                               f"import socket;socket.create_connection(('127.0.0.1',{port}),1)"]).returncode == 0
    argv = log.read_text()
    assert "-N" in argv and "-i /Users" in argv.replace(str(Path.home()), "/Users")
    assert f"-L {port}:" in argv
    time.sleep(0.3)
    assert not _listening(port)


def test_tunnel_reports_a_refused_session(tmp_path):
    with pytest.raises(RuntimeError, match="ssh exited"):
        with phone.tunnel("user@host", binary=str(FAKE / "ssh-fail"), log=lambda *_: None):
            pass


def test_tunnel_fails_when_the_port_never_opens(tmp_path, monkeypatch):
    silent = tmp_path / "ssh-silent"
    silent.write_text("#!/bin/sh\nsleep 30\n")
    silent.chmod(0o755)
    with pytest.raises(RuntimeError, match="did not open port"):
        with phone.tunnel("user@host", binary=str(silent), wait=1, log=lambda *_: None):
            pass


def test_pulled_rows_become_a_graded_phone_column(tmp_path, adb_state):
    from capri import cli, grade, suites
    questions = suites.load("search", 4)
    ids = [q["id"] for q in questions]
    assert {q["label"] for q in questions} <= set(grade.LABELS)
    rows(adb_state, "m.pte", ids)
    pulled = tmp_path / "results"
    pulled.mkdir()
    shutil.copy(adb_state / "rows" / "m.pte.jsonl", pulled / "m.pte.jsonl")
    engine = cli.phone_rows(pulled / "m.pte.jsonl", questions)
    summary = grade.summarize(questions, engine)
    assert summary["rows"] == 4
    assert summary["malformed_calls"] == "0/4" and summary["mean_p_call_needs_tool"] is None
    assert all(engine[i]["calls"][0]["name"] == "web_search" for i in ids)


def test_ids_in_reads_both_json_spacings(tmp_path):
    rowsfile = tmp_path / "m.pte.jsonl"
    rowsfile.write_text('{"id":"a"}\n{"id": "b"}\nnot json\n')
    assert phone._ids_in(rowsfile) == {"a", "b"}


def _listening(port):
    import socket
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) == 0
