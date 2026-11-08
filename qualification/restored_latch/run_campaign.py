"""Read-only restored-latch qualification. No server, sockets or external services."""
import argparse
import ast
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import platform
import stat
import sys
import traceback
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TEST = "tests/test_recovery_quarantine_restored_latch.py"
EXPECTED_SHA256 = "0a01b17bf9de4fe0d4eccdbae2da89f3345c261622bb8f11a2777c2f53229565"
TARGET_LATCH = Path(
    "/home/adeline/docnelo-lab/artifacts/qualification/capture-v51/"
    "roundtrip-restore/files/recovery-state.json"
)
EVIDENCE_BASE = Path(
    "/home/adeline/docnelo-lab/development/v5.1-hardening/quarantine-debian-evidence"
)
COUNT = 9


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def latch_snapshot(path):
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise RuntimeError("Latch must be an absolute path without symlinks")
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > 1024:
        raise RuntimeError("Latch must be a bounded regular file")
    if os.name == "posix" and stat.S_IMODE(metadata.st_mode) != 0o600:
        raise RuntimeError("POSIX latch permissions must be exactly 0600")
    return {
        "sha256": digest(path), "mode": stat.S_IMODE(metadata.st_mode),
        "size": metadata.st_size, "mtime_ns": metadata.st_mtime_ns,
        "inode": metadata.st_ino, "device": metadata.st_dev,
    }


def new_output(path):
    if not path.is_absolute() or any(p.is_symlink() for p in (path, *path.parents)):
        raise RuntimeError("Output must be absolute and without symlinks")
    path = path.resolve()
    if path.exists() or path.is_relative_to(ROOT) or any(
        p.lower() in {"release", "releases", "fixtures", "artifacts"} for p in path.parts
    ):
        raise RuntimeError("Output must be new and outside protected/source directories")
    if not path.parent.is_dir():
        raise RuntimeError("Output parent must already exist")
    return path


def install_audit(allowed_writes, violations, inventory, executed):
    def deny(label):
        violations.append(label)
        raise RuntimeError("Forbidden I/O: " + label)

    def writable(value, dir_fd=None):
        if dir_fd not in (None, -1) or isinstance(value, int):
            deny("unresolved_write_descriptor")
        path = Path(os.fsdecode(value))
        if any(p.is_symlink() for p in (path.absolute(), *path.absolute().parents)):
            deny("symlink_write")
        path = path.resolve()
        if not any(path == root or path.is_relative_to(root) for root in allowed_writes):
            deny("write_outside_evidence_or_scratch:" + str(path))

    def audit(event, arguments):
        if event.startswith("socket.") or event in {
            "subprocess.Popen", "os.system", "os.fork", "os.forkpty",
            "os.posix_spawn", "sqlite3.connect", "smtplib.connect",
            "http.client.connect", "urllib.Request",
        }:
            deny(event)
        if event == "open":
            value, mode, flags = arguments
            if not isinstance(value, int) and Path(os.fsdecode(value)).name.startswith(".env"):
                deny("dotenv_read")
            if (isinstance(mode, str) and any(c in mode for c in "wax+")) or flags & (
                os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
            ):
                writable(value)
        if event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.chown", "os.utime"}:
            writable(arguments[0], arguments[-1])
        if event in {"os.rename", "os.link"}:
            writable(arguments[0], arguments[2])
            writable(arguments[1], arguments[3])
        if event in {"os.symlink", "os.truncate"}:
            deny(event)
        if event == "exec":
            filename = arguments[0].co_filename
            if not filename.startswith("<"):
                path = Path(filename).resolve()
                if (
                    path.is_relative_to(ROOT) and path.suffix == ".py"
                    and not path.is_relative_to(Path(sys.prefix).resolve())
                ):
                    name = path.relative_to(ROOT).as_posix()
                    if name not in inventory:
                        deny("uninventoried_source:" + name)
                    executed.add(name)

    sys.addaudithook(audit)


