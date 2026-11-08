import base64
import csv
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import common
import gate
import image_catalog
import native
import preserve
import report_materials
import transfer
import wheels


def dummy_wheel(changed=False, tag='py3-none-any'):
    files = {
        'sample/__init__.py': b'',
        'sample-1.0.dist-info/METADATA':
            b'Metadata-Version: 2.1\nName: sample\nVersion: 1.0\nRequires-Python: >=3.9\n',
        'sample-1.0.dist-info/WHEEL': ('Wheel-Version: 1.0\nTag: ' + tag + '\n').encode(),
    }
    record = io.StringIO(newline='')
    writer = csv.writer(record, lineterminator='\n')
    for name, value in files.items():
        encoded = base64.urlsafe_b64encode(bytes.fromhex(common.sha(value))).decode().rstrip('=')
        writer.writerow((name, 'sha256=' + encoded, len(value)))
    writer.writerow(('sample-1.0.dist-info/RECORD', '', ''))
    files['sample-1.0.dist-info/RECORD'] = record.getvalue().encode()
    if changed:
        files['sample/__init__.py'] = b'changed without updating RECORD'
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    data = output.getvalue()
    return {'distribution': 'sample', 'version': '1.0', 'file': 'sample-1.0-py3-none-any.whl',
            'sha256': common.sha(data), 'bytes': len(data),
            'requires_dist': [], 'requires_python': '>=3.9'}, data


