"""Verify transferred copies of existing B1 proof bytes, never rootfs/image contents or approval."""
import argparse
import json
from pathlib import Path
import re
import stat
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import digest, load, need, no_links, safe_name, write_new

ROOT = Path(__file__).resolve().parent


class ProofHashMismatch(ValueError):
    pass


def assess_references(refs):
    source, layer = refs['source_rootfs'], refs['layer_comparison']
    source_total = source['regular_files'] + source['directories_including_root']
    layer_total = layer['regular_files'] + layer['directories']
    need(source['regular_files'] == layer['regular_files']
         and source['directories_including_root'] == layer['directories'] + 1
         and layer['missing_entries'] == ['.'] and source_total == layer_total + 1,
         'Inconsistent reported path counts/root exclusion')
    need(layer['uid_gid_mismatches'] == layer_total
         and source['uid_gid_reported'] != layer['uid_gid_reported'], 'Inconsistent ownership counts')
    need(all(layer[key] == 0 for key in ('content_mismatches', 'permission_mismatches',
                                        'type_mismatches', 'extra_entries', 'special_entries')),
         'Reported mismatches require a different contents assessment')
    code = source['sha256sum_status_returncode_reported']
    need(type(code) is int and code == 0, 'Numeric reported checksum return code required')
    for value in refs['artifact_sha256'].values():
        need(re.fullmatch('[a-f0-9]{64}', value), 'Invalid artifact SHA')
    need(re.fullmatch('[a-f0-9]{64}', refs['image']['docker_save_archive_sha256']), 'Invalid archive SHA')
    for key in ('config_id', 'layer_diff_id'):
        need(re.fullmatch('sha256:[a-f0-9]{64}', refs['image'][key]), 'Invalid image/layer identity')
    return {'status': 'REPORTED_COUNTS_CONSISTENT_NOT_A_NEW_MEASUREMENT',
            'source_entries': source_total, 'layer_entries': layer_total,
            'reported_regular_file_content_identity_supported': True,
            'missing_root_is_not_file_content_divergence': True,
            'all_present_entries_have_reported_ownership_difference': True,
            'full_metadata_equality': False, 'formal_b1_contents_closed': False,
            'build_go': False, 'create_go': False, 'start_go': False, 'production_go': False}


def verify_existing(proof_directory, refs):
    assessment = assess_references(refs)
    directory = no_links(proof_directory)
    checked = {}
    for name, expected in refs['artifact_sha256'].items():
        safe_name(name)
        path = no_links(directory / name)
        info = path.stat()
        need(stat.S_ISREG(info.st_mode) and info.st_size <= 64 * 1024**2, 'Regular bounded proof file required')
        actual = digest(path)
        if actual != expected:
            raise ProofHashMismatch('Transferred proof SHA mismatch: ' + name)
        checked[name] = {'sha256': actual, 'bytes': info.st_size}

    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'Duplicate comparison JSON key')
            result[key] = value
        return result

    report = json.loads((directory / 'p3-layer-comparison.json').read_text(encoding='utf-8'),
                        object_pairs_hook=unique)
    need(isinstance(report, dict), 'Comparison report object required; unsupported schema')
    return {'status': 'PASS_ANCHORED_PROOF_BYTES_ONLY', 'checked': checked,
            'normalized_operator_reference_assessment': assessment,
            'raw_report_schema_and_counter_semantics_validated': False,
            'comparison_tool_and_receipts_reviewed': False,
            'archive_and_rootfs_rehashed': False, 'formal_b1_contents_closed': False,
            'p4_base_approved': False, 'build_go': False, 'create_go': False,
            'start_go': False, 'production_go': False,
            'note': 'No raw schema was supplied; hash/JSON validation is not formal contents closure'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--proof-directory', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    need(not no_links(args.out).is_relative_to(no_links(args.proof_directory)),
         'Write only to a new evidence directory, never the existing proofs')
    refs_path = ROOT / 'P4_B1_OBSERVED_REFERENCES.json'
    try:
        result = verify_existing(args.proof_directory, load(refs_path))
        code = 0
    except ProofHashMismatch as error:
        result = {'status': 'FAIL_TRANSFERRED_PROOF_HASH', 'error': str(error)}
        code = 1
    except (OSError, ValueError, KeyError) as error:
        result = {'status': 'INCOMPLETE_EVIDENCE_REVIEW', 'error': str(error)}
        code = 2
    result.update(references_sha256=digest(refs_path), decision='BLOCKED',
                  formal_b1_contents_closed=False, build_go=False, create_go=False,
                  start_go=False, run_go=False, pull_go=False, import_go=False, production_go=False)
    write_new(args.out, result)
    sys.exit(code)


if __name__ == '__main__':
    main()
