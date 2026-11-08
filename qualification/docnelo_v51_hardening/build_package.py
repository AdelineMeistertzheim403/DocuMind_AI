"""Build a source-only qualification ZIP; no application imports or service access."""
import argparse
from hashlib import sha256
import io
from pathlib import Path, PurePosixPath
import re
import zipfile


REPORT = "DOCNELO_V51_BACKUP_RESTORE_HARDENING_REPORT.md"
EXPECTED = {
    "backend/lifecycle_backup_lock.py": "efca36c25a7ffb372edaee7120a57aa68b926da9801bada5bb41dc24753f6433",
    "tools/restore_pgvector.py": "4848d95793f86e27fa06f35036f2db49f7b14bc58cdb2e835a246ddb7aef5292",
    "tools/validate_restore.py": "92edaabbf1ca48f62687156c9f7e4c6d31629546be20ea1d26107a18d15357ff",
    "tools/verify_snapshot.py": "f7cead2c1fa8e623e3b6c52c81d584ac0addee4e7a0fba26846650d5681fae8e",
    "tests/test_lifecycle_backup_lock.py": "990206c685868ed036e8a004891c87418c9e46347f9815ca87d029695fabbfbb",
    "tests/test_restore_pgvector.py": "94f2514c265314454b3808aa2d6017b68cada0dd1bd36cae5c3c937e61eea3ea",
    "tests/test_restore_hardening.py": "5b16abbab6b4c6466a6db374b3cbaf2dd3223804daf85bfff547b74ab7d70afc",
    "tests/test_restore_hardening_postgres.py": "8a0c6927e81d6ec02a3528cb9140c0136cf55f1c05682b22b291e3c49142985b",
    "tests/test_public_beta_snapshot.py": "99cd6178467bed1cbde24b45a5b16cf2a661c09a878055238b0cd4acd6b098ae",
}
EXTRA = (
    "backend/__init__.py",
    "backend/lifecycle_snapshot.py",
    "tools/lifecycle_key_policy.py",
    "tests/__init__.py",
    "tests/test_lifecycle_keys_restore.py",
    REPORT,
    "qualification/docnelo_v51_hardening/pytest_plugin.py",
    "qualification/docnelo_v51_hardening/pytest.ini",
    "qualification/docnelo_v51_hardening/requirements.txt",
    "qualification/docnelo_v51_hardening/README.md",
    "qualification/docnelo_v51_hardening/build_package.py",
)
FILES = tuple(sorted((*EXPECTED, *EXTRA)))


def read_payload(root):
    root = root.resolve()
    payload = {}
    for name in FILES:
        path = root.joinpath(*PurePosixPath(name).parts)
        if not path.is_file() or path.is_symlink() or path.resolve() != path:
            raise ValueError(f"Missing or non-canonical expected source: {name}")
        payload[name] = path.read_bytes()
    pairs = re.findall(
        r"\| `([^`]+\.py)` \| `([a-f0-9]{64})` \|",
        payload[REPORT].decode("utf-8"),
    )
    recorded = {name.replace("\\", "/"): digest for name, digest in pairs}
    if len(pairs) != 9 or recorded != EXPECTED:
        raise ValueError("Hardening report does not match the pinned nine-file revision")
    for name, expected in EXPECTED.items():
        if sha256(payload[name]).hexdigest() != expected:
            raise ValueError(f"Expected source SHA-256 mismatch: {name}")
    return payload


def build_package(root, output):
    manifest_path = output.with_suffix(".SHA256SUMS")
    checksum_path = output.with_name(output.name + ".sha256")
    for path in (output, manifest_path, checksum_path):
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"Refuse to overwrite an existing artifact: {path}")
    payload = read_payload(root)
    manifest = "".join(
        f"{sha256(content).hexdigest()}  {name}\n"
        for name, content in sorted(payload.items())
    ).encode("utf-8")
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in (*sorted(payload.items()), ("SHA256SUMS", manifest)):
            member = zipfile.ZipInfo(name, date_time=(2026, 11, 1, 0, 0, 0))
            member.compress_type = zipfile.ZIP_DEFLATED
            member.create_system = 3
            member.external_attr = 0o100600 << 16
            archive.writestr(member, content)
    zipped = stream.getvalue()
    with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
        if set(archive.namelist()) != {*payload, "SHA256SUMS"}:
            raise ValueError("Unexpected archive inventory")
        for name, content in payload.items():
            if archive.read(name) != content:
                raise ValueError(f"Archive bytes differ: {name}")
        if archive.read("SHA256SUMS") != manifest or archive.testzip() is not None:
            raise ValueError("Archive or manifest verification failed")
    digest = sha256(zipped).hexdigest()
    output.parent.mkdir(parents=True, exist_ok=True)
    for path, content in (
        (output, zipped),
        (manifest_path, manifest),
        (checksum_path, f"{digest}  {output.name}\n".encode("ascii")),
    ):
        with path.open("xb") as destination:
            destination.write(content)
    return digest, len(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    digest, count = build_package(Path(__file__).resolve().parents[2], args.output)
    print(f"ZIP: {args.output.resolve()}")
    print(f"SHA-256: {digest}")
    print(f"Payload files: {count}; SHA256SUMS additionally included")


if __name__ == "__main__":
    main()
