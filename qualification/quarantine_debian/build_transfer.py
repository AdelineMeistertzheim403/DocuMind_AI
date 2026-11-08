"""Build an allowlisted transfer; download only public binary distributions."""
import argparse
import ast
from datetime import datetime, timezone
import email
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zipfile

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name, parse_wheel_filename

from verify_transfer import digest, verify_manifest


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
GUIDE = "DOCNELO_V51_QUARANTINE_DEBIAN_TRANSFER_GUIDE.md"
SOURCE_FILES = """
analyseur_documents/__init__.py
analyseur_documents/core/__init__.py
analyseur_documents/core/analyseur.py
analyseur_documents/core/analyseur_lisibilite.py
analyseur_documents/core/analyseur_phrases.py
analyseur_documents/core/analyseur_resume.py
analyseur_documents/core/analyseur_structure.py
analyseur_documents/core/analyseur_style.py
analyseur_documents/core/analyseur_termes.py
analyseur_documents/core/analyseur_utils.py
backend/__init__.py
backend/account_api.py
backend/account_models.py
backend/ai/__init__.py
backend/ai/api.py
backend/ai/long_api.py
backend/ai/long_models.py
backend/ai/long_plan.py
backend/ai/long_summary.py
backend/ai/models.py
backend/ai/providers.py
backend/ai/retrieval.py
backend/ai/schemas.py
backend/ai/service.py
backend/ai/settings_api.py
backend/api.py
backend/audit_middleware.py
backend/auth.py
backend/authentication.py
backend/config.py
backend/db.py
backend/gateway.py
backend/lite_admissions.py
backend/main.py
backend/models.py
backend/public_registration.py
backend/rag/__init__.py
backend/rag/api.py
backend/rag/billing.py
backend/rag/comparison.py
backend/rag/indexing.py
backend/rag/models.py
backend/rag/providers.py
backend/rag/retrieval.py
backend/rag/schemas.py
backend/rag/service.py
backend/recovery_quarantine.py
backend/resource_limits.py
backend/schemas.py
backend/security_audit.py
backend/services/__init__.py
backend/services/document_integrity.py
backend/services/documents.py
backend/services/worker.py
backend/upload_admission.py
tests/__init__.py
tests/test_recovery_quarantine_inprocess.py
qualification/quarantine_inprocess/pytest.ini
qualification/quarantine_debian/run_campaign.py
qualification/quarantine_debian/verify_transfer.py
""".split()


