"""P3 regular-layer contents only; strict whole-archive refusal is never lifted."""
import argparse
import os
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).absolute().parent))
import comparator as core


REFERENCES = {
    **core.REFERENCES,
    "oci_manifest": "c4c9b897d2e3dea6bbcc3da95b078ce5ffa556f5e4c52020a40da8be784ccc44",
    "oci_manifest_size": 402,
    "config_size": 835,
    "layer_size": 322534912,
    "auxiliary": "eec772146db049680bf51af9758854bd4c210bff907cac5d73a10deec0775653",
    "auxiliary_size": 829,
}
HISTORICAL_V2 = {
    "source": "operator-reported Debian 13.7 / Python 3.11.18; raw receipts not opened here",
    "returncode": 20, "status": "ERROR", "complete": True,
    "evidence_manifest_sha256": "da22ccae43b1eb4df9906993015fc666bb454e7bdb0cdcc41ea1ba65d780cd0c",
    "tests_passed": 35, "tests_skipped": 0,
    "tests_manifest_sha256": "80f0435b6d5eddfd724660359c1cfd7ec0ef76aa13ea01484855c370188067ea",
}


def base_report(refs):
    return {
        "schema": "p4-b1-p3-layer-contents-v1", "decision": "REVIEW_ONLY_BLOCKED",
        "status": "ERROR", "returncode": 20, "formal_b1_contents_closed": False,
        "go": {"production": False, "runtime": False, "p4": False, "c5": False},
        "expected_anchors": refs, "observed_sha256": {}, "checks": {},
        "historical_v2_refusal": dict(HISTORICAL_V2),
        "A_regular_layer_contents": {"decision": "NOT_ESTABLISHED", "measurement_complete": False,
                                     "scope_returncode": 20},
        "B_strict_whole_archive": {"decision": "BLOCKED", "status": "ERROR", "returncode": 20,
                                  "conformity_granted": False, "anomalies": [],
                                  "expected_persistent_anomaly": {
                                      "path": "blobs/sha256/" + refs["auxiliary"],
                                      "sha256": refs["auxiliary"], "size": refs["auxiliary_size"],
                                      "approved": False}},
        "C_p4_and_provenance": {"qualification_granted": False, "provenance_granted": False},
        "methodological_limits": list(core.LIMITS) + [
            "Regular layer contents are a separate scope, not a whole-archive approval.",
            "The pinned unreferenced auxiliary blob remains an archive anomaly.",
            "Historical v2 refusal and receipts are reported references, never replaced.",
        ],
    }


def pinned_member(entries, name, sha256, size):
    core.need(name in entries and entries[name]["type"] == "file",
              "Pinned member missing/nonregular: " + name)
    core.need(entries[name]["sha256"] == sha256, "Pinned member SHA-256 mismatch: " + name)
    core.need(entries[name]["size"] == size, "Pinned member size mismatch: " + name)


def exact_descriptor(value, digest, size, media):
    core.need(isinstance(value, dict) and set(value) == {"mediaType", "digest", "size"},
              "Ambiguous/unrecognized explicit OCI descriptor")
    core.need(value["digest"] == "sha256:" + digest and value["mediaType"] == media
              and type(value["size"]) is int and value["size"] == size,
              "Explicit OCI descriptor identity/size/mediaType mismatch")


