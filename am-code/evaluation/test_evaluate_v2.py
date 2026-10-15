"""Fake-metadata tests of scorer binding and final access order; no native execution."""
import argparse
import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import evaluate_v2 as scorer


class EntryPointTests(unittest.TestCase):
    def test_both_entrypoints_verify_profile_before_task_access(self):
        spec = importlib.util.spec_from_file_location('test_scan_v2',
            scorer.ROOT.parent / 'end-to-end/evaluate_v2.py')
        scan = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(scan)
        for module in (scorer, scan):
            with self.subTest(module=module.__name__):
                with patch.object(sys, 'argv', ['evaluate_v2.py', '--references', '--run-dir', '/fixture/new']):
                    with patch.object(module.policy, 'verify_checker_profile', side_effect=ValueError('unfrozen')):
                        with patch.object(Path, 'read_text', side_effect=AssertionError('no task read')):
                            with self.assertRaisesRegex(ValueError, 'unfrozen'):
                                module.main()

    def test_final_requires_complete_selection_before_task_hash_or_read(self):
        binding = {'checker_profile_sha256': 'a' * 64, 'profile': {}}
        with patch.object(sys, 'argv', ['evaluate_v2.py', '--split', 'final', '--run-dir', '/fixture/new',
                                      '--responses', '/fixture/responses']):
            with patch.object(scorer.policy, 'verify_checker_profile', return_value=binding):
                with patch.object(Path, 'read_text', side_effect=AssertionError('no final read')):
                    with patch.object(scorer.native, 'digest', side_effect=AssertionError('no final hash')):
                        with self.assertRaisesRegex(ValueError, 'final scoring requires'):
                            scorer.main()

    def test_final_context_uses_shared_selection_guard_and_preserves_final_seal(self):
        q = scorer.qualification
        sha = 'a' * 64
        selected = {'schema': q.SELECTION_SCHEMA, 'checker_policy': q.CHECKER_POLICY,
            'checker_profile_sha256': sha, 'status': 'selected_for_final_evaluation',
            'development_passes': 11, 'scan_passes': 4, 'required_safety_passed': True,
            'checks': dict.fromkeys(q.QUALIFICATION_CHECK_KEYS, True),
            'qualification': 'software and geometry only', 'manufacturing_authorized': False,
            **dict.fromkeys(('adapter_sha256', 'adapter_config_sha256', 'base_weights_sha256',
                'development_task_sha256', 'scan_task_sha256', 'scan_freeze_sha256',
                'qualification_source_sha256', 'development_gate_source_sha256'), sha)}
        protocol = {'checker_policy': q.CHECKER_POLICY, 'checker_profile_sha256': sha,
            'selection_receipt_sha256': sha,
            **dict.fromkeys(('adapter_sha256', 'adapter_config_sha256', 'base_weights_sha256'), sha)}
        args = argparse.Namespace(references=False, selection_receipt=Path('/fixture/selection.json'),
            adapter=Path('/fixture/adapter/adapters.safetensors'), base_profile=Path('/fixture/base.json'),
            responses=Path('/fixture/responses'), run_dir=Path('/fixture/new'))
        def read(path):
            self.assertNotEqual(path.name, 'final.json')
            if path.name == 'selection.json':
                return selected
            if path.name == 'freeze.json':
                return {'files': {'development.json': sha, 'final.json': sha}}
            if path.name == 'protocol.json':
                return protocol
            raise AssertionError('unexpected metadata read')
        with patch.object(q, 'read', side_effect=read), patch.object(q, 'digest', return_value=sha):
            with patch.object(q, 'verify_scan_freeze', return_value={}):
                with patch.object(q.base_runtime, 'verify_base', return_value={
                        'base_weights_sha256': sha, 'binding': {}}):
                    with patch.object(q.base_runtime, 'verify_evidence'):
                        self.assertEqual(scorer.final_context(args, sha)['selection_receipt_sha256'], sha)
                        for key, value in (('checker_profile_sha256', 'b' * 64),
                                           ('adapter_sha256', 'b' * 64), ('development_passes', 10),
                                           ('manufacturing_authorized', True)):
                            previous = selected[key]
                            selected[key] = value
                            with self.subTest(key=key), self.assertRaises(ValueError):
                                scorer.final_context(args, sha)
                            selected[key] = previous
                        args.selection_receipt = scorer.ROOT / 'final.json'
                        with self.assertRaises(ValueError):
                            scorer.final_context(args, sha)


if __name__ == '__main__':
    unittest.main()