def manifest(directory):
    paths = sorted(p for p in directory.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    (directory / "SHA256SUMS").write_text(
        "".join(f"{digest(p)}  {p.relative_to(directory).as_posix()}\n" for p in paths),
        encoding="ascii", newline="\n",
    )
    verify_manifest(directory)


def archive(directory, destination):
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                entry = zipfile.ZipInfo(path.relative_to(directory).as_posix(), (2026, 11, 2, 0, 0, 0))
                entry.external_attr = 0o100644 << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                output.writestr(entry, path.read_bytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path,
                        help="Reuse a previously verified wheelhouse without network access")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise RuntimeError("Output must be new: " + str(output))
    pins = [
        Requirement(line) for line in (HERE / "requirements.pins").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    expected = {canonicalize_name(p.name): p for p in pins}
    if len(expected) != len(pins) or any(
        len(p.specifier) != 1 or not str(p.specifier).startswith("==") for p in pins
    ):
        raise RuntimeError("Dependencies must be uniquely and exactly pinned")
    before = {name: digest(ROOT / name) for name in SOURCE_FILES}
    with tempfile.TemporaryDirectory(prefix="docnelo-quarantine-build-") as temp:
        stage = Path(temp)
        source, wheels = stage / "source", stage / "wheels"
        wheels.mkdir()
        if args.wheelhouse:
            verified = verify_manifest(args.wheelhouse)
            if any(not name.endswith(".whl") for name in verified):
                raise RuntimeError("Only wheels are allowed in the wheelhouse")
            for name in verified:
                shutil.copyfile(args.wheelhouse / name, wheels / name)
        else:
            subprocess.run([
                sys.executable, "-m", "pip", "--isolated", "download",
                "--disable-pip-version-check", "--no-cache-dir", "--progress-bar", "off",
                "--only-binary=:all:", "--no-deps",
                "--platform", "manylinux_2_28_x86_64", "--platform", "manylinux2014_x86_64",
                "--implementation", "cp", "--python-version", "3.11",
                "--abi", "cp311", "--abi", "abi3", "--abi", "none",
                "--dest", str(wheels), "-r", str(HERE / "requirements.pins"),
            ], check=True)
        found, inventory = {}, []
        for path in sorted(wheels.iterdir()):
            name, version, _, tags = parse_wheel_filename(path.name)
            if name in found or name not in expected or version not in expected[name].specifier:
                raise RuntimeError("Unexpected wheel: " + path.name)
            if any(t.platform != "any" and not t.platform.endswith("_x86_64") for t in tags):
                raise RuntimeError("Unexpected wheel platform: " + path.name)
            with zipfile.ZipFile(path) as wheel:
                metadata_names = [n for n in wheel.namelist() if n.endswith(".dist-info/METADATA")]
                if len(metadata_names) != 1:
                    raise RuntimeError("Unexpected wheel metadata: " + path.name)
                metadata = email.message_from_bytes(wheel.read(metadata_names[0]))
                requires_python = metadata.get("Requires-Python")
                if requires_python:
                    from packaging.specifiers import SpecifierSet
                    if "3.11.18" not in SpecifierSet(requires_python):
                        raise RuntimeError("Incompatible Requires-Python: " + path.name)
            found[name] = path
            inventory.append({
                "file": path.name, "name": name, "version": str(version),
                "sha256": digest(path), "tags": sorted(map(str, tags)),
                "requires_python": requires_python,
            })
        if set(found) != set(expected):
            raise RuntimeError("Incomplete wheel closure")
        lock = "# Linux x86_64 CPython 3.11; one reviewed binary wheel per pin.\n"
        for name in sorted(expected):
            lock += f"{expected[name]} --hash=sha256:{digest(found[name])}\n"
        for name in SOURCE_FILES:
            original = ROOT / name
            if original.suffix == ".py":
                ast.parse(original.read_text(encoding="utf-8-sig"), filename=name, feature_version=(3, 11))
            destination = source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, destination)
        (source / "qualification" / "quarantine_debian" / "requirements.lock").write_text(
            lock, encoding="ascii", newline="\n",
        )
        shutil.copyfile(ROOT / GUIDE, source / GUIDE)
        (source / "PACKAGE.json").write_text(json.dumps({
            "campaign": "Docnelo V5.1 Quarantine in-process",
            "built_at_utc": datetime.now(timezone.utc).isoformat(),
            "target": "Debian 13 / Linux x86_64 / CPython 3.11.18",
            "expected_tests": 42, "application_sources": before,
            "wheels": inventory,
            "qualification": "Not a Debian VM result, restored-latch or Docker qualification",
        }, indent=2) + "\n", encoding="utf-8", newline="\n")
        manifest(source)
        manifest(wheels)
        if before != {name: digest(ROOT / name) for name in SOURCE_FILES}:
            raise RuntimeError("Sources changed during packaging")
        output.mkdir(parents=True)
        archive(source, output / "quarantine-sources.zip")
        archive(wheels, output / "quarantine-wheels-cp311-linux-x86_64.zip")
        (output / "requirements.lock").write_text(lock, encoding="ascii", newline="\n")
        shutil.copyfile(ROOT / GUIDE, output / GUIDE)
        shutil.copyfile(HERE / "verify_transfer.py", output / "verify_transfer.py")
        manifest(output)
    print(json.dumps({
        "output": str(output), "source_files": len(SOURCE_FILES),
        "wheels": len(found), "SHA256SUMS_sha256": digest(output / "SHA256SUMS"),
    }, indent=2))


if __name__ == "__main__":
    main()