def scoped_binding(entries, small, refs, report):
    prefix = "blobs/sha256/"
    config_name, layer_name = prefix + refs["config"], prefix + refs["layer"]
    manifest_name, auxiliary_name = prefix + refs["oci_manifest"], prefix + refs["auxiliary"]
    core.need(len({config_name, layer_name, manifest_name, auxiliary_name}) == 4,
              "Aliased pinned blob identities")
    for name, digest, size in (
            (config_name, refs["config"], refs["config_size"]),
            (layer_name, refs["layer"], refs["layer_size"]),
            (manifest_name, refs["oci_manifest"], refs["oci_manifest_size"])):
        pinned_member(entries, name, digest, size)
    report["checks"]["pinned_config_manifest_layer_bytes_and_sizes"] = True
    core.need(manifest_name in small and "index.json" in small, "Explicit OCI JSON missing")
    manifest = core.json_object(small[manifest_name])
    core.need(isinstance(manifest, dict) and set(manifest) ==
              {"schemaVersion", "mediaType", "config", "layers"} and
              type(manifest["schemaVersion"]) is int and manifest["schemaVersion"] == 2
              and manifest["mediaType"] == "application/vnd.oci.image.manifest.v1+json"
              and isinstance(manifest["layers"], list) and len(manifest["layers"]) == 1,
              "Unexpected pinned OCI manifest schema")
    exact_descriptor(manifest["config"], refs["config"], refs["config_size"],
                     "application/vnd.oci.image.config.v1+json")
    exact_descriptor(manifest["layers"][0], refs["layer"], refs["layer_size"],
                     "application/vnd.oci.image.layer.v1.tar")
    index = core.json_object(small["index.json"])
    core.need(isinstance(index, dict) and set(index) == {"schemaVersion", "mediaType", "manifests"}
              and type(index["schemaVersion"]) is int and index["schemaVersion"] == 2
              and index["mediaType"] == "application/vnd.oci.image.index.v1+json"
              and isinstance(index["manifests"], list) and len(index["manifests"]) == 1,
              "Unexpected OCI index schema")
    exact_descriptor(index["manifests"][0], refs["oci_manifest"], refs["oci_manifest_size"],
                     "application/vnd.oci.image.manifest.v1+json")
    report["checks"]["explicit_index_to_pinned_manifest_to_layer"] = True

    # Run the unchanged v2 gate on the FULL inventory and retain its rejection.
    try:
        core.docker_binding(entries, small, refs)
    except core.Invalid as error:
        report["B_strict_whole_archive"]["new_strict_binding_check"] = {
            "status": "ERROR", "returncode": 20, "error": str(error),
            "full_outer_inventory_supplied": True,
            "stage": "unchanged v2 docker_binding, not a new historical v2 CLI receipt",
        }
    else:
        raise core.Invalid("Expected persistent strict whole-archive refusal not observed")

    pinned_member(entries, auxiliary_name, refs["auxiliary"], refs["auxiliary_size"])
    # This graph-only view has NO whole-archive conformity meaning. Only this
    # exact pinned anomaly is omitted from the graph view, never from the report.
    graph_entries = {n: r for n, r in entries.items() if n != auxiliary_name}
    selected, binding = core.docker_binding(graph_entries, small, refs)
    core.need(selected == layer_name, "Docker and explicit pinned OCI layer disagree")
    report["checks"]["docker_and_pinned_oci_graph_agree"] = True
    binding["scope"] = "EXPLICIT_PRINCIPAL_GRAPH_ONLY_NOT_WHOLE_ARCHIVE"
    binding["pinned_oci_manifest_path"] = manifest_name
    return selected, binding


def evaluate(archive_path, sums_path, metadata_path, refs=None):
    refs = dict(REFERENCES if refs is None else refs)
    report = base_report(refs)
    try:
        expected, hashes = core.inventories(sums_path, metadata_path, refs, report["observed_sha256"])
        report["checks"]["inventories_authenticated_and_path_sets_valid"] = True
        with core.open_input(archive_path) as stream:
            before = core.fingerprint(stream)
            report["observed_sha256"]["archive"] = core.digest_stream(stream)
            core.need(report["observed_sha256"]["archive"] == refs["archive"],
                      "Exact complete archive SHA-256 mismatch")
            report["checks"]["complete_archive_authenticated_before_tar"] = True
            entries, small, coverage, _, _ = core.outer_pass(stream, refs)
            report["outer_entries"], report["outer_coverage"] = entries, coverage
            report["observed_sha256"]["outer_regular_entries"] = {
                n: r["sha256"] for n, r in sorted(entries.items()) if r["type"] == "file"}
            auxiliary_name = "blobs/sha256/" + refs["auxiliary"]
            if auxiliary_name in entries:
                report["B_strict_whole_archive"]["anomalies"].append({
                    "path": auxiliary_name, "sha256": entries[auxiliary_name].get("sha256"),
                    "size": entries[auxiliary_name]["size"],
                    "digest_matches_blob_name": entries[auxiliary_name].get("sha256") == refs["auxiliary"],
                    "reason": "OUTSIDE_EXPECTED_PINNED_PRINCIPAL_GRAPH",
                    "approved": False, "used_to_identify_layer": False,
                })
            layer_name, binding = scoped_binding(entries, small, refs, report)
            report["principal_graph_binding"] = binding
            again, _, coverage2, rows, layer_coverage = core.outer_pass(stream, refs, layer_name)
            core.need(again == entries and coverage2 == coverage, "Archive changed between passes")
            core.need(before == core.fingerprint(stream), "Archive changed during measurement")
            report["checks"]["all_passes_same_complete_archive_bytes"] = True
            report["layer_coverage"] = layer_coverage
            result, metadata_code = core.compare_rows(expected, hashes, rows)
            result["directory_comparison"] = {
                "expected_directories_including_root": sum(r["type"] == "directory" for r in expected.values()),
                "layer_directories": sum(r["type"] == "directory" for r in rows.values()),
                "missing_nonroot": result["differences"]["missing_nonroot_directories"],
                "root_absent": result["root_directory"]["absent_from_layer"],
                "extra_directories": sorted(n for n in set(rows) - set(expected)
                                             if rows[n]["type"] == "directory"),
                "directory_type_mismatches": [r for r in result["differences"]["type"]
                                              if "directory" in (r["expected"], r["actual"])],
            }
            report["comparison"] = result
            report["controlled_metadata_scope_returncode"] = metadata_code
            equal = result["regular_contents_equal"]
            report["A_regular_layer_contents"] = {
                "decision": "REGULAR_LAYER_CONTENTS_IDENTICAL_ONLY" if equal else
                            "REGULAR_LAYER_CONTENTS_DIFFERENT",
                "measurement_complete": True, "scope_returncode": 0 if equal else 10,
                "regular_contents_equal": equal,
                "expected_regular_paths": len(hashes),
                "complete_metadata_equality_established": False,
            }
            report["status"] = "REVIEW_ONLY_BLOCKED"
    except core.Incomplete as error:
        report["A_regular_layer_contents"]["scope_returncode"] = 30
        report.update(status="CONTROL_INCOMPLETE", error=str(error))
    except (core.Invalid, OSError, ValueError, KeyError, TypeError, AttributeError, OverflowError) as error:
        report.update(status="ERROR", error=type(error).__name__ + ": " + str(error))
    return report


