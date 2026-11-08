import copy
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common import digest, files, load, sha
from evidence_check import ProofHashMismatch, assess_references, verify_existing
import transfer


class ProofTests(unittest.TestCase):
    def fixture(self, root):
        refs = copy.deepcopy(load(ROOT / 'P4_B1_OBSERVED_REFERENCES.json'))
        for name in refs['artifact_sha256']:
            data = b'{"fixture":true}' if name.endswith('.json') else b'fixture, not historical evidence'
            (root / name).write_bytes(data)
            refs['artifact_sha256'][name] = sha(data)
        return refs

    def test_root_omission_and_uid_changes_do_not_become_full_equality_or_closure(self):
        result = assess_references(load(ROOT / 'P4_B1_OBSERVED_REFERENCES.json'))
        self.assertEqual(result['source_entries'] - result['layer_entries'], 1)
        self.assertTrue(result['missing_root_is_not_file_content_divergence'])
        self.assertTrue(result['reported_regular_file_content_identity_supported'])
        self.assertFalse(result['full_metadata_equality'])
        self.assertFalse(result['formal_b1_contents_closed'])
        self.assertFalse(result['build_go'])

    def test_inconsistent_counts_or_content_difference_cannot_reuse_assessment(self):
        refs = load(ROOT / 'P4_B1_OBSERVED_REFERENCES.json')
        for key, value in (('uid_gid_mismatches', 0), ('content_mismatches', 1),
                           ('missing_entries', ['.', 'missing-file'])):
            changed = copy.deepcopy(refs)
            changed['layer_comparison'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                assess_references(changed)

    def test_hash_success_never_means_schema_review_or_b1_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            result = verify_existing(root, self.fixture(root))
            self.assertEqual(result['status'], 'PASS_ANCHORED_PROOF_BYTES_ONLY')
            self.assertFalse(result['raw_report_schema_and_counter_semantics_validated'])
            self.assertFalse(result['formal_b1_contents_closed'])
            self.assertFalse(result['archive_and_rootfs_rehashed'])

    def test_tampered_copy_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            refs = self.fixture(root)
            (root / 'ROOTFS-METADATA.txt').write_bytes(b'changed')
            with self.assertRaises(ProofHashMismatch):
                verify_existing(root, refs)

    def test_duplicate_json_keys_not_silently_accepted(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            refs = self.fixture(root)
            path = root / 'p3-layer-comparison.json'
            path.write_bytes(b'{"x":1,"x":2}')
            refs['artifact_sha256'][path.name] = digest(path)
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                verify_existing(root, refs)

    def test_missing_proofs_cli_returns_incomplete_not_a_pass(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            proof = root / 'proof'
            proof.mkdir()
            output = root / 'result.json'
            result = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'evidence_check.py'),
                                     '--proof-directory', str(proof), '--out', str(output)],
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 2)
            data = load(output)
            self.assertEqual(data['status'], 'INCOMPLETE_EVIDENCE_REVIEW')
            self.assertFalse(data['formal_b1_contents_closed'])
            self.assertFalse(data['start_go'])


class TransferTests(unittest.TestCase):
    def test_traversal_and_zip_symlink_refused(self):
        for name, mode in (('../outside', stat.S_IFREG), ('link', stat.S_IFLNK)):
            data = io.BytesIO()
            with zipfile.ZipFile(data, 'w') as archive:
                item = zipfile.ZipInfo(name)
                item.external_attr = (mode | 0o644) << 16
                archive.writestr(item, b'target')
            with self.subTest(name=name), self.assertRaises(ValueError):
                transfer.checked_zip(data.getvalue())

    def test_relative_destination_refused(self):
        with self.assertRaises(ValueError):
            transfer.destination(Path('relative-new-directory'))

    def test_roundtrip_and_external_manifest_tamper(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder)
            source = parent / 'source'
            source.mkdir()
            for name in ('transfer.py', 'common.py', 'TRANSFER.md'):
                (source / name).write_bytes(('fixture ' + name).encode())
            transfer.seal(source)
            with patch.object(transfer, 'ROOT', source):
                anchors = transfer.pack(parent / 'delivery')
                transfer.extract(parent / 'delivery', anchors['delivery_sha256sums_anchor'], parent / 'out')
                self.assertEqual(files(source), files(parent / 'out'))
                (parent / 'delivery' / transfer.ARCHIVE).write_bytes(b'changed')
                with self.assertRaises(ValueError):
                    transfer.extract(parent / 'delivery', anchors['delivery_sha256sums_anchor'], parent / 'refused')


if __name__ == '__main__':
    unittest.main()
