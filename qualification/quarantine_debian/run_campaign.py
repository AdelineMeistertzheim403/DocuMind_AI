"""Fail-closed entry point for the unchanged 42-case in-process campaign."""
import argparse
import ast
from collections import Counter
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import sys
import xml.etree.ElementTree as ET

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
TEST = "tests/test_recovery_quarantine_inprocess.py"
sys.path.insert(0, str(HERE))

from verify_transfer import digest, verify_manifest


def check_dependencies():
    from packaging.requirements import Requirement
    from packaging.specifiers import SpecifierSet
    from packaging.utils import canonicalize_name

    expected = {}
    for line in (HERE / "requirements.lock").read_text(encoding="ascii").splitlines():
        if line and not line.startswith("#"):
            requirement = Requirement(line.split(" --hash=")[0])
            expected[canonicalize_name(requirement.name)] = str(requirement.specifier)[2:]
    installed = {}
    distributions = list(importlib.metadata.distributions())
    for dist in distributions:
        name = canonicalize_name(dist.metadata["Name"])
        if name in installed:
            raise RuntimeError("Duplicate installed distribution: " + name)
        installed[name] = dist.version
        location = Path(dist.locate_file("")).resolve()
        if not location.is_relative_to(Path(sys.prefix).resolve()):
            raise RuntimeError("Dependency outside the dedicated venv: " + name)
        requires_python = dist.metadata.get("Requires-Python")
        if requires_python and platform.python_version() not in SpecifierSet(requires_python):
            raise RuntimeError("Incompatible Python dependency: " + name)
        for text in dist.requires or []:
            dependency = Requirement(text)
            if dependency.marker is None or dependency.marker.evaluate({"extra": ""}):
                actual = importlib.metadata.version(dependency.name)
                if actual not in dependency.specifier:
                    raise RuntimeError("Unsatisfied dependency: " + text)
    if installed != expected:
        raise RuntimeError("Installed dependencies differ from requirements.lock: " + repr(installed))
    return installed


