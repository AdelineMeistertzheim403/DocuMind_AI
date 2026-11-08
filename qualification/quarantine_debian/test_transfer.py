"""Transfer-tool checks, deliberately separate from the 42-case campaign."""
import hashlib
import importlib.util
from pathlib import Path
import sys
import zipfile

import pytest


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from verify_transfer import extract_archive, verify_manifest


def inventory(root):
    source = root / "payload.txt"
    source.write_bytes(b"synthetic")
    (root / "SHA256SUMS").write_text(
        hashlib.sha256(source.read_bytes()).hexdigest() + "  payload.txt\n",
        encoding="ascii",
    )
    return source


@pytest.mark.parametrize("change", ["missing", "extra", "modified"])
def test_inventory_refuses_any_file_drift(tmp_path, change):
    source = inventory(tmp_path)
    assert verify_manifest(tmp_path)
    if change == "missing":
        source.unlink()
    elif change == "extra":
        (tmp_path / "unlisted.txt").write_text("extra")
    else:
        source.write_bytes(b"modified")
    with pytest.raises(RuntimeError, match="mismatch"):
        verify_manifest(tmp_path)


@pytest.mark.parametrize("name", ["../outside.txt", "/absolute.txt", "a\\escape.txt", "line\nbreak.txt"])
def test_zip_refuses_unsafe_members_before_extraction(tmp_path, name):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as stream:
        entry = zipfile.ZipInfo()
        entry.filename = name
        stream.writestr(entry, "synthetic")
    destination = tmp_path / "extracted"
    with pytest.raises(RuntimeError, match="Unsafe"):
        extract_archive(archive, destination)
    assert not destination.exists()


@pytest.mark.parametrize("outcome", ["skipped", "failure", "error", "missing"])
def test_junit_refuses_nonpassing_or_missing_cases(tmp_path, outcome):
    spec = importlib.util.spec_from_file_location("quarantine_runner_checks", HERE / "run_campaign.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    path = tmp_path / "junit.xml"
    cases = ['<testcase name="case-%d"/>' % i for i in range(42)]
    path.write_text('<testsuite tests="42">' + "".join(cases) + "</testsuite>")
    runner.validate_junit(path)
    if outcome == "missing":
        cases.pop()
    else:
        cases[0] = '<testcase name="bad"><%s/></testcase>' % outcome
    path.write_text('<testsuite tests="42">' + "".join(cases) + "</testsuite>")
    with pytest.raises(RuntimeError, match="42"):
        runner.validate_junit(path)
