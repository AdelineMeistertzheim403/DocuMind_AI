"""Verify exact inventories and extract only into a new, dedicated directory."""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import re
import stat
import zipfile


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def safe_name(name):
    path = PurePosixPath(name)
    if (
        not name or "\\" in name or ":" in name or path.is_absolute()
        or any(ord(char) < 32 or ord(char) == 127 for char in name)
        or any(part in {"", ".", ".."} for part in name.split("/"))
        or path.as_posix() != name
    ):
        raise RuntimeError("Unsafe inventory path: " + name)
    return path


def verify_manifest(root):
    root = root.resolve(strict=True)
    expected = {}
    for line in (root / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        match = re.fullmatch(r"([0-9a-f]{64})  (.+)", line)
        if not match:
            raise RuntimeError("Malformed SHA256SUMS entry")
        sha, name = match.groups()
        safe_name(name)
        if name == "SHA256SUMS" or name in expected:
            raise RuntimeError("Duplicate or self-referencing inventory entry")
        expected[name] = sha
    if not expected:
        raise RuntimeError("Empty inventory")
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise RuntimeError("Unexpected filesystem object: " + str(path))
        if path.is_file() and path != root / "SHA256SUMS":
            actual.add(path.relative_to(root).as_posix())
    if actual != set(expected):
        raise RuntimeError(
            "Inventory mismatch; missing=" + repr(sorted(set(expected) - actual))
            + "; extra=" + repr(sorted(actual - set(expected)))
        )
    for name, sha in expected.items():
        if digest(root / name) != sha:
            raise RuntimeError("SHA-256 mismatch: " + name)
    return expected


def extract_archive(archive, destination):
    with zipfile.ZipFile(archive) as source:
        names = set()
        for item in source.infolist():
            safe_name(item.orig_filename)
            safe_name(item.filename)
            mode = item.external_attr >> 16
            if (
                item.filename in names or item.is_dir() or item.flag_bits & 1
                or (stat.S_IFMT(mode) not in {0, stat.S_IFREG})
            ):
                raise RuntimeError("Unexpected ZIP member: " + item.filename)
            names.add(item.filename)
        destination.mkdir()
        source.extractall(destination)
    verify_manifest(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transfer", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()
    transfer = args.transfer.resolve(strict=True)
    verify_manifest(transfer)
    if args.destination.is_symlink():
        raise RuntimeError("Extraction destination must not be a symlink")
    destination = args.destination.resolve()
    if any(part.lower() in {"release", "releases", "fixtures", "artifacts"} for part in destination.parts):
        raise RuntimeError("Extraction into protected paths is forbidden")
    if destination.exists() or destination.is_symlink():
        raise RuntimeError("Extraction destination must not exist")
    destination.mkdir()
    extract_archive(transfer / "quarantine-sources.zip", destination / "source")
    extract_archive(transfer / "quarantine-wheels-cp311-linux-x86_64.zip", destination / "wheels")
    lock = destination / "source" / "qualification" / "quarantine_debian" / "requirements.lock"
    if digest(lock) != digest(transfer / "requirements.lock"):
        raise RuntimeError("Source and transfer dependency locks differ")
    print("Transfer verified and extracted into " + str(destination))


if __name__ == "__main__":
    main()