def validate_junit(path):
    root = ET.parse(path).getroot()
    cases = list(root.iter("testcase"))
    if len(cases) != 42 or any(
        list(case.iter(tag)) for case in cases for tag in ("failure", "error", "skipped")
    ):
        raise RuntimeError("JUnit must contain exactly 42 successful, non-skipped cases")
    suites = list(root.iter("testsuite"))
    if not suites or sum(int(s.get("tests", "0")) for s in suites) != 42:
        raise RuntimeError("Unexpected JUnit test count")
    if any(int(s.get(field, "0")) for s in suites for field in ("failures", "errors", "skipped")):
        raise RuntimeError("JUnit contains unsuccessful outcomes")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--basetemp", type=Path, required=True)
    parser.add_argument("--allow-patch-mismatch", action="store_true",
                        help="Preparation check only; never a target qualification")
    args = parser.parse_args()
    if os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") != "1":
        raise RuntimeError("PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 is required")
    if any(os.environ.get(key) for key in ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTHONPATH", "PYTHONHOME")):
        raise RuntimeError("External Python/pytest configuration is forbidden")
    if (
        sys.implementation.name != "cpython" or sys.platform != "linux"
        or sys.version_info[:2] != (3, 11) or platform.machine() != "x86_64"
        or sys.prefix == sys.base_prefix
    ):
        raise RuntimeError("A dedicated Linux x86_64 CPython 3.11 venv is required")
    target_runtime = sys.version_info[:3] == (3, 11, 18)
    if not target_runtime and not args.allow_patch_mismatch:
        raise RuntimeError("Target qualification requires exactly Python 3.11.18")
    if args.evidence.is_symlink() or args.basetemp.is_symlink():
        raise RuntimeError("Evidence and basetemp must not be symlinks")
    evidence, basetemp = args.evidence.resolve(), args.basetemp.resolve()
    for path in (evidence, basetemp):
        if path.exists() or path.is_symlink():
            raise RuntimeError("Evidence and basetemp must both be new: " + str(path))
        if path.is_relative_to(ROOT) or any(
            part.lower() in {"release", "releases", "fixtures", "artifacts"} for part in path.parts
        ):
            raise RuntimeError("Protected output path: " + str(path))
    if evidence.is_relative_to(basetemp) or basetemp.is_relative_to(evidence):
        raise RuntimeError("Evidence and temporary files must be separate")
    inventory = verify_manifest(ROOT)
    for name in inventory:
        if name.endswith(".py"):
            text = (ROOT / name).read_text(encoding="utf-8-sig")
            ast.parse(text, filename=name, feature_version=(3, 11))
            compile(text, str(ROOT / name), "exec")
    dependencies = check_dependencies()
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    evidence.mkdir(mode=0o700)
    report = evidence / "junit.xml"
    violations, executed = [], set()

    def audit(event, arguments):
        if event.startswith("socket.") or event in {
            "subprocess.Popen", "os.system", "os.fork", "os.forkpty", "os.posix_spawn",
            "sqlite3.connect",
        }:
            violations.append(event)
            raise RuntimeError("Forbidden I/O: " + event)
        if event == "exec":
            filename = arguments[0].co_filename
            if not filename.startswith("<"):
                path = Path(filename).resolve()
                if path.is_relative_to(ROOT) and path.suffix == ".py":
                    name = path.relative_to(ROOT).as_posix()
                    if name not in inventory:
                        violations.append("unexpected_source")
                        raise RuntimeError("Uninventoried source: " + name)
                    executed.add(name)

    sys.addaudithook(audit)
    import pytest

    class StrictCampaign:
        def __init__(self):
            self.outcomes = Counter()

        def pytest_collection_finish(self, session):
            if len(session.items) != 42 or any(
                item.path.resolve() != (ROOT / TEST).resolve() for item in session.items
            ):
                raise pytest.UsageError("Exactly the 42 quarantine cases must be collected")
            for item in session.items:
                if any(any(item.iter_markers(mark)) for mark in ("skip", "skipif", "xfail")):
                    raise pytest.UsageError("Skipped or xfailed cases are forbidden")

        def pytest_runtest_logreport(self, report):
            if report.when == "call":
                self.outcomes[report.outcome] += 1
            if report.skipped or hasattr(report, "wasxfail"):
                pytest.exit("A skipped or xfailed test is forbidden", returncode=1)

    strict = StrictCampaign()
    command = [
        "-c", str(ROOT / "qualification" / "quarantine_inprocess" / "pytest.ini"),
        "--noconftest", "-p", "no:cacheprovider", "-x", "-q", "--tb=short",
        "-o", "junit_family=legacy", "--basetemp", str(basetemp),
        "--junitxml", str(report), TEST,
    ]
    metadata = {
        "python": sys.version, "platform": sys.platform, "kernel": os.uname().release,
        "target_python_3_11_18": target_runtime,
        "preparation_only": not target_runtime,
        "dependencies": dependencies, "pytest_arguments": command,
        "source_manifest_sha256": digest(ROOT / "SHA256SUMS"),
        "verdict": "INCOMPLETE",
    }
    (evidence / "environment.json").write_text(json.dumps(metadata, indent=2) + "\n")
    status = pytest.main(command, plugins=[strict])
    metadata.update(
        pytest_exit_code=int(status), outcomes=dict(strict.outcomes),
        forbidden_io_events=violations, executed_sources=sorted(executed),
    )
    try:
        if status != 0 or strict.outcomes != Counter(passed=42) or violations:
            raise RuntimeError("Campaign failed or violated isolation")
        validate_junit(report)
        verify_manifest(ROOT)
        metadata["verdict"] = "42_PASS_NO_SKIP" if target_runtime else "PREPARATION_ONLY_42_PASS_NO_SKIP"
    finally:
        (evidence / "environment.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print(metadata["verdict"] + "; no global GO, restored-latch or Docker qualification")


if __name__ == "__main__":
    main()
