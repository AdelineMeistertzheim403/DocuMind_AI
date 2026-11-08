"""Synthetic fixtures only: never opens historical P3 inputs or invokes Docker."""
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import comparator as c


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tar_bytes(rows, fmt=tarfile.USTAR_FORMAT):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w", format=fmt) as archive:
        for name, kind, data, options in rows:
            item = tarfile.TarInfo(name)
            item.type = kind
            item.mode = options.get("mode", 0o755 if kind == tarfile.DIRTYPE else 0o644)
            item.uid = options.get("uid", 1000)
            item.gid = options.get("gid", 1000)
            item.linkname = options.get("target", "")
            item.pax_headers = options.get("pax", {})
            item.size = len(data) if kind == tarfile.REGTYPE else 0
            archive.addfile(item, io.BytesIO(data) if item.size else None)
    return out.getvalue()


BASE = [
    (".", tarfile.DIRTYPE, b"", {}),
    ("lib", tarfile.DIRTYPE, b"", {}),
    ("lib/a", tarfile.REGTYPE, b"alpha", {}),
    ("lib/b", tarfile.REGTYPE, b"beta", {}),
]


class ComparatorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.inputs = self.root / "inputs"
        self.inputs.mkdir()
        self.sums = self.inputs / "ROOTFS-SHA256SUMS"
        self.meta = self.inputs / "ROOTFS-METADATA.txt"
        self.archive = self.inputs / "image.tar"
        self.sums.write_bytes((sha(b"alpha") + "  ./lib/a\n" +
                               sha(b"beta") + "  ./lib/b\n").encode())
        self.meta.write_bytes(b"d 755 1000:1000 .\nd 755 1000:1000 ./lib\n"
                              b"f 644 1000:1000 ./lib/a\nf 644 1000:1000 ./lib/b\n")
        self.refs = {"sums": c.digest(self.sums), "metadata": c.digest(self.meta),
                     "files": 2, "directories": 2}

    def image(self, rows=None, layer=None, outer_extra=(), config_change=None,
              manifest_change=None, fmt=tarfile.USTAR_FORMAT, oci=False):
        layer = tar_bytes(BASE if rows is None else rows, fmt) if layer is None else layer
        config = {"architecture": "amd64", "os": "linux",
                  "rootfs": {"type": "layers", "diff_ids": ["sha256:" + sha(layer)]}}
        if config_change:
            config_change(config)
        config_data = c.encode(config)
        config_name = sha(config_data) + ".json"
        layer_name = "layer/layer.tar"
        if oci:
            config_name = "blobs/sha256/" + sha(config_data)
            layer_name = "blobs/sha256/" + sha(layer)
        manifest = [{"Config": config_name, "RepoTags": ["fixture:test"], "Layers": [layer_name]}]
        if manifest_change:
            manifest_change(manifest)
        items = [(layer_name, tarfile.REGTYPE, layer, {}),
                 (config_name, tarfile.REGTYPE, config_data, {}),
                 ("manifest.json", tarfile.REGTYPE, c.encode(manifest), {})]
        if oci:
            desc_config = {"digest": "sha256:" + sha(config_data), "size": len(config_data),
                           "mediaType": "application/vnd.oci.image.config.v1+json"}
            desc_layer = {"digest": "sha256:" + sha(layer), "size": len(layer),
                          "mediaType": "application/vnd.oci.image.layer.v1.tar"}
            manifest_data = c.encode({"schemaVersion": 2, "config": desc_config,
                                      "layers": [desc_layer]})
            index = {"schemaVersion": 2, "manifests": [{
                "digest": "sha256:" + sha(manifest_data), "size": len(manifest_data),
                "mediaType": "application/vnd.oci.image.manifest.v1+json"}]}
            items.extend([
                ("blobs/sha256/" + sha(manifest_data), tarfile.REGTYPE, manifest_data, {}),
                ("index.json", tarfile.REGTYPE, c.encode(index), {}),
                ("oci-layout", tarfile.REGTYPE, c.encode({"imageLayoutVersion": "1.0.0"}), {}),
            ])
        self.archive.write_bytes(tar_bytes(items + list(outer_extra)))
        self.refs.update(archive=c.digest(self.archive), config=sha(config_data), layer=sha(layer))

    def result(self):
        return c.evaluate(self.archive, self.sums, self.meta, self.refs)

    def test_equal_and_deterministic(self):
        self.image()
        first = self.result()
        self.assertEqual(first["returncode"], 0)
        self.assertTrue(first["regular_contents_equal"])
        self.assertFalse(first["complete_metadata_equality_established"])
        self.assertEqual(c.encode(first), c.encode(self.result()))
        self.assertEqual(first["layer_coverage"]["physical_headers"], 4)
        self.assertTrue(first["outer_coverage"]["all_bytes_accounted"])
        self.assertFalse(any(first["go"].values()))

    def test_historical_root_and_ownership_pattern(self):
        rows = [(n, k, d, {"uid": 0, "gid": 0}) for n, k, d, _ in BASE[1:]]
        self.image(rows)
        report = self.result()
        self.assertEqual(report["returncode"], 10)
        self.assertTrue(report["root_directory"]["absent_from_layer"])
        self.assertEqual(report["difference_counts"]["missing_regular"], 0)
        self.assertEqual(report["difference_counts"]["uid_gid"], 3)
        self.assertTrue(report["regular_contents_equal"])
        self.assertFalse(report["all_controlled_metadata_equal"])

    def test_missing_file(self):
        self.image(BASE[:-1])
        report = self.result()
        self.assertEqual(report["returncode"], 10)
        self.assertEqual(report["differences"]["missing_regular"], ["lib/b"])
        self.assertFalse(report["regular_contents_equal"])

    def test_modified_content(self):
        self.image(BASE[:-1] + [("lib/b", tarfile.REGTYPE, b"changed", {})])
        report = self.result()
        self.assertEqual(report["returncode"], 10)
        self.assertEqual(report["differences"]["content"][0]["path"], "lib/b")

    def test_same_count_different_path(self):
        self.image(BASE[:-1] + [("lib/c", tarfile.REGTYPE, b"beta", {})])
        report = self.result()
        self.assertEqual(report["differences"]["missing_regular"], ["lib/b"])
        self.assertEqual(report["differences"]["extra_entries"], ["lib/c"])
        self.assertEqual(report["returncode"], 10)

    def test_duplicate_layer(self):
        self.image(BASE + [("./lib/a", tarfile.REGTYPE, b"alpha", {})])
        self.assertEqual(self.result()["returncode"], 20)

    def test_dangerous_paths(self):
        for name in ("../escape", "/escape", "./../escape", "lib//a", "lib/./a",
                     "C:escape", "lib\\escape", "lib/.wh.a", "././lib/a"):
            with self.subTest(name=name):
                self.image(BASE + [(name, tarfile.REGTYPE, b"bad", {})])
                self.assertEqual(self.result()["returncode"], 20)

    def test_incorrect_layer_anchor(self):
        self.image()
        self.refs["layer"] = "0" * 64
        report = self.result()
        self.assertEqual(report["returncode"], 20)
        self.assertIn("Layer", report["error"])

    def test_altered_inventories(self):
        for path in (self.sums, self.meta):
            self.image()
            original = path.read_bytes()
            path.write_bytes(original + b"\n")
            with self.subTest(path=path.name):
                self.assertEqual(self.result()["returncode"], 20)
            path.write_bytes(original)

    def test_invalid_anchored_inventory_sets_and_duplicates(self):
        self.image()
        for data in (self.sums.read_bytes().splitlines(keepends=True)[0],
                     self.sums.read_bytes() + self.sums.read_bytes().splitlines(keepends=True)[0],
                     (sha(b"beta") + "  ../escape\n").encode()):
            self.sums.write_bytes(data)
            self.refs["sums"] = c.digest(self.sums)
            self.assertEqual(self.result()["returncode"], 20)

    def test_unknown_metadata_format(self):
        self.image()
        self.meta.write_bytes(b"unattested format\n")
        self.refs["metadata"] = c.digest(self.meta)
        self.assertEqual(self.result()["returncode"], 30)

    def test_duplicate_metadata_and_parent_alias(self):
        self.image()
        original = self.meta.read_bytes()
        for data in (original + b"d 755 1000:1000 ./lib\n",
                     original.replace(b"d 755 1000:1000 ./lib\n", b"d 755 1000:1000 ./other\n")):
            self.meta.write_bytes(data)
            self.refs["metadata"] = c.digest(self.meta)
            self.assertEqual(self.result()["returncode"], 20)
        self.meta.write_bytes(original)
        self.refs["metadata"] = c.digest(self.meta)
        self.image(BASE[:-1] + [("lib/b", tarfile.DIRTYPE, b"", {}),
                                ("lib/b/child", tarfile.REGTYPE, b"x", {})])
        report = self.result()
        self.assertEqual(report["returncode"], 10)
        self.assertEqual(report["difference_counts"]["type"], 1)
        self.image(BASE + [("lib/a/child", tarfile.REGTYPE, b"x", {})])
        self.assertEqual(self.result()["returncode"], 20)

    def test_permissions_type_and_links(self):
        self.image(BASE[:-1] + [("lib/b", tarfile.LNKTYPE, b"",
                                {"target": "lib/a", "mode": 0o600})])
        report = self.result()
        self.assertEqual(report["returncode"], 10)
        for key in ("type", "permissions", "links", "content"):
            self.assertEqual(report["difference_counts"][key], 1)
        self.assertEqual(report["layer_entries"]["lib/b"]["mode"], 0o600)

    def test_unsafe_symlink_and_cyclic_hardlinks(self):
        variants = [
            BASE + [("link", tarfile.SYMTYPE, b"", {"target": "../escape"})],
            BASE[:2] + [("lib/a", tarfile.LNKTYPE, b"", {"target": "lib/b"}),
                        ("lib/b", tarfile.LNKTYPE, b"", {"target": "lib/a"})],
        ]
        for rows in variants:
            self.image(rows)
            self.assertEqual(self.result()["returncode"], 20)

    def test_special_file(self):
        self.image(BASE + [("device", tarfile.CHRTYPE, b"", {})])
        self.assertEqual(self.result()["returncode"], 20)

    def test_duplicate_outer_unclaimed_and_unsafe_outer(self):
        for name in ("manifest.json", "unexpected", "../outside"):
            with self.subTest(name=name):
                self.image(outer_extra=[(name, tarfile.REGTYPE, b"{}", {})])
                self.assertEqual(self.result()["returncode"], 20)
        self.image(outer_extra=[("unclaimed", tarfile.DIRTYPE, b"", {})])
        self.assertEqual(self.result()["returncode"], 20)

    def test_wrong_config_and_diff_id(self):
        self.image()
        self.refs["config"] = "0" * 64
        self.assertEqual(self.result()["returncode"], 20)
        self.image(config_change=lambda obj: obj["rootfs"].update(diff_ids=["sha256:" + "0" * 64]))
        self.assertEqual(self.result()["returncode"], 20)

    def test_manifest_wrong_binding_and_duplicate_json(self):
        self.image(manifest_change=lambda obj: obj[0].update(Layers=["wrong/layer.tar"]))
        self.assertEqual(self.result()["returncode"], 20)
        self.image(outer_extra=[("other.json", tarfile.REGTYPE, b'{"a":1,"a":2}', {})])
        self.assertEqual(self.result()["returncode"], 20)
        with self.assertRaises(c.Invalid):
            c.json_object(b'{"Config":"a","Config":"b"}')

    def test_trailing_data_and_truncation(self):
        layer = tar_bytes(BASE)
        for data in (layer + b"hidden", layer[:1024], layer[:-1]):
            self.image(layer=data)
            self.assertEqual(self.result()["returncode"], 20)
        self.image()
        self.archive.write_bytes(self.archive.read_bytes() + b"x")
        self.refs["archive"] = c.digest(self.archive)
        self.assertEqual(self.result()["returncode"], 20)

    def test_corrupt_header_padding_and_nonregular_payload(self):
        data = bytearray(tar_bytes(BASE))
        data[0] ^= 1
        self.image(layer=bytes(data))
        self.assertEqual(self.result()["returncode"], 20)
        data = bytearray(tar_bytes(BASE))
        data[1536 + len(b"alpha")] = 1
        self.image(layer=bytes(data))
        self.assertEqual(self.result()["returncode"], 20)
        out = io.BytesIO()
        with tarfile.open(fileobj=out, mode="w", format=tarfile.USTAR_FORMAT) as archive:
            item = tarfile.TarInfo("lib")
            item.type, item.size = tarfile.DIRTYPE, 1
            archive.addfile(item, io.BytesIO(b"x"))
        self.image(layer=out.getvalue())
        self.assertEqual(self.result()["returncode"], 20)

    def test_pax_timestamp_recorded_xattr_incomplete(self):
        self.image(BASE[:-1] + [("lib/b", tarfile.REGTYPE, b"beta",
                                {"pax": {"mtime": "1.25"}})], fmt=tarfile.PAX_FORMAT)
        report = self.result()
        self.assertEqual(report["returncode"], 0)
        self.assertEqual(report["layer_entries"]["lib/b"]["pax"], {"mtime": "1.25"})
        self.assertEqual(len(report["layer_coverage"]["extension_headers"]), 1)
        self.image(BASE[:-1] + [("lib/b", tarfile.REGTYPE, b"beta",
                                {"pax": {"SCHILY.xattr.user.test": "value"}})],
                   fmt=tarfile.PAX_FORMAT)
        self.assertEqual(self.result()["returncode"], 30)

    def test_gnu_long_path_and_pax_path_duplicate(self):
        longname = "lib/" + "a" * 110
        self.image(BASE + [(longname, tarfile.REGTYPE, b"x", {})], fmt=tarfile.GNU_FORMAT)
        report = self.result()
        self.assertEqual(report["returncode"], 10)
        self.assertEqual(report["differences"]["extra_entries"], [longname])
        self.image(BASE + [("other", tarfile.REGTYPE, b"x", {"pax": {"path": "lib/a"}})],
                   fmt=tarfile.PAX_FORMAT)
        self.assertEqual(self.result()["returncode"], 20)

    def test_oci_layout_and_legacy_ancillary(self):
        self.image(oci=True)
        self.assertEqual(self.result()["returncode"], 0)
        self.image(outer_extra=[("layer/VERSION", tarfile.REGTYPE, b"1.0", {}),
                                ("layer/json", tarfile.REGTYPE, b"{}", {})])
        self.assertEqual(self.result()["returncode"], 0)

    def test_archive_hash_before_tar_parse(self):
        self.image()
        self.refs["archive"] = "0" * 64
        with patch.object(c, "outer_pass", side_effect=AssertionError("must not parse")):
            self.assertEqual(self.result()["returncode"], 20)

    def test_stream_reads_are_bounded(self):
        class Bounded(io.BytesIO):
            def read(self, size=-1):
                if not 0 <= size <= c.CHUNK:
                    raise AssertionError("unbounded read")
                return super().read(size)
        rows, coverage = c.layer_inventory(Bounded(tar_bytes(BASE)))
        self.assertEqual(len(rows), 4)
        self.assertTrue(coverage["all_bytes_accounted"])

    def test_release_manifest_and_no_overwrite(self):
        release = self.root / "release"
        release.mkdir()
        for name in ("comparator.py", "test_comparator.py"):
            (release / name).write_bytes(b"fixture\n")
        data = "".join(c.digest(release / n) + "  " + n + "\n"
                       for n in ("comparator.py", "test_comparator.py")).encode()
        (release / "SHA256SUMS").write_bytes(data)
        c.verify_release(release, sha(data))
        (release / "comparator.py").write_bytes(b"changed")
        with self.assertRaises(c.Invalid):
            c.verify_release(release, sha(data))
        with self.assertRaises(c.Invalid):
            c.new_directory(release)

    @unittest.skipUnless(sys.platform == "linux", "Native symlink semantics")
    def test_symlink_input_and_release_refused(self):
        self.image()
        linked = self.root / "linked"
        linked.symlink_to(self.sums)
        report = c.evaluate(self.archive, linked, self.meta, self.refs)
        self.assertEqual(report["returncode"], 20)
        release = self.root / "release"
        release.mkdir()
        (release / "comparator.py").symlink_to(Path(c.__file__))
        (release / "SHA256SUMS").write_bytes(b"")
        with self.assertRaises(c.Invalid):
            c.verify_release(release, sha(b""))

    @unittest.skipUnless(sys.version_info[:2] == (3, 11), "CLI requires installed Python 3.11")
    def test_cli_evidence_receipt_and_existing_directory(self):
        self.image()
        release = self.root / "cli"
        release.mkdir()
        original = Path(c.__file__).read_bytes()
        # Fixture anchors replace only the new temporary comparator, never delivery/P3 bytes.
        source = original.replace(b"REFERENCES = {", b"REFERENCES = " +
                                  repr(self.refs).encode() + b"\n_UNUSED = {", 1)
        (release / "comparator.py").write_bytes(source)
        (release / "test_comparator.py").write_bytes(b"fixture")
        manifest = "".join(c.digest(release / n) + "  " + n + "\n"
                           for n in ("comparator.py", "test_comparator.py")).encode()
        (release / "SHA256SUMS").write_bytes(manifest)
        out = self.root / "proof"
        command = [sys.executable, "-I", "-B", str(release / "comparator.py"),
                   "--archive", str(self.archive), "--sums", str(self.sums),
                   "--metadata", str(self.meta), "--release-anchor", sha(manifest),
                   "--out", str(out)]
        result = subprocess.run(command, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((out / "stdout").read_bytes(), result.stdout)
        self.assertEqual((out / "stderr").read_bytes(), result.stderr)
        receipt = json.loads((out / "receipt.json").read_bytes())
        self.assertEqual(receipt["returncode"], 0)
        self.assertEqual(receipt["argv"], command)
        for name, value in receipt["sha256"].items():
            self.assertEqual(c.digest(out / name), value)
        before = {p.name: p.read_bytes() for p in out.iterdir()}
        repeat = subprocess.run(command, capture_output=True, timeout=30)
        self.assertEqual(repeat.returncode, 20)
        self.assertEqual(before, {p.name: p.read_bytes() for p in out.iterdir()})

    @unittest.skipUnless(sys.version_info[:2] == (3, 11), "CLI requires installed Python 3.11")
    def test_cli_differences_error_incomplete_and_input_directory_guard(self):
        for code, rows, fmt in (
                (10, BASE[:-1], tarfile.USTAR_FORMAT),
                (20, BASE + [("../escape", tarfile.REGTYPE, b"x", {})], tarfile.USTAR_FORMAT),
                (30, BASE + [("extra", tarfile.REGTYPE, b"x",
                             {"pax": {"SCHILY.xattr.user.test": "value"}})], tarfile.PAX_FORMAT)):
            with self.subTest(code=code):
                self.image(rows, fmt=fmt)
                release = self.root / ("cli" + str(code))
                release.mkdir()
                source = Path(c.__file__).read_bytes().replace(
                    b"REFERENCES = {", b"REFERENCES = " + repr(self.refs).encode() +
                    b"\n_UNUSED = {", 1)
                (release / "comparator.py").write_bytes(source)
                (release / "test_comparator.py").write_bytes(b"fixture")
                data = "".join(c.digest(release / n) + "  " + n + "\n"
                               for n in ("comparator.py", "test_comparator.py")).encode()
                (release / "SHA256SUMS").write_bytes(data)
                out = self.root / ("proof" + str(code))
                command = [sys.executable, "-I", "-B", str(release / "comparator.py"),
                           "--archive", str(self.archive), "--sums", str(self.sums),
                           "--metadata", str(self.meta), "--release-anchor", sha(data),
                           "--out", str(out)]
                result = subprocess.run(command, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, code, result.stderr)
                report = json.loads((out / "report.json").read_bytes())
                receipt = json.loads((out / "receipt.json").read_bytes())
                self.assertEqual(receipt["returncode"], report["returncode"])
                self.assertEqual(result.stdout, (out / "stdout").read_bytes())
                self.assertEqual(result.stderr, (out / "stderr").read_bytes())
                self.assertFalse(any(report["go"].values()))
                command[-1] = str(self.inputs / ("forbidden" + str(code)))
                result = subprocess.run(command, capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 20)
                self.assertFalse(Path(command[-1]).exists())


if __name__ == "__main__":
    unittest.main()
