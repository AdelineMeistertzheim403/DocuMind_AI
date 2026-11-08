"""One-time sealing of a new delivery; no overwrite, download or historical input."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).absolute().parent))
from comparator import digest, encode, need, safe_path, verify_release, write_new


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--anchor-out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).absolute().parent
    need(args.anchor_out.is_absolute() and root not in args.anchor_out.parents
         and not args.anchor_out.exists() and not args.anchor_out.is_symlink()
         and args.anchor_out.parent.is_dir(), "New external anchor file required")
    need(not (root / "SHA256SUMS").exists(), "Already sealed; never overwrite")
    files = []
    for path in root.rglob("*"):
        need(not path.is_symlink(), "Symlink in delivery")
        if path.is_file():
            name = safe_path(path.relative_to(root).as_posix())
            need("__pycache__" not in name.split("/"), "Bytecode must not enter delivery")
            files.append(name)
        else:
            need(path.is_dir(), "Special delivery entry")
    data = "".join(digest(root / n) + "  " + n + "\n" for n in sorted(files)).encode("ascii")
    write_new(root / "SHA256SUMS", data)
    anchor = digest(root / "SHA256SUMS")
    verify_release(root, anchor)
    value = {"delivery": root.name, "decision": "REVIEW_ONLY_BLOCKED",
             "formal_b1_contents_closed": False,
             "go": {"production": False, "runtime": False, "c5": False},
             "sha256sums": anchor, "comparator_sha256": digest(root / "comparator.py"),
             "payload_files": len(files), "signature": False,
             "external_trusted_channel_required": True}
    write_new(args.anchor_out, encode(value))
    print(encode(value).decode("ascii"), end="")


if __name__ == "__main__":
    main()
