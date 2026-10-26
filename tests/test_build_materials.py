import hashlib
import base64
import json
from types import SimpleNamespace
import zipfile

import pytest

from tools.build_materials import artifact_materials, constraint_pins, main, npm_materials, python_materials

VALID_SRI = 'sha512-' + base64.b64encode(b'x' * 64).decode()


@pytest.mark.parametrize('value', ['pkg>=1', 'pkg==1.*', 'pkg @ https://example.test/private', 'pkg==1\npkg==2'])
def test_nonexact_or_ambiguous_constraints_refused(tmp_path, value):
    source = tmp_path / 'constraints.lock'
    source.write_text(value)
    with pytest.raises(ValueError):
        constraint_pins(source)


def test_constraint_markers_are_platform_specific(tmp_path):
    source = tmp_path / 'constraints.lock'
    source.write_text('one==1\ntwo==2; sys_platform == "impossible-platform"\n')
    assert constraint_pins(source) == {'one': '1'}


def test_transitive_extras_and_version_mismatch_cannot_hide(tmp_path):
    project = {'build-system': {'requires': ['setuptools>=75']},
               'project': {'dependencies': ['root[extra]>=1'], 'optional-dependencies': {'test': []}}}
    distributions = {'root': SimpleNamespace(version='1', requires=['child>=2; extra == "extra"']),
                     'child': SimpleNamespace(version='2', requires=[])}
    from importlib.metadata import PackageNotFoundError
    def lookup(name):
        if name not in distributions:
            raise PackageNotFoundError(name)
        return distributions[name]
    result = python_materials(project, {'root': '1'}, lookup)
    assert result['packages']['child']['version'] == '2'
    assert not result['constraint_coverage_complete']
    result = python_materials(project, {'root': '1', 'child': '2'}, lookup)
    assert result['constraint_coverage_complete']
    assert result['build_tools_installed']['setuptools'] is None
    assert not result['pep517_environment_verified']


def test_wheel_hash_is_of_the_exact_archive_and_not_installed_files(tmp_path):
    wheel = tmp_path / 'fake-1-py3-none-any.whl'
    with zipfile.ZipFile(wheel, 'w') as archive:
        archive.writestr('fake-1.dist-info/METADATA', 'Name: fake\nVersion: 1\n')
        archive.writestr('fake-1.dist-info/WHEEL', 'Tag: py3-none-any\n')
    row, = artifact_materials(tmp_path)
    assert row['sha256'] == hashlib.sha256(wheel.read_bytes()).hexdigest()
    assert row['name'] == 'fake' and not row['origin_verified']
    assert str(tmp_path) not in json.dumps(row)


def test_ambiguous_wheel_metadata_is_rejected(tmp_path):
    with zipfile.ZipFile(tmp_path / 'ambiguous.whl', 'w') as archive:
        archive.writestr('one.dist-info/METADATA', 'Name: fake\nVersion: 1\n')
        archive.writestr('two.dist-info/METADATA', 'Name: other\nVersion: 1\n')
    with pytest.raises(ValueError):
        artifact_materials(tmp_path)


@pytest.mark.parametrize('url', ['http://registry.npmjs.org/a', 'https://token@registry.npmjs.org/a',
                              'https://registry.npmjs.org/a?token=private', 'https://example.test/a'])
def test_npm_origin_and_integrity_fail_closed(tmp_path, url):
    path = tmp_path / 'package-lock.json'
    path.write_text(json.dumps({'lockfileVersion': 3, 'packages': {'node_modules/a':
        {'resolved': url, 'integrity': VALID_SRI}}}))
    with pytest.raises(ValueError):
        npm_materials(path)


def test_inventory_error_does_not_print_private_path(tmp_path, capsys):
    assert main(['--project', str(tmp_path / 'PRIVATE_SENTINEL')]) == 1
    output = capsys.readouterr().out
    assert json.loads(output)['error'] == 'materials_validation_failed'
    assert 'PRIVATE_SENTINEL' not in output and str(tmp_path) not in output


def test_every_dependency_edge_is_validated_even_when_already_visited():
    project = {'build-system': {'requires': []}, 'project': {'dependencies': ['root>=2', 'root<2']}}
    result = python_materials(project, {'root': '2'}, lambda name: SimpleNamespace(version='2', requires=[]))
    assert 'incompatible_dependency' in result['issues']


def test_npm_sri_format_is_checked_but_download_is_not_claimed(tmp_path):
    path = tmp_path / 'package-lock.json'
    row = {'resolved': 'https://registry.npmjs.org/fake/-/fake-1.tgz', 'integrity': VALID_SRI}
    path.write_text(json.dumps({'lockfileVersion': 3, 'packages': {'node_modules/fake': row}}))
    assert npm_materials(path)['packages'] == 1
    assert not npm_materials(path)['downloaded_bytes_verified']
    row['integrity'] = 'sha512-not-a-complete-digest'
    path.write_text(json.dumps({'lockfileVersion': 3, 'packages': {'node_modules/fake': row}}))
    with pytest.raises(ValueError):
        npm_materials(path)