class WheelTests(unittest.TestCase):
    def test_hash_and_exhaustive_record_integrity(self):
        record, data = dummy_wheel()
        self.assertEqual(wheels.verify_wheel(record, data)['record_integrity'], 'PASS')
        changed_record, changed_data = dummy_wheel(changed=True)
        with self.assertRaisesRegex(ValueError, 'RECORD hash'):
            wheels.verify_wheel(changed_record, changed_data)
        record['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'Wheel bytes'):
            wheels.verify_wheel(record, data)

    def test_inventory_cannot_hide_actual_requires_dist(self):
        record, data = dummy_wheel()
        record['requires_dist'] = ['unobserved-extra']
        with self.assertRaisesRegex(ValueError, 'dependency metadata mismatch'):
            wheels.verify_wheel(record, data)

    def test_internal_tag_mismatch_and_zip_traversal(self):
        record, data = dummy_wheel(tag='cp313-cp313-win_amd64')
        with self.assertRaisesRegex(ValueError, 'tags differ'):
            wheels.verify_wheel(record, data)
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr('../outside', b'x')
        with self.assertRaises(ValueError):
            wheels.checked_zip(output.getvalue())

    def test_published_metadata_match_is_not_approval(self):
        inv = common.inventory(ROOT / 'materials' / 'DEPENDENCIES_OBSERVED.json')
        record = next(r for r in inv['distributions'] if r['distribution'].lower() == 'pyyaml')
        source = ROOT / 'pyyaml-upstream'
        endpoint = 'https://pypi.org/pypi/PyYAML/6.0.3/json'
        result = wheels.verify_upstream(record, source / 'stdout', source / 'receipt.json', endpoint)
        self.assertIn('MATCHED_PYPI', result['status'])
        self.assertFalse(result['artifact_signature_verified'])
        self.assertFalse(result['independent_approval'])
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            metadata = common.load(source / 'stdout')
            entry = next(v for v in metadata['urls'] if v['filename'] == record['file'])
            entry['yanked'] = True
            common.write_new(root / 'metadata', metadata)
            receipt = common.load(source / 'receipt.json')
            receipt['sha256']['stdout'] = common.digest(root / 'metadata')
            common.write_new(root / 'receipt.json', receipt)
            with self.assertRaisesRegex(ValueError, 'artifact mismatch'):
                wheels.verify_upstream(record, root / 'metadata', root / 'receipt.json', endpoint)

    def test_selection_has_no_unexplained_package_and_preserves_binary_extra(self):
        inv = common.inventory(ROOT / 'materials' / 'DEPENDENCIES_OBSERVED.json')
        reasons = report_materials.graph(inv['distributions'])
        self.assertIn('psycopg', reasons['psycopg-binary'])
        self.assertIn('bootstrap', reasons['pip'])
        without_binary = [r for r in inv['distributions'] if r['distribution'].lower() != 'psycopg-binary']
        with self.assertRaises(ValueError):
            report_materials.graph(without_binary)


class NativeTests(unittest.TestCase):
    def binary(self):
        inv = common.inventory(ROOT / 'materials' / 'DEPENDENCIES_OBSERVED.json')
        record = next(r for r in inv['distributions'] if r['distribution'].lower() == 'pyyaml')
        with zipfile.ZipFile(ROOT / 'materials' / 'wheels' / record['file']) as archive:
            return archive.read(next(n for n in archive.namelist() if n.endswith('.so')))

    def test_real_elf_has_versioned_system_needs_without_execution(self):
        parsed = native.elf(self.binary())
        self.assertIn('libc.so.6', parsed['needed'])
        self.assertTrue(any(v.startswith('GLIBC_') for v in parsed['version_requires']['libc.so.6']))
        self.assertIsNone(parsed['interpreter'])

    def test_malformed_wrong_arch_and_missing_section_table_refuse(self):
        data = self.binary()
        variants = [data[:32], data[:4] + b'\x01' + data[5:]]
        wrong_machine = bytearray(data)
        struct.pack_into('<H', wrong_machine, 18, 3)
        variants.append(bytes(wrong_machine))
        no_sections = bytearray(data)
        struct.pack_into('<H', no_sections, 60, 0)
        variants.append(bytes(no_sections))
        for value in variants:
            with self.subTest(length=len(value)), self.assertRaises(ValueError):
                native.elf(value)

    def test_origin_search_is_direct_only_and_unsupported_tokens_block(self):
        obj = {'path': native.SITE + '/pkg/extension.so', 'rpath': ['$ORIGIN/../libs'], 'runpath': []}
        self.assertEqual(native.local_candidates(obj, 'libx.so'), [native.SITE + '/libs/libx.so'])
        obj['rpath'] = ['$ORIGIN/$LIB']
        with self.assertRaises(ValueError):
            native.local_candidates(obj, 'libx.so')
        with self.assertRaises(ValueError):
            native.local_candidates(obj, '../libx.so')


class ImageAndTransferTests(unittest.TestCase):
    def image_archive(self, path, python_version):
        config = json.dumps({'os': 'linux', 'architecture': 'amd64',
                             'config': {'Env': ['PYTHON_VERSION=' + python_version, 'PRIVATE_DUMMY=not-published']},
                             'rootfs': {'diff_ids': []}}).encode()
        config_name = common.sha(config) + '.json'
        values = {'manifest.json': json.dumps([{'Config': config_name, 'RepoTags': [], 'Layers': []}]).encode(),
                  config_name: config}
        with tarfile.open(path, 'w') as archive:
            for name, value in values.items():
                item = tarfile.TarInfo(name)
                item.size = len(value)
                archive.addfile(item, io.BytesIO(value))

    def test_target_env_hint_never_approves_layers_or_debian(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'image.tar'
            self.image_archive(path, '3.11.18')
            report = image_catalog.inspect_archive(path)
            result = report['images'][0]
            self.assertEqual(result['status'], 'UNVERIFIED_CANDIDATE')
            self.assertFalse(result['debian13_verified'])
            self.assertFalse(result['layer_diff_ids_verified'])
            self.assertFalse(result['provenance_approved'])
            self.assertNotIn('PRIVATE_DUMMY', json.dumps(report))

    def test_wrong_python_base_rejects_without_starting(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'image.tar'
            self.image_archive(path, '3.13.17')
            self.assertEqual(image_catalog.inspect_archive(path)['images'][0]['status'], 'NOT_A_TARGET_BASE')

    def test_exact_manifest_and_existing_destination_refusal(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'file').write_bytes(b'proof')
            transfer.seal(root)
            anchor = common.digest(root / 'SHA256SUMS')
            common.manifest(root, anchor)
            with self.assertRaises(ValueError):
                transfer.new_destination(root)
            (root / 'extra').write_bytes(b'extra')
            with self.assertRaises(ValueError):
                common.manifest(root, anchor)

    def test_delivery_roundtrip_and_archive_tampering(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / 'source'
            source.mkdir()
            for name in ('transfer.py', 'common.py', 'wheels.py', 'TRANSFER.md'):
                (source / name).write_bytes(('fixture ' + name).encode())
            transfer.seal(source)
            with patch.object(transfer, 'ROOT', source):
                result = transfer.pack(root / 'delivery')
                anchor = result['transfer_sha256sums_anchor']
                transfer.extract(root / 'delivery', anchor, root / 'extracted')
                self.assertEqual(common.files(source), common.files(root / 'extracted'))
                (root / 'delivery' / transfer.ARCHIVE).write_bytes(b'tampered')
                with self.assertRaises(ValueError):
                    transfer.extract(root / 'delivery', anchor, root / 'refused')
                self.assertFalse((root / 'refused').exists())


class GateAndPreservationTests(unittest.TestCase):
    def test_material_gate_is_blocked_and_cli_keeps_numeric_nonzero(self):
        result = gate.decision(ROOT)
        self.assertEqual(result['decision'], 'BLOCKED')
        self.assertFalse(result['build_go'])
        self.assertGreaterEqual(len(result['blockers']), 6)
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / 'result.json'
            process = subprocess.run([sys.executable, '-I', '-B', str(ROOT / 'gate.py'),
                                      '--root', str(ROOT), '--out', str(out)],
                                     capture_output=True, timeout=30)
            self.assertEqual(process.returncode, 2)
            self.assertEqual(common.load(out)['decision'], 'BLOCKED')

    def test_gate_cannot_promote_a_modified_native_report(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for name in ('P4_IMAGE_COMPONENTS.json', 'P4_NATIVE_CLOSURE.json',
                         'P4_WHEEL_CHECKS.json', 'P4_PIP_BOOTSTRAP.json'):
                value = common.load(ROOT / name)
                if name == 'P4_NATIVE_CLOSURE.json':
                    value['binary_closure_approved'] = True
                common.write_new(root / name, value)
            with self.assertRaisesRegex(ValueError, 'binding mismatch'):
                gate.decision(root)

    def test_preservation_detects_content_change(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'old').mkdir()
            path = root / 'old' / 'proof'
            path.write_bytes(b'frozen')
            baseline = {'scope': ['old'], 'files': {'old/proof': common.digest(path)}}
            preserve.verify(root, baseline)
            path.write_bytes(b'changed')
            with self.assertRaises(ValueError):
                preserve.verify(root, baseline)


if __name__ == '__main__':
    unittest.main()
