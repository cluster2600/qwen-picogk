"""Contract checks for the DfAM code corpus that need neither .NET nor PicoGK."""
import json
import copy
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import dfam_corpus  # noqa: E402


class DfamCorpusTest(unittest.TestCase):
    def setUp(self):
        self.cases = dfam_corpus.load_cases(ROOT / 'data/dfam-code/cases.jsonl')
        self.bib = dfam_corpus.bibliography()

    def test_cases_pass_lint(self):
        self.assertEqual(dfam_corpus.lint(self.cases), {})

    def test_bibliography_entries_are_scoped(self):
        for key, entry in self.bib.items():
            self.assertEqual(set(entry), {'cite', 'entry', 'scope'}, key)
            self.assertIn(entry['cite'].split('(')[-1].rstrip(')'), entry['entry'], key)

    def test_legacy_receipt_is_preserved_but_not_training_eligible(self):
        receipt = json.loads((ROOT / 'evidence/dfam-code/verification.json').read_text())
        self.assertEqual(receipt['picogk_package'], '2.3.0')
        record = receipt['cases']['infill-001']
        self.assertTrue(record['passed'])
        metrics = record['run']['outputs']['part.stl']
        # The legacy record lacks the v3 measurements, and its mesh had 86 degenerate triangles.
        self.assertIn('missing, nonfinite or invalid metric self_intersecting_pairs',
                      dfam_corpus.evaluate(metrics, {'min_wall_mm': 1.0}))
        self.assertIn('degenerate_triangles = 86, required 0',
                      dfam_corpus.evaluate(dict(self.v3_fields(), **metrics), {'min_wall_mm': 1.0}))
        with self.assertRaisesRegex(ValueError, 'current strict-policy'):
            dfam_corpus.receipt_check(self.cases, receipt)

    def test_strict_v2_receipt_is_historical_under_v3(self):
        receipt = json.loads((ROOT / 'evidence/dfam-code/strict-v2-20261015.json').read_text())
        self.assertEqual(receipt['policy'], 'dfam-strict-v2')
        with self.assertRaisesRegex(ValueError, 'current strict-policy'):
            dfam_corpus.receipt_check(self.cases, receipt)

    def test_lint_rejects_known_invalid_api(self):
        case = dict(self.cases[0], code=self.cases[0]['code'] + '\n// voxPart.Sub(voxVents);\n')
        problems = dfam_corpus.lint_case(case, self.bib)
        self.assertTrue(any('Sub()' in p for p in problems))

    def test_text_format(self):
        row = dfam_corpus.assemble_text(self.cases[0], self.bib)
        self.assertEqual(set(row), {'messages'})
        self.assertEqual([m['role'] for m in row['messages']], ['user', 'assistant'])
        self.assertIn(self.cases[0]['code'].strip(), row['messages'][1]['content'])
        self.assertNotIn('<|im_start|>', row['messages'][0]['content'])

    @staticmethod
    def v3_fields():
        # Values measured on infill-001 by the v3 checker and the libigl sidecar.
        return dict(needle_triangles=0, self_intersecting_pairs=0, self_intersecting_coplanar_pairs=0,
                    self_intersecting_triangles=0, wall_thickness_p01_mm=1.0495, wall_thickness_p05_mm=1.2039,
                    wall_thickness_cap_mm=4.0, thin_wall_area_fraction=0.00371)

    def metrics(self):
        receipt = json.loads((ROOT / 'evidence/dfam-code/verification.json').read_text())
        return dict(receipt['cases']['infill-001']['run']['outputs']['part.stl'], **self.v3_fields(),
                    degenerate_triangles=0, stl_sha256='a' * 64)

    def receipt(self):
        return dict(policy=dfam_corpus.POLICY, isolation='linux-bubblewrap-systemd',
                    policy_source_sha256=dfam_corpus.sha(Path(dfam_corpus.__file__).read_bytes()),
                    checker_source_sha256=dfam_corpus.checker_stamp(),
                    picogk_package='2.3.0', voxel_mm=0.3,
                    cases={'infill-001': dict(passed=True, case_sha256=dfam_corpus.case_sha(self.cases[0]),
                        run=dict(exit=0, failed=[], outputs={'part.stl': self.metrics()}))})

    def test_metrics_reject_bad_topology_and_nonfinite_values(self):
        metrics = self.metrics()
        self.assertEqual(dfam_corpus.evaluate(metrics, self.cases[0]['expect']), [])
        for key, value in [('degenerate_triangles', 1), ('inconsistent_orientation_edges', 1),
                           ('boundary_edges', 1), ('solid_components', 1.5), ('triangles', 0),
                           ('enclosed_void_mm3', float('nan')), ('thin_fraction', float('inf')),
                           ('overhang_fraction', -1), ('volume_ratio_to_fixture', True),
                           ('min_wall_mm', 0.1), ('mesh_volume_mm3', 0)]:
            with self.subTest(key=key):
                self.assertTrue(dfam_corpus.evaluate(dict(metrics, **{key: value}), self.cases[0]['expect']))
        del metrics['nonmanifold_edges']
        self.assertTrue(dfam_corpus.evaluate(metrics, self.cases[0]['expect']))

    def test_declared_overhang_and_thin_limits_are_enforced(self):
        expect = dict(self.cases[0]['expect'], overhang_fraction_max=0, thin_fraction_max=0,
                      thin_wall_area_fraction_max=0.001)
        self.assertEqual(len(dfam_corpus.evaluate(self.metrics(), expect)), 3)

    def test_v3_gates_self_intersections_needles_and_thickness_metrics(self):
        expect = self.cases[0]['expect']
        for key, value in [('self_intersecting_pairs', 4), ('needle_triangles', 2)]:
            with self.subTest(key=key):
                self.assertIn(f'{key} = {value}, required 0',
                              dfam_corpus.evaluate(dict(self.metrics(), **{key: value}), expect))
        for key, value in [('thin_wall_area_fraction', 1.5), ('wall_thickness_p01_mm', float('nan')),
                           ('self_intersecting_triangles', 2.5)]:
            with self.subTest(key=key):
                self.assertTrue(dfam_corpus.evaluate(dict(self.metrics(), **{key: value}), expect))
        metrics = self.metrics(); del metrics['wall_thickness_p05_mm']
        self.assertTrue(dfam_corpus.evaluate(metrics, expect))

    def test_checker_stamp_binds_the_selfcheck_sidecar(self):
        self.assertIn('SelfCheck/selfcheck.py', dfam_corpus.CHECKER_FILES)
        self.assertIn('SelfCheck/requirements.txt', dfam_corpus.CHECKER_FILES)
        for line in (ROOT / 'dfam-native/SelfCheck/requirements.txt').read_text().splitlines():
            if line and not line.startswith('#'):
                self.assertRegex(line, r'^[a-z]+==[0-9.]+ --hash=sha256:[0-9a-f]{64}$')

    def test_selfcheck_known_answers(self):
        try:
            import numpy  # noqa: F401
            import igl  # noqa: F401
        except ImportError:
            self.skipTest('numpy/libigl not installed; the native verifier installs the pinned sidecar')
        sys.path.insert(0, str(ROOT / 'dfam-native/SelfCheck'))
        import selfcheck
        self.assertFalse(selfcheck.self_test()['closed_cube']['found'])

    def test_schema_rejects_invalid_expectations_and_paths(self):
        for key, value in [('volume_ratio', [0.7, 0.5]), ('volume_ratio', [True, 0.7]),
                           ('volume_ratio', [float('nan'), 0.7]), ('volume_ratio', 'bad'),
                           ('outputs', ['../escape.stl']), ('outputs', ['/tmp/escape.stl']),
                           ('outputs', ['part.stl', 'part.stl']), ('outputs', [['bad']]),
                           ('thin_fraction_max', float('nan')), ('min_wall_mm', 0)]:
            case = copy.deepcopy(self.cases[0]); case['expect'][key] = value
            with self.subTest(key=key, value=value):
                self.assertTrue(dfam_corpus.lint_case(case, self.bib))
        for bad in [[], {}, {'id': 42}, dict(self.cases[0], code=None)]:
            self.assertTrue(dfam_corpus.lint([bad]))
        self.assertTrue(dfam_corpus.lint([]))

    def test_only_scan_cases_may_declare_volume_above_reference(self):
        infill = copy.deepcopy(self.cases[0]); infill['expect']['volume_ratio'] = [0.5, 1.1]
        self.assertTrue(any('volume_ratio' in p for p in dfam_corpus.lint_case(infill, self.bib)))
        scan = copy.deepcopy(self.cases[0]); scan.update(id='scan-900', category='scan_repair')
        for interval, ok in [([0.9, 1.15], True), ([0.9, 1.6], False), ([1.2, 1.1], False)]:
            scan['expect'] = {'volume_ratio': interval}
            with self.subTest(interval=interval):
                problems = [p for p in dfam_corpus.lint_case(scan, self.bib) if 'volume_ratio' in p]
                self.assertEqual(not problems, ok)

    def test_unassigned_corpus_is_refused_before_assembly(self):
        with self.assertRaisesRegex(ValueError, 'Corpus not ready'):
            dfam_corpus.assemble(self.cases, {}, Mock())
        problems = dfam_corpus.lint(self.cases, full=True)
        self.assertIn('register family and split before assembly', problems['infill-001'])

    def test_related_family_cannot_cross_partitions(self):
        a = dict(self.cases[0], family='gyroid-sheet', split='train')
        b = dict(a, id='infill-002', split='test', user='A completely different prompt. ' * 10,
                 code=self.cases[0]['code'].replace('fSkinMM', 'fNewSkinMM'))
        with patch.object(dfam_corpus, 'jaccard', return_value=0):
            problems = dfam_corpus.lint([a, b], full=True)
        self.assertIn('family gyroid-sheet crosses partitions', problems['corpus'])

    def test_receipt_requires_current_bindings_and_recomputed_metrics(self):
        # The receipt fixture covers infill-001 only; bind it to that case.
        cases = [c for c in self.cases if c['id'] == 'infill-001']
        receipt = self.receipt()
        dfam_corpus.receipt_check(cases, receipt)
        for key, value in [('policy_source_sha256', '0' * 64), ('checker_source_sha256', '0' * 64),
                           ('voxel_mm', 0.5), ('isolation', 'host')]:
            with self.subTest(key=key), self.assertRaises(ValueError):
                dfam_corpus.receipt_check(cases, dict(receipt, **{key: value}))
        for key, value in [('degenerate_triangles', 86), ('stl_sha256', ''), ('thin_fraction', float('nan'))]:
            changed = copy.deepcopy(receipt)
            changed['cases']['infill-001']['run']['outputs']['part.stl'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                dfam_corpus.receipt_check(cases, changed)
        changed = copy.deepcopy(self.cases)
        changed[0]['user'] += ' changed'
        with self.assertRaises(ValueError):
            dfam_corpus.receipt_check(changed, receipt)

    def test_length_guard_rejects_truncation_and_retains_complete_code(self):
        case = dict(self.cases[0], split='train', family='gyroid-sheet')
        tokenizer = Mock()
        with patch.object(dfam_corpus, 'lint', return_value={}), patch.object(dfam_corpus, 'receipt_check'):
            tokenizer.apply_chat_template.return_value = range(dfam_corpus.MAX_SEQ_LENGTH + 1)
            with self.assertRaisesRegex(ValueError, 'refusing truncation'):
                dfam_corpus.assemble([case], {}, tokenizer)
            tokenizer.apply_chat_template.return_value = range(3595)
            files = dfam_corpus.assemble([case], {}, tokenizer)
        row = json.loads(files['train'])
        self.assertIn(case['code'].strip(), row['messages'][1]['content'])
        tokenizer.apply_chat_template.assert_called_with(row['messages'], tokenize=True,
                                                         add_generation_prompt=False, return_dict=False)
        config = json.loads((ROOT / 'training/configs/dfam-code.json').read_text())
        self.assertEqual(config['max_seq_length'], dfam_corpus.MAX_SEQ_LENGTH)
        self.assertTrue(config['mask_prompt'])

    def test_no_uncapped_or_unsandboxed_fallback(self):
        with patch.object(dfam_corpus.sys, 'platform', 'darwin'), self.assertRaisesRegex(RuntimeError, 'no uncapped fallback'):
            dfam_corpus.capped(['true'], '3G')
        with patch.object(dfam_corpus.sys, 'platform', 'linux'), patch.object(dfam_corpus.shutil, 'which', return_value=None):
            with self.assertRaises(RuntimeError):
                dfam_corpus.capped(['true'], '3G')
            with self.assertRaises(RuntimeError):
                dfam_corpus.sandbox_command(Path('runner'), '', Path('out'), 'Case', {})
        with patch.object(dfam_corpus.sys, 'platform', 'linux'), patch.object(dfam_corpus.shutil, 'which', return_value='/usr/bin/systemd-run'), patch.object(dfam_corpus.subprocess, 'run', return_value=Mock(returncode=1)):
            with self.assertRaises(RuntimeError):
                dfam_corpus.capped(['true'], '3G')

    def test_candidate_scope_requests_two_cpu_quota(self):
        with patch.object(dfam_corpus.sys, 'platform', 'linux'), patch.object(dfam_corpus.shutil, 'which', return_value='/usr/bin/systemd-run'), patch.object(dfam_corpus.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            cmd = dfam_corpus.capped(['true'], '3G', dfam_corpus.CANDIDATE_CPU_QUOTA)
            self.assertIn('CPUQuota=200%', run.call_args[0][0])   # the probe tests the quota too
            checker = dfam_corpus.capped(['true'], '4G')             # trusted checker: no quota
        self.assertEqual(cmd[cmd.index('CPUQuota=200%') - 1], '-p')
        self.assertNotIn('CPUQuota=200%', checker)

    def test_sandbox_exposes_only_runtime_selected_input_and_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); runtime = base/'dotnet'; runtime.mkdir()
            binary = runtime/'dotnet'; binary.touch()
            out = base/'out'; out.mkdir()
            app = base/'app'; app.mkdir()
            source = base/'selected.stl'; source.touch()
            env = {'PATH': str(runtime), 'DOTNET_ROOT': str(runtime), 'PICOGK_NATIVE': str(runtime)}
            with patch.object(dfam_corpus.sys, 'platform', 'linux'), patch.object(dfam_corpus.shutil, 'which', side_effect=lambda name, **kw: str(binary) if name == 'dotnet' else '/usr/bin/bwrap'), patch.object(dfam_corpus, 'capped', side_effect=lambda cmd, mem, *quota: cmd), patch.object(Path, 'is_file', return_value=True):
                cmd = dfam_corpus.sandbox_command(app/'Runner.dll', str(source), out, 'Case', env)
            self.assertIn('--unshare-all', cmd)
            self.assertIn('--clearenv', cmd)
            self.assertEqual(cmd[cmd.index('--bind') + 1:cmd.index('--bind') + 3], [str(out.resolve()), '/output'])
            self.assertIn('/input/selected.stl', cmd)
            self.assertIn('--fsize=268435456:268435456', cmd)
            # The runtime cannot start under that file limit with W^X double mapping.
            i = cmd.index('DOTNET_EnableWriteXorExecute')
            self.assertEqual((cmd[i - 1], cmd[i + 1]), ('--setenv', '0'))
            self.assertNotIn(str(ROOT), cmd)

    def test_escaping_candidate_output_is_not_sent_to_checker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); out = root/'runs/infill-001'; out.mkdir(parents=True)
            external = root/'outside.stl'; external.write_text('not geometry')
            (out/'part.stl').symlink_to(external)
            with patch.object(dfam_corpus.shutil, 'rmtree'), patch.object(Path, 'mkdir'), patch.object(dfam_corpus, 'sandbox_command', return_value=['true']), patch.object(dfam_corpus.subprocess, 'run', return_value=Mock(returncode=0)), patch.object(dfam_corpus, 'check_stl') as checker:
                result = dfam_corpus.run_case(Path('runner'), Path('checker'), root, self.cases[0], False,
                                             {'PATH': '/usr/bin'}, root/'runs', 1)
            self.assertTrue(result['failed'])
            checker.assert_not_called()

    def test_assembly_does_not_overwrite_existing_partitions(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'cases.jsonl').write_text(json.dumps(self.cases[0]) + '\n')
            (root/'release.json').write_text(json.dumps({'base': {'files': {}}}))
            (root/'receipt.json').write_text('{}')
            (root/'train.jsonl').write_text('published partition\n')
            argv = ['dfam_corpus.py', 'assemble', '--receipt', str(root/'receipt.json'), '--base', str(root)]
            transformers = SimpleNamespace(AutoTokenizer=Mock())
            with patch.object(dfam_corpus, 'ROOT', root), patch.object(dfam_corpus, 'DATA', root), patch.object(dfam_corpus, 'lint', return_value={}), patch.object(dfam_corpus, 'receipt_check'), patch.object(dfam_corpus, 'assemble', return_value={'train': 'changed', 'valid': 'new', 'test': 'new'}), patch.dict(sys.modules, {'transformers': transformers}), patch.object(sys, 'argv', argv), patch.object(sys, 'stderr'):
                with self.assertRaises(SystemExit) as error:
                    dfam_corpus.main()
            self.assertEqual(error.exception.code, 2)
            self.assertEqual((root/'train.jsonl').read_text(), 'published partition\n')
            self.assertFalse((root/'valid.jsonl').exists())
            self.assertFalse((root/'test.jsonl').exists())

    def test_unknown_case_selection_refuses_before_native_work(self):
        argv = ['dfam_corpus.py', 'verify', str(ROOT/'data/dfam-code/cases.jsonl'),
                '--tag', 'test', '--ids', 'infill-999']
        with patch.object(sys, 'argv', argv), patch.object(sys, 'stderr'), patch.object(dfam_corpus, 'verify') as verify:
            with self.assertRaises(SystemExit) as error:
                dfam_corpus.main()
        self.assertEqual(error.exception.code, 2)
        verify.assert_not_called()

    def test_unsafe_tag_refuses_before_building(self):
        with patch.object(dfam_corpus, 'build') as build:
            with self.assertRaises(ValueError):
                dfam_corpus.verify(self.cases, '../escape', 1, 300)
        build.assert_not_called()

    def test_existing_receipt_is_never_overwritten(self):
        receipt_path = ROOT/'evidence/dfam-code/verification.json'
        before = receipt_path.read_bytes()
        argv = ['dfam_corpus.py', 'verify', str(ROOT/'data/dfam-code/cases.jsonl'),
                '--tag', 'test', '--receipt', str(receipt_path)]
        with patch.object(sys, 'argv', argv), patch.object(sys, 'stderr'), patch.object(dfam_corpus, 'verify') as verify:
            with self.assertRaises(SystemExit) as error:
                dfam_corpus.main()
        self.assertEqual(error.exception.code, 2)
        verify.assert_not_called()
        self.assertEqual(receipt_path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
