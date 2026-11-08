"""Build a NEW offline-only transfer from explicitly allowlisted worktree sources."""
import argparse
import ast
from datetime import datetime, timezone
import email
import json
from pathlib import Path
import shutil
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "qualification" / "quarantine_debian"))
from build_transfer import SOURCE_FILES, archive, manifest
from verify_transfer import digest, extract_archive, verify_manifest

GUIDE = "DOCNELO_V51_RESTORED_LATCH_DEBIAN_GUIDE.md"
FILES = [name for name in SOURCE_FILES if name != "qualification/quarantine_inprocess/pytest.ini"] + [
    "tests/test_recovery_quarantine_restored_latch.py",
    "qualification/restored_latch/pytest.ini",
    "qualification/restored_latch/run_campaign.py",
    GUIDE,
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous-transfer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    previous, output = args.previous_transfer.resolve(strict=True), args.output.resolve()
    if output.exists() or output.is_relative_to(previous) or previous.is_relative_to(output):
        raise RuntimeError("Output must be new and separate from the previous transfer")
    verify_manifest(previous)
    before = {name: digest(ROOT / name) for name in FILES}
    old_sources = previous / "quarantine-sources.zip"
    with zipfile.ZipFile(old_sources) as old:
        old_names = set(old.namelist())
    with tempfile.TemporaryDirectory(prefix="docnelo-restored-latch-build-") as temp:
        stage = Path(temp)
        wheels, source = stage / "wheels", stage / "source"
        extract_archive(previous / "quarantine-wheels-cp311-linux-x86_64.zip", wheels)
        lock = (previous / "requirements.lock").read_text(encoding="ascii")
        # Revalidate every reused wheel against the exact hash lock and Python target.
        from packaging.requirements import Requirement
        from packaging.specifiers import SpecifierSet
        from packaging.utils import canonicalize_name, parse_wheel_filename

        pins = {}
        for line in lock.splitlines():
            if line and not line.startswith("#"):
                text, sha = line.split(" --hash=sha256:")
                req = Requirement(text)
                name = canonicalize_name(req.name)
                if name in pins or len(req.specifier) != 1 or not str(req.specifier).startswith("=="):
                    raise RuntimeError("Non-exact/duplicate dependency pin")
                pins[name] = (req, sha)
        inventory = []
        seen = set()
        for path in sorted(wheels.iterdir()):
            if path.name == "SHA256SUMS":
                continue
            name, version, _, tags = parse_wheel_filename(path.name)
            if name in seen or name not in pins:
                raise RuntimeError("Unexpected wheel: " + path.name)
            req, sha = pins[name]
            if version not in req.specifier or digest(path) != sha:
                raise RuntimeError("Wheel does not match hash lock: " + path.name)
            compatible = any(
                (
                    t.interpreter == "py3" and t.abi == "none"
                    or t.interpreter == "cp311" and t.abi in {"none", "cp311"}
                    or t.abi == "abi3" and t.interpreter.startswith("cp3")
                    and t.interpreter[2:].isdigit() and 32 <= int(t.interpreter[2:]) <= 311
                )
                and (t.platform == "any" or t.platform.startswith("manylinux") and t.platform.endswith("_x86_64"))
                for t in tags
            )
            if not compatible:
                raise RuntimeError("Incompatible wheel: " + path.name)
            with zipfile.ZipFile(path) as wheel:
                names = [n for n in wheel.namelist() if n.endswith(".dist-info/METADATA")]
                if len(names) != 1:
                    raise RuntimeError("Invalid wheel metadata")
                metadata = email.message_from_bytes(wheel.read(names[0]))
                requires_python = metadata.get("Requires-Python")
                if requires_python and "3.11.18" not in SpecifierSet(requires_python):
                    raise RuntimeError("Incompatible Python requirement")
            seen.add(name)
            inventory.append({
                "file": path.name, "version": str(version), "sha256": sha,
                "tags": sorted(map(str, tags)), "requires_python": requires_python,
            })
        if seen != set(pins):
            raise RuntimeError("Incomplete wheel closure")
        for name in FILES:
            path = ROOT / name
            if path.is_symlink() or not path.is_file():
                raise RuntimeError("Unexpected source object: " + name)
            if path.suffix == ".py":
                ast.parse(path.read_text(encoding="utf-8-sig"), filename=name, feature_version=(3, 11))
            destination = source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
        lock_destination = source / "qualification" / "quarantine_debian" / "requirements.lock"
        lock_destination.write_text(lock, encoding="ascii", newline="\n")
        (source / "PACKAGE.json").write_text(json.dumps({
            "campaign": "Docnelo V5.1 restored latch real FastAPI in-process",
            "built_at_utc": datetime.now(timezone.utc).isoformat(),
            "target": "Debian 13 x86_64 / CPython 3.11.18",
            "expected_tests": 9, "sources_sha256": before, "wheels": inventory,
            "previous_transfer_manifest_sha256": digest(previous / "SHA256SUMS"),
            "additional_files_vs_previous_sources": sorted(set(FILES) - old_names),
            "scope": "Qualification harness only, not a deployable service or Debian result",
        }, indent=2) + "\n", encoding="utf-8", newline="\n")
        manifest(source)
        if before != {name: digest(ROOT / name) for name in FILES}:
            raise RuntimeError("Sources changed during packaging")
        output.mkdir(parents=True)
        archive(source, output / "quarantine-sources.zip")
        # Identical bytes, no rebuild or change to the former wheel evidence.
        shutil.copyfile(previous / "quarantine-wheels-cp311-linux-x86_64.zip",
                        output / "quarantine-wheels-cp311-linux-x86_64.zip")
        shutil.copyfile(previous / "requirements.lock", output / "requirements.lock")
        shutil.copyfile(ROOT / GUIDE, output / GUIDE)
        shutil.copyfile(ROOT / "qualification" / "quarantine_debian" / "verify_transfer.py",
                        output / "verify_transfer.py")
        manifest(output)
    print(json.dumps({
        "output": str(output), "source_files": len(FILES), "wheels": len(seen),
        "SHA256SUMS_sha256": digest(output / "SHA256SUMS"),
    }, indent=2))


if __name__ == "__main__":
    main()
