import io
import json
from pathlib import Path
import struct
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from common import digest, files, inventory, load, sha
from elf_audit import compare_symbols, inspect
import image_check
from rootfs_check import candidates, resolve_virtual
import review
import transfer


def tar_data(items):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name, kind, value in items:
            item = tarfile.TarInfo(name)
            item.mode = 0o755 if kind == 'directory' else 0o644
            item.mtime = 1234567890
            if kind == 'directory':
                item.type = tarfile.DIRTYPE
            elif kind in ('symlink', 'hardlink'):
                item.type = tarfile.SYMTYPE if kind == 'symlink' else tarfile.LNKTYPE
                item.linkname = value
            else:
                item.size = len(value)
            archive.addfile(item, io.BytesIO(value) if kind == 'file' else None)
    return stream.getvalue()


class ElfTests(unittest.TestCase):
    def binary(self):
        observed = inventory(ROOT / 'inputs' / 'DEPENDENCIES_OBSERVED.json')
        row = next(r for r in observed['distributions'] if r['distribution'].lower() == 'pyyaml')
        with zipfile.ZipFile(ROOT / 'inputs' / 'wheels' / row['file']) as archive:
            return archive.read(next(n for n in archive.namelist() if n.endswith('.so')))

    def test_real_symbol_versions_and_unversioned_python_scope(self):
        result = inspect(self.binary())
        self.assertIn('libc.so.6', result['needed'])
        self.assertTrue(any(s['library'] == 'libc.so.6' and s['version'].startswith('GLIBC_')
                            for s in result['undefined_symbols']))
        self.assertTrue(any(s['name'].startswith('Py') and s['version'] is None
                            for s in result['undefined_symbols']))
        self.assertTrue(any(s['name'].startswith('PyInit_') and s['version'] is None
                            for s in result['exported_symbols']))

    def test_truncation_wrong_machine_and_section_bounds(self):
        data = self.binary()
        machine = bytearray(data)
        struct.pack_into('<H', machine, 18, 3)
        section = bytearray(data)
        struct.pack_into('<Q', section, 40, len(data) + 1)
        for value in (data[:32], bytes(machine), bytes(section)):
            with self.subTest(length=len(value)), self.assertRaises(ValueError):
                inspect(value)

    def test_version_node_alone_does_not_prove_a_symbol(self):
        consumer = {'version_requires': {'libx.so': ['X_1']}, 'undefined_symbols': [
            {'name': 'needed', 'library': 'libx.so', 'version': 'X_1', 'weak': False}]}
        provider = {'version_defines': ['X_1'], 'exported_symbols': [
            {'name': 'other', 'version': 'X_1'}]}
        result = compare_symbols(consumer, provider, 'libx.so')
        self.assertFalse(result['missing_versions'])
        self.assertEqual(result['missing_strong'][0]['name'], 'needed')
        report = {'elf_objects': {
            '/lib/consumer.so': {**consumer, 'needed': ['libx.so'], 'soname': [], 'interpreter': None},
            '/lib/libx.so': {**provider, 'undefined_symbols': [], 'needed': [],
                            'soname': ['libx.so'], 'interpreter': None}}}
        edge = candidates(report)['edges'][0]
        self.assertEqual(edge['status'], 'CANDIDATES_ONLY_NOT_LOADER_RESOLUTION')
        self.assertTrue(edge['direct_candidate_symbol_comparisons'][0]['missing_strong'])
        provider['exported_symbols'].append({'name': 'needed', 'version': 'X_1'})
        self.assertFalse(compare_symbols(consumer, provider, 'libx.so')['missing_strong'])

    def test_real_32_object_review_remains_blocked(self):
        native, components, decision = review.review(ROOT)
        self.assertEqual(native['counts']['versioned_local_symbol_references'], 1223)
        self.assertTrue(all(not e['missing_strong'] and not e['missing_versions']
                            for e in native['wheel_local_versioned_symbol_review']))
        self.assertFalse(components['p3']['independently_inspected_here'])
        self.assertEqual(decision['decision'], 'BLOCKED')
        self.assertFalse(decision['build_go'])