def verify_release(root, anchor):
    sealed = core.verify_release(root, anchor)
    core.need({"layer_contents.py", "test_layer_contents.py"}.issubset(sealed),
              "Unsealed scoped code/tests")
    return sealed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--sums", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--release-anchor", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).absolute().parent
    out = None
    report = base_report(dict(REFERENCES))
    try:
        for path in (args.archive, args.sums, args.metadata, args.out):
            core.need(path.is_absolute(), "Absolute input/output paths required")
        out_abs = Path(os.path.abspath(args.out))
        for source in (args.archive, args.sums, args.metadata, root / "SHA256SUMS"):
            parent = Path(os.path.abspath(source)).parent
            core.need(out_abs not in source.parents and out_abs != parent
                      and parent not in out_abs.parents, "Independent evidence directory required")
        observed_code = {n: core.digest(root / n) for n in ("layer_contents.py", "comparator.py")}
        out = core.new_directory(args.out)
        start = {"argv": sys.orig_argv, "parameters": {k: str(v) for k, v in vars(args).items()},
                 "cwd": os.getcwd(), "python": sys.version, "python_executable": sys.executable,
                 "start_ns": time.time_ns(), "complete": False, "returncode": None,
                 "code_sha256_observed": observed_code}
        core.write_new(out / "started.json", core.encode(start))
        core.need(sys.version_info[:2] == (3, 11), "Python 3.11 required; no installation")
        sealed = verify_release(root, args.release_anchor)
        report = evaluate(args.archive, args.sums, args.metadata)
        report["code_sha256"] = {n: sealed[n] for n in ("layer_contents.py", "comparator.py")}
        report["release_manifest_sha256"] = args.release_anchor
    except Exception as error:
        report.update(status="ERROR", error=type(error).__name__ + ": " + str(error))
    stdout = core.encode({k: report[k] for k in ("status", "decision", "returncode",
                                                "A_regular_layer_contents")})
    stderr = (report.get("error", "") + ("\n" if "error" in report else "")).encode("utf-8")
    if out is not None:
        core.write_new(out / "report.json", core.encode(report))
        core.write_new(out / "stdout", stdout)
        core.write_new(out / "stderr", stderr)
        receipt = dict(start, complete=True, returncode=20, end_ns=time.time_ns(),
                       sha256={n: core.digest(out / n) for n in
                               ("started.json", "report.json", "stdout", "stderr")})
        core.write_new(out / "receipt.json", core.encode(receipt))
        names = ("started.json", "report.json", "stdout", "stderr", "receipt.json")
        core.write_new(out / "SHA256SUMS", "".join(
            core.digest(out / n) + "  " + n + "\n" for n in names).encode("ascii"))
        core.write_new(out / "evidence-anchor.json", core.encode({
            "sha256sums": core.digest(out / "SHA256SUMS"), "decision": "REVIEW_ONLY_BLOCKED",
            "external_authentication_required": True}))
    sys.stdout.buffer.write(stdout)
    sys.stderr.buffer.write(stderr)
    return 20


if __name__ == "__main__":
    sys.exit(main())
