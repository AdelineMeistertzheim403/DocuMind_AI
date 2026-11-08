"""Focused launcher checks; no backend import and no real forbidden operation."""
import importlib.util
import os
from pathlib import Path
import sys

import pytest


SPEC = importlib.util.spec_from_file_location(
    "restored_launcher_checks", Path(__file__).with_name("run_campaign.py"),
)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


@pytest.mark.parametrize("event,args", [
    ("socket.__new__", ()),
    ("socket.getaddrinfo", ()),
    ("sqlite3.connect", ()),
    ("subprocess.Popen", ()),
    ("smtplib.connect", ()),
    ("open", ("outside.txt", "w", os.O_WRONLY)),
    ("open", (".env", "r", os.O_RDONLY)),
    ("os.mkdir", ("outside", 0o700, -1)),
    ("os.rename", ("outside.txt", "elsewhere.txt", -1, -1)),
    ("os.symlink", ("source", "target", -1)),
])
def test_audit_denial_is_persistent_even_if_caught(tmp_path, monkeypatch, event, args):
    hooks, violations = [], []
    monkeypatch.setattr(sys, "addaudithook", hooks.append)
    runner.install_audit((tmp_path,), violations, {}, set())
    with pytest.raises(RuntimeError, match="Forbidden I/O"):
        hooks[0](event, args)
    assert len(violations) == 1


def test_audit_allows_scratch_but_not_restored_directory(tmp_path, monkeypatch):
    hooks, violations = [], []
    monkeypatch.setattr(sys, "addaudithook", hooks.append)
    scratch = tmp_path / "scratch"
    runner.install_audit((scratch,), violations, {}, set())
    hooks[0]("open", (str(scratch / "allowed"), "w", os.O_WRONLY))
    with pytest.raises(RuntimeError, match="write_outside"):
        hooks[0]("open", (str(tmp_path / "recovery-state.json"), "w", os.O_TRUNC))
    assert not (tmp_path / "recovery-state.json").exists()


@pytest.mark.parametrize("outcome", ["skipped", "failure", "error", "missing"])
def test_junit_rejects_unsuccessful_or_incomplete_runs(tmp_path, outcome):
    path = tmp_path / "junit.xml"
    cases = ['<testcase name="case-%d"/>' % i for i in range(9)]
    path.write_text('<testsuite tests="9">' + "".join(cases) + "</testsuite>")
    runner.validate_junit(path)
    if outcome == "missing":
        cases.pop()
    else:
        cases[0] = '<testcase name="bad"><%s/></testcase>' % outcome
    path.write_text('<testsuite tests="9">' + "".join(cases) + "</testsuite>")
    with pytest.raises(RuntimeError, match="JUnit"):
        runner.validate_junit(path)
