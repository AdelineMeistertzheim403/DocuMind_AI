"""Capture only this delivery's unit tests in a new independent evidence directory."""
import argparse
from pathlib import Path
import platform
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).absolute().parent))
from comparator import digest, encode, need, new_directory, write_new
from layer_contents import verify_release


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--release-anchor")
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    root = Path(__file__).absolute().parent
    need(args.out.is_absolute() and root not in args.out.parents and args.out != root,
         "Absolute independent output required")
    need(sys.version_info[:2] == (3, 11), "Python 3.11 required")
    if args.release_anchor:
        verify_release(root, args.release_anchor)
    need(args.timeout > 0, "Positive timeout required")
    out = new_directory(args.out)
    argv = [sys.executable, "-I", "-B", "-m", "unittest", "discover",
            "-s", str(root), "-p", "test_*.py", "-v"]
    receipt = {"argv": argv, "recorder_argv": sys.orig_argv,
               "cwd": str(root), "python": sys.version, "start_ns": time.time_ns(),
               "platform": platform.platform(),
               "os_release": platform.freedesktop_os_release() if sys.platform == "linux" else None,
               "complete": False, "returncode": None, "timeout": args.timeout,
               "release_anchor": args.release_anchor,
               "code_sha256": {p.name: digest(p) for p in sorted(root.glob("*.py"))}}
    write_new(out / "started.json", encode(receipt))
    code = 30
    try:
        with (out / "stdout").open("xb") as stdout, (out / "stderr").open("xb") as stderr:
            process = subprocess.Popen(argv, cwd=root, stdout=stdout, stderr=stderr)
            try:
                code = process.wait(timeout=args.timeout)
                receipt.update(complete=True, returncode=code)
            except BaseException:
                process.kill()
                process.wait()
                raise
    except BaseException as error:
        receipt["capture_error"] = type(error).__name__ + ": " + str(error)
    receipt["end_ns"] = time.time_ns()
    receipt["sha256"] = {n: digest(out / n) for n in ("stdout", "stderr")}
    write_new(out / "receipt.json", encode(receipt))
    names = ("started.json", "stdout", "stderr", "receipt.json")
    write_new(out / "SHA256SUMS", "".join(
        digest(out / n) + "  " + n + "\n" for n in names).encode("ascii"))
    write_new(out / "evidence-anchor.json", encode({
        "sha256sums": digest(out / "SHA256SUMS"), "decision": "REVIEW_ONLY_BLOCKED",
        "external_authentication_required": True}))
    return code if receipt["complete"] and code >= 0 else 30


if __name__ == "__main__":
    sys.exit(main())