def validate_junit(path):
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    suites = list(root.iter("testsuite"))
    if len(cases) != COUNT or not suites or sum(int(s.get("tests", 0)) for s in suites) != COUNT:
        raise RuntimeError("JUnit must contain exactly nine cases")
    if any(list(case.iter(tag)) for case in cases for tag in ("failure", "error", "skipped")):
        raise RuntimeError("JUnit must contain only successful non-skipped cases")
    if any(int(s.get(field, 0)) for s in suites for field in ("failures", "errors", "skipped")):
        raise RuntimeError("JUnit suite contains unsuccessful outcomes")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--latch-path", type=Path)
    parser.add_argument("--expected-sha256", default=EXPECTED_SHA256)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--preparation", action="store_true",
                        help="Synthetic latch only; NEVER qualifies the restored Debian latch")
    args = parser.parse_args()
    if not sys.flags.isolated or not sys.flags.dont_write_bytecode:
        raise RuntimeError("Use python -I -B")
    if os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") != "1":
        raise RuntimeError("PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 is required")
    if any(os.environ.get(k) for k in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONPATH", "PYTHONHOME")):
        raise RuntimeError("External Python/pytest configuration is forbidden")
    target_runtime = (
        sys.implementation.name == "cpython" and sys.platform == "linux"
        and sys.version_info[:3] == (3, 11, 18) and platform.machine() == "x86_64"
        and platform.freedesktop_os_release().get("ID") == "debian"
        and platform.freedesktop_os_release().get("VERSION_ID") == "13"
        and sys.prefix != sys.base_prefix
    )
    if not args.preparation and not target_runtime:
        raise RuntimeError("Qualification requires Debian 13 / x86_64 / CPython 3.11.18 dedicated venv")
    if args.preparation and args.latch_path is not None:
        raise RuntimeError("Preparation never accepts an external latch")
    if not args.preparation and (
        args.latch_path != TARGET_LATCH or args.expected_sha256 != EXPECTED_SHA256
    ):
        raise RuntimeError("Explicit restored path and expected campaign SHA-256 are required")
    evidence, scratch = new_output(args.evidence), new_output(args.scratch)
    if evidence.is_relative_to(scratch) or scratch.is_relative_to(evidence):
        raise RuntimeError("Evidence and scratch must be separate")
    if not args.preparation and (
        not evidence.is_relative_to(EVIDENCE_BASE.resolve())
        or scratch.is_relative_to(TARGET_LATCH.parent.resolve())
        or TARGET_LATCH.resolve().is_relative_to(scratch)
    ):
        raise RuntimeError("Invalid evidence/scratch scope")
    # These directories are new; no existing proof or restored directory is written.
    evidence.mkdir(mode=0o700)
    scratch.mkdir(mode=0o700)
    bootstrap = "qualification/quarantine_debian/verify_transfer.py"
    violations, executed, inventory = [], set(), {bootstrap: digest(ROOT / bootstrap)}
    install_audit((evidence, scratch), violations, inventory, executed)
    os.environ.update(TEMP=str(scratch), TMP=str(scratch), TMPDIR=str(scratch))
    # JUnit must not query even the host name through socket.gethostname().
    platform.node = lambda: "isolated-inprocess"
    import tempfile

    tempfile.tempdir = str(scratch)
    sys.path.insert(0, str(ROOT))
    metadata = {
        "python": sys.version, "platform": sys.platform,
        "preparation_only": args.preparation, "target_runtime": target_runtime,
        "verdict": "INCOMPLETE", "forbidden_io_events": violations,
    }
    latch, before = None, None
    try:
        from qualification.quarantine_debian.verify_transfer import verify_manifest

        if (ROOT / "SHA256SUMS").is_file():
            inventory.update(verify_manifest(ROOT))
            metadata["source_manifest_sha256"] = digest(ROOT / "SHA256SUMS")
        elif args.preparation:
            # Worktree preparation is explicitly non-qualifying.
            inventory.update({
                p.relative_to(ROOT).as_posix(): digest(p)
                for directory in ("backend", "analyseur_documents", "tests", "qualification")
                for p in (ROOT / directory).rglob("*.py")
                if "__pycache__" not in p.parts
            })
        else:
            raise RuntimeError("A verified transfer source manifest is required")
        (evidence / "source-SHA256SUMS").write_text(
            "".join(f"{sha}  {name}\n" for name, sha in sorted(inventory.items())),
            encoding="ascii",
        )
        for name in inventory:
            if name.endswith(".py"):
                ast.parse((ROOT / name).read_text(encoding="utf-8-sig"), filename=name, feature_version=(3, 11))
        if not args.preparation:
            from qualification.quarantine_debian.run_campaign import check_dependencies

            metadata["dependencies"] = check_dependencies()
            lock = ROOT / "qualification" / "quarantine_debian" / "requirements.lock"
            metadata["dependency_lock_sha256"] = digest(lock)
            (evidence / "requirements.lock").write_bytes(lock.read_bytes())
        else:
            import importlib.metadata

            metadata["dependencies"] = {
                d.metadata["Name"]: d.version for d in importlib.metadata.distributions()
            }
        latch = scratch / "synthetic-latch.json" if args.preparation else args.latch_path
        if args.preparation:
            latch.write_text('{"format": 1, "state": "quarantined"}\n', encoding="ascii")
            if os.name == "posix":
                latch.chmod(0o600)
        before = latch_snapshot(latch)
        expected = before["sha256"] if args.preparation else args.expected_sha256
        metadata.update(latch_path=str(latch), expected_sha256=expected, latch_before=before)
        if before["sha256"] != expected:
            raise RuntimeError("Restored latch SHA-256 mismatch")
        import pytest

        class StrictCampaign:
            def __init__(self):
                self.outcomes = Counter()
                self.scenarios = []
                self.case_index = 0

            @pytest.fixture
            def tmp_path(self):
                # Avoid pytest's best-effort "current" symlinks and automatic cleanup.
                self.case_index += 1
                directory = scratch / ("case-%02d" % self.case_index)
                directory.mkdir(mode=0o700)
                return directory

            def pytest_configure(self, config):
                config._restored_latch_campaign = {"latch": str(latch), "sha256": expected}

            def pytest_collection_finish(self, session):
                if len(session.items) != COUNT or any(
                    item.path.resolve() != (ROOT / TEST).resolve() for item in session.items
                ):
                    raise pytest.UsageError("Exactly the nine restored-latch cases must be collected")
                if any(
                    any(item.iter_markers(mark))
                    for item in session.items for mark in ("skip", "skipif", "xfail")
                ):
                    raise pytest.UsageError("skip/xfail markers are forbidden")

            def pytest_runtest_logreport(self, report):
                if report.when == "call":
                    self.outcomes[report.outcome] += 1
                    self.scenarios.append({
                        "nodeid": report.nodeid, "outcome": report.outcome,
                        "properties": dict(report.user_properties),
                    })
                if report.skipped or hasattr(report, "wasxfail"):
                    pytest.exit("skip/xfail/xpass is forbidden", returncode=1)

        strict = StrictCampaign()
        command = [
            "-c", str(HERE / "pytest.ini"), "--noconftest", "-p", "no:cacheprovider",
            "-x", "-q", "--tb=short", "--capture=sys", "-o", "junit_family=legacy",
            "--log-file", str(evidence / "pytest-internal.log"),
            "--basetemp", str(scratch / "pytest"), "--junitxml", str(evidence / "junit.xml"),
            str(ROOT / TEST),
        ]
        metadata["pytest_arguments"] = command
        status = pytest.main(command, plugins=[strict])
        metadata.update(pytest_exit_code=int(status), outcomes=dict(strict.outcomes))
        (evidence / "scenarios.json").write_text(json.dumps(strict.scenarios, indent=2) + "\n")
        if status != 0 or strict.outcomes != Counter(passed=COUNT) or violations:
            raise RuntimeError("Campaign failed or violated isolation")
        validate_junit(evidence / "junit.xml")
        for name, sha in inventory.items():
            if digest(ROOT / name) != sha:
                raise RuntimeError("Source changed during campaign: " + name)
        if (ROOT / "SHA256SUMS").is_file():
            verify_manifest(ROOT)
        metadata["verdict"] = (
            "PREPARATION_ONLY_9_PASS_NO_SKIP" if args.preparation
            else "LIMITED_GO_RESTORED_LATCH_FASTAPI_INPROCESS_ONLY"
        )
    except BaseException as exc:
        metadata.update(verdict="FAILED", error=str(exc))
        (evidence / "failure.txt").write_text(traceback.format_exc(), encoding="utf-8")
        raise
    finally:
        try:
            if before is not None:
                after = latch_snapshot(latch)
                metadata["latch_after"] = after
                if after != before:
                    metadata["verdict"] = "FAILED"
                    raise RuntimeError("Latch modified during campaign")
            if violations:
                metadata["verdict"] = "FAILED"
                raise RuntimeError("Forbidden I/O attempts were recorded")
        finally:
            metadata["executed_sources"] = sorted(executed)
            (evidence / "environment.json").write_text(json.dumps(metadata, indent=2) + "\n")
            # Includes JUnit, route/read evidence, failures and environment metadata.
            files = sorted(p for p in evidence.iterdir() if p.is_file())
            (evidence / "SHA256SUMS").write_text(
                "".join(f"{digest(p)}  {p.name}\n" for p in files), encoding="ascii",
            )
    print(metadata["verdict"])
    print("No GO: Docker, global Backup/Restore, S2, Lifecycle 10, Public Beta, production")


if __name__ == "__main__":
    main()
