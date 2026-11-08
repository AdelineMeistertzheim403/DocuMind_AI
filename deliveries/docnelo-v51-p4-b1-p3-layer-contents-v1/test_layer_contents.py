"""Scoped synthetic measurements; no historical P3 bytes are present."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import unittest
from unittest.mock import patch

import comparator as core
import layer_contents as scoped
import test_comparator as fixtures


class ScopedContentsTests(unittest.TestCase):
    def setUp(self):
        fixtures.ComparatorTests.setUp(self)

    def image(self, rows=None, layer=None, change_index=None, change_manifest=None,
              change_docker=None, extras=(), fmt=tarfile.USTAR_FORMAT):
        layer = fixtures.tar_bytes(fixtures.BASE if rows is None else rows, fmt) if layer is None else layer
        config = core.encode({"os": "linux", "architecture": "amd64",
                              "rootfs": {"type": "layers", "diff_ids": ["sha256:" + fixtures.sha(layer)]}})
        prefix = "blobs/sha256/"
        config_name, layer_name = prefix + fixtures.sha(config), prefix + fixtures.sha(layer)
        config_desc = {"mediaType": "application/vnd.oci.image.config.v1+json",
                       "digest": "sha256:" + fixtures.sha(config), "size": len(config)}
        layer_desc = {"mediaType": "application/vnd.oci.image.layer.v1.tar",
                      "digest": "sha256:" + fixtures.sha(layer), "size": len(layer)}
        manifest = {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
                    "config": config_desc, "layers": [layer_desc]}
        if change_manifest:
            change_manifest(manifest)
        manifest_bytes = core.encode(manifest)
        manifest_name = prefix + fixtures.sha(manifest_bytes)
        index = {"schemaVersion": 2, "mediaType": "application/vnd.oci.image.index.v1+json",
                 "manifests": [{"mediaType": "application/vnd.oci.image.manifest.v1+json",
                                "digest": "sha256:" + fixtures.sha(manifest_bytes),
                                "size": len(manifest_bytes)}]}
        if change_index:
            change_index(index)
        docker = [{"Config": config_name, "RepoTags": None, "Layers": [layer_name],
                   "LayerSources": {"sha256:" + fixtures.sha(layer): copy.deepcopy(layer_desc)}}]
        if change_docker:
            change_docker(docker)
        auxiliary = b'{"unreferenced":"Docker metadata fixture"}'
        auxiliary_name = prefix + fixtures.sha(auxiliary)
        rows = [(layer_name, tarfile.REGTYPE, layer, {}),
                (config_name, tarfile.REGTYPE, config, {}),
                (manifest_name, tarfile.REGTYPE, manifest_bytes, {}),
                (auxiliary_name, tarfile.REGTYPE, auxiliary, {}),
                ("manifest.json", tarfile.REGTYPE, core.encode(docker), {}),
                ("index.json", tarfile.REGTYPE, core.encode(index), {}),
                ("oci-layout", tarfile.REGTYPE, core.encode({"imageLayoutVersion": "1.0.0"}), {})]
        self.archive.write_bytes(fixtures.tar_bytes(rows + list(extras)))
        self.refs.update(archive=core.digest(self.archive), config=fixtures.sha(config),
                         config_size=len(config), layer=fixtures.sha(layer), layer_size=len(layer),
                         oci_manifest=fixtures.sha(manifest_bytes), oci_manifest_size=len(manifest_bytes),
                         auxiliary=fixtures.sha(auxiliary), auxiliary_size=len(auxiliary))

    def result(self):
        return scoped.evaluate(self.archive, self.sums, self.meta, self.refs)

    def test_equal_contents_keeps_full_archive_refusal(self):
        self.image()
        strict = core.evaluate(self.archive, self.sums, self.meta, self.refs)
        self.assertEqual(strict["returncode"], 20)
        self.assertIn("Unclaimed outer regular entries", strict["error"])
        report = self.result()
        self.assertEqual(report["returncode"], 20)
        self.assertEqual(report["status"], "REVIEW_ONLY_BLOCKED")
        self.assertEqual(report["A_regular_layer_contents"]["scope_returncode"], 0)
        self.assertTrue(report["A_regular_layer_contents"]["measurement_complete"])
        self.assertEqual(report["B_strict_whole_archive"]["returncode"], 20)
        self.assertEqual(len(report["B_strict_whole_archive"]["anomalies"]), 1)
        self.assertFalse(report["B_strict_whole_archive"]["anomalies"][0]["approved"])
        self.assertTrue(report["outer_coverage"]["all_bytes_accounted"])
        self.assertTrue(report["layer_coverage"]["all_bytes_accounted"])
        self.assertEqual(core.encode(report), core.encode(self.result()))
        self.assertFalse(report["formal_b1_contents_closed"])
        self.assertFalse(any(report["go"].values()))
        self.assertFalse(report["C_p4_and_provenance"]["qualification_granted"])

    def test_regular_identity_is_not_metadata_identity(self):
        rows = [(n, k, d, {"uid": 0, "gid": 0, "mode": 0o700 if k == tarfile.DIRTYPE else 0o600})
                for n, k, d, _ in fixtures.BASE[1:]]
        self.image(rows)
        report = self.result()
        self.assertEqual(report["A_regular_layer_contents"]["scope_returncode"], 0)
        comparison = report["comparison"]
        self.assertTrue(comparison["root_directory"]["absent_from_layer"])
        self.assertEqual(comparison["difference_counts"]["missing_regular"], 0)
        self.assertEqual(comparison["difference_counts"]["uid_gid"], 3)
        self.assertEqual(comparison["difference_counts"]["permissions"], 3)
        self.assertFalse(comparison["complete_metadata_equality_established"])
        self.assertEqual(report["controlled_metadata_scope_returncode"], 10)
        self.assertEqual(comparison["directory_comparison"]["expected_directories_including_root"], 2)
        self.assertEqual(comparison["directory_comparison"]["layer_directories"], 1)
        self.image(fixtures.BASE + [("extra-directory", tarfile.DIRTYPE, b"", {})])
        report = self.result()
        self.assertEqual(report["A_regular_layer_contents"]["scope_returncode"], 0)
        self.assertEqual(report["comparison"]["directory_comparison"]["extra_directories"],
                         ["extra-directory"])

    def test_missing_changed_extra_and_hardlink_are_not_regular_identity(self):
        variants = [
            fixtures.BASE[:-1],
            fixtures.BASE[:-1] + [("lib/b", tarfile.REGTYPE, b"modified", {})],
            fixtures.BASE[:-1] + [("lib/c", tarfile.REGTYPE, b"beta", {})],
            fixtures.BASE[:-1] + [("lib/b", tarfile.LNKTYPE, b"", {"target": "lib/a"})],
        ]
        for rows in variants:
            with self.subTest(rows=rows[-1][0]):
                self.image(rows)
                report = self.result()
                self.assertEqual(report["returncode"], 20)
                self.assertEqual(report["A_regular_layer_contents"]["scope_returncode"], 10)
                self.assertTrue(report["A_regular_layer_contents"]["measurement_complete"])
                self.assertEqual(report["B_strict_whole_archive"]["returncode"], 20)

    def test_wrong_pinned_member_digest_and_sizes(self):
        for key, value in (("oci_manifest", "0" * 64), ("config", "0" * 64),
                           ("layer", "0" * 64), ("oci_manifest_size", 403),
                           ("config_size", 836), ("layer_size", 322534912),
                           ("auxiliary_size", 829), ("auxiliary", "0" * 64)):
            with self.subTest(key=key):
                self.image()
                self.refs[key] = value
                report = self.result()
                self.assertFalse(report["A_regular_layer_contents"]["measurement_complete"])
                self.assertEqual(report["A_regular_layer_contents"]["scope_returncode"], 20)

    def test_no_layer_discovery_outside_explicit_graph(self):
        for change in (
                lambda obj: obj["manifests"][0].update(digest="sha256:" + "0" * 64),
                lambda obj: obj["manifests"].append(copy.deepcopy(obj["manifests"][0])),
                lambda obj: obj["manifests"][0].update(size=True),
                lambda obj: obj["manifests"][0].update(urls=["offline"]),
                lambda obj: obj.update(mediaType="application/unknown")):
            self.image(change_index=change)
            self.assertFalse(self.result()["A_regular_layer_contents"]["measurement_complete"])
        for change in (
                lambda obj: obj["layers"][0].update(digest="sha256:" + "0" * 64),
                lambda obj: obj["config"].update(size=999),
                lambda obj: obj["layers"][0].update(mediaType="application/vnd.oci.image.layer.v1.tar+gzip"),
                lambda obj: obj["layers"].append(copy.deepcopy(obj["layers"][0]))):
            self.image(change_manifest=change)
            self.assertFalse(self.result()["A_regular_layer_contents"]["measurement_complete"])
        self.image(change_docker=lambda obj: obj[0].update(Layers=["other"]))
        self.assertFalse(self.result()["A_regular_layer_contents"]["measurement_complete"])

    def test_unknown_extra_blob_or_directory_not_accepted(self):
        data = b'{"other":"unreferenced"}'
        for extra in (
                ("blobs/sha256/" + fixtures.sha(data), tarfile.REGTYPE, data, {}),
                ("unknown", tarfile.REGTYPE, b"x", {}),
                ("unknown", tarfile.DIRTYPE, b"", {})):
            self.image(extras=[extra])
            report = self.result()
            self.assertFalse(report["A_regular_layer_contents"]["measurement_complete"])
            self.assertEqual(report["B_strict_whole_archive"]["returncode"], 20)
            self.assertEqual(len(report["B_strict_whole_archive"]["anomalies"]), 1)

    def test_blob_digest_must_match_name_even_for_auxiliary(self):
        self.image(extras=[("blobs/sha256/" + "0" * 64, tarfile.REGTYPE, b"wrong", {})])
        report = self.result()
        self.assertFalse(report["A_regular_layer_contents"]["measurement_complete"])
        self.assertIn("OCI blob pathname digest mismatch", report["error"])

    def test_archive_and_inventories_before_interpretation(self):
        self.image()
        self.refs["archive"] = "0" * 64
        with patch.object(core, "outer_pass", side_effect=AssertionError("must not parse")):
            self.assertFalse(self.result()["A_regular_layer_contents"]["measurement_complete"])
        for path in (self.sums, self.meta):
            self.image()
            original = path.read_bytes()
            path.write_bytes(original + b"\n")
            with patch.object(core, "outer_pass", side_effect=AssertionError("must not parse")):
                self.assertFalse(self.result()["A_regular_layer_contents"]["measurement_complete"])
            path.write_bytes(original)

    def test_tar_dangerous_duplicate_special_and_trailer_refused(self):
        for rows in (
                fixtures.BASE + [("../escape", tarfile.REGTYPE, b"x", {})],
                fixtures.BASE + [("./lib/a", tarfile.REGTYPE, b"alpha", {})],
                fixtures.BASE + [("device", tarfile.CHRTYPE, b"", {})]):
            self.image(rows)
            self.assertFalse(self.result()["A_regular_layer_contents"]["measurement_complete"])
        self.image(layer=fixtures.tar_bytes(fixtures.BASE) + b"hidden")
        self.assertFalse(self.result()["A_regular_layer_contents"]["measurement_complete"])

    def test_unsupported_pax_keeps_control_incomplete(self):
        self.image(fixtures.BASE + [("extra", tarfile.REGTYPE, b"x",
                                    {"pax": {"SCHILY.xattr.user.test": "value"}})],
                   fmt=tarfile.PAX_FORMAT)
        report = self.result()
        self.assertEqual(report["A_regular_layer_contents"]["scope_returncode"], 30)
        self.assertEqual(report["returncode"], 20)
        self.assertEqual(report["status"], "CONTROL_INCOMPLETE")

    @unittest.skipUnless(sys.version_info[:2] == (3, 11), "CLI requires installed Python 3.11")
    def test_cli_receipt_keeps_code20_and_never_overwrites(self):
        self.image()
        release = self.root / "scoped-release"
        release.mkdir()
        root = Path(scoped.__file__).parent
        for name in ("comparator.py", "test_comparator.py", "test_layer_contents.py"):
            (release / name).write_bytes((root / name).read_bytes())
        source = (root / "layer_contents.py").read_bytes().replace(
            b"REFERENCES = {", b"REFERENCES = " + repr(self.refs).encode() + b"\n_UNUSED = {", 1)
        (release / "layer_contents.py").write_bytes(source)
        manifest = "".join(core.digest(release / n) + "  " + n + "\n" for n in sorted(
            p.name for p in release.iterdir())).encode()
        (release / "SHA256SUMS").write_bytes(manifest)
        out = self.root / "scoped-proof"
        argv = [sys.executable, "-I", "-B", str(release / "layer_contents.py"),
                "--archive", str(self.archive), "--sums", str(self.sums), "--metadata", str(self.meta),
                "--release-anchor", fixtures.sha(manifest), "--out", str(out)]
        result = subprocess.run(argv, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 20, result.stderr)
        report = json.loads((out / "report.json").read_bytes())
        receipt = json.loads((out / "receipt.json").read_bytes())
        self.assertTrue(receipt["complete"])
        self.assertEqual(receipt["returncode"], 20)
        self.assertEqual(receipt["argv"], argv)
        self.assertEqual(report["A_regular_layer_contents"]["scope_returncode"], 0)
        self.assertEqual(result.stdout, (out / "stdout").read_bytes())
        self.assertEqual(result.stderr, (out / "stderr").read_bytes())
        for n, value in receipt["sha256"].items():
            self.assertEqual(core.digest(out / n), value)
        before = {p.name: p.read_bytes() for p in out.iterdir()}
        repeat = subprocess.run(argv, capture_output=True, timeout=30)
        self.assertEqual(repeat.returncode, 20)
        self.assertEqual(before, {p.name: p.read_bytes() for p in out.iterdir()})
        argv[-1] = str(self.inputs / "forbidden")
        result = subprocess.run(argv, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 20)
        self.assertFalse(Path(argv[-1]).exists())


if __name__ == "__main__":
    unittest.main()