class RootAndImageTests(unittest.TestCase):
    def layer(self):
        return tar_data([('.', 'directory', None), ('usr', 'directory', None),
                         ('usr/lib', 'directory', None), ('usr/lib/libx.so', 'file', b'library'),
                         ('usr/lib/libx-alias.so', 'hardlink', 'usr/lib/libx.so'),
                         ('lib', 'symlink', '/usr/lib')])

    def test_virtual_absolute_symlink_is_inside_root_and_cycles_reject(self):
        entries, _ = image_check.layer_inventory(self.layer())
        self.assertEqual(resolve_virtual(entries, '/lib/libx.so'), 'usr/lib/libx.so')
        entries['loop'] = {'type': 'symlink', 'target': 'loop'}
        with self.assertRaises(ValueError):
            resolve_virtual(entries, 'loop')
        entries['escape'] = {'type': 'symlink', 'target': '../outside'}
        with self.assertRaises(ValueError):
            resolve_virtual(entries, 'escape')

    def test_layer_preserves_hardlinks_and_detects_mode_or_mtime_change(self):
        entries, hardlinks = image_check.layer_inventory(self.layer())
        self.assertEqual(hardlinks, [['usr/lib/libx-alias.so', 'usr/lib/libx.so']])
        prepared = {'entries': entries, 'hardlinks': hardlinks}
        image_check.compare(prepared, entries, hardlinks)
        changed = json.loads(json.dumps(entries))
        changed['usr/lib/libx.so']['mtime_ns'] += 1
        with self.assertRaises(ValueError):
            image_check.compare(prepared, changed, hardlinks)

    def test_unsafe_duplicate_whiteout_and_missing_root_reject(self):
        for values in ([('../escape', 'file', b'x')],
                       [('.', 'directory', None), ('a', 'file', b'x'), ('a', 'file', b'y')],
                       [('.', 'directory', None), ('.wh.x', 'file', b'')],
                       [('a', 'file', b'x')]):
            with self.subTest(values=values), self.assertRaises(ValueError):
                image_check.layer_inventory(tar_data(values))

    def test_actual_synthetic_docker_save_binds_layer_and_config_not_just_filenames(self):
        layer = self.layer()
        entries, hardlinks = image_check.layer_inventory(layer)
        prepared = {'entries': entries, 'hardlinks': hardlinks}
        config = json.dumps({'os': 'linux', 'architecture': 'amd64',
                             'rootfs': {'type': 'layers', 'diff_ids': ['sha256:' + sha(layer)]}}).encode()
        config_name = sha(config) + '.json'
        manifest = json.dumps([{'Config': config_name, 'Layers': ['layer.tar']}]).encode()
        archive = tar_data([('manifest.json', 'file', manifest), (config_name, 'file', config),
                            ('layer.tar', 'file', layer)])
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'image.tar'
            path.write_bytes(archive)
            result = image_check.verify(path, digest(path), 'sha256:' + sha(config), prepared)
            self.assertTrue(result['rootfs_bytes_and_posix_metadata_equal'])
            self.assertFalse(result['native_abi_qualified'])
            with self.assertRaises(ValueError):
                image_check.verify(path, digest(path), 'sha256:' + '0' * 64, prepared)
            with self.assertRaises(ValueError):
                image_check.verify(path, '0' * 64, 'sha256:' + sha(config), prepared)
            wrong = json.loads(config)
            wrong['rootfs']['diff_ids'] = ['sha256:' + '0' * 64]
            wrong_bytes = json.dumps(wrong).encode()
            wrong_name = sha(wrong_bytes) + '.json'
            wrong_manifest = json.dumps([{'Config': wrong_name, 'Layers': ['layer.tar']}]).encode()
            path.write_bytes(tar_data([('manifest.json', 'file', wrong_manifest),
                                      (wrong_name, 'file', wrong_bytes), ('layer.tar', 'file', layer)]))
            with self.assertRaisesRegex(ValueError, 'diff ID mismatch'):
                image_check.verify(path, digest(path), 'sha256:' + sha(wrong_bytes), prepared)


class TransferTests(unittest.TestCase):
    def test_roundtrip_rejects_archive_tamper_and_existing_destination(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder)
            root = parent / 'source'
            root.mkdir()
            for name in ('transfer.py', 'common.py', 'wheels.py', 'TRANSFER.md'):
                (root / name).write_bytes(('fixture ' + name).encode())
            transfer.seal(root)
            with patch.object(transfer, 'ROOT', root):
                result = transfer.pack(parent / 'delivery')
                transfer.extract(parent / 'delivery', result['transfer_sha256sums_anchor'], parent / 'extracted')
                self.assertEqual(files(root), files(parent / 'extracted'))
                with self.assertRaises(ValueError):
                    transfer.new_destination(parent / 'extracted')
                (parent / 'delivery' / transfer.ARCHIVE).write_bytes(b'tampered')
                with self.assertRaises(ValueError):
                    transfer.extract(parent / 'delivery', result['transfer_sha256sums_anchor'], parent / 'refused')


if __name__ == '__main__':
    unittest.main()
