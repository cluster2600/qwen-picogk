import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))

import contracts
import infer
import evaluate

ROOT = Path(__file__).resolve().parents[1]


class ReleaseContracts(unittest.TestCase):
    def test_reorganized_layout_preserves_parent_and_gallery_identity(self):
        for name, expected in {
            'infer.py': '1914af0d4926ba017b381419a83581ab64d9591ca10d5a69c9e0f3be87d891df',
            'release.json': '93e05fac0c2113de9b851aaf8b5ad03669600ae02bc2a1243f6736c4939bdeb7',
        }.items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), expected)
        receipt = json.loads((ROOT/'docs/visuals/generated/gallery.json').read_text())
        self.assertEqual(hashlib.sha256((ROOT/'contracts/__init__.py').read_bytes()).hexdigest(),
                         receipt['source_sha256']['contracts.py'])
        self.assertEqual(Path(evaluate.__file__), ROOT/'scripts/evaluate.py')
        for name in ['planner', 'selector', 'scan-demo']:
            self.assertTrue((ROOT/'training/configs'/f'{name}.yaml').is_file())
            self.assertFalse((ROOT/f'training-{name}.yaml').exists())

    def setUp(self):
        self.request = json.loads((ROOT/'examples/pipe-fr.json').read_text())

    def test_mixed_units_and_radial_roles(self):
        self.assertEqual(contracts.normalize(self.request)['parameters_mm'], [12, 8.5, 2])
        changed = copy.deepcopy(self.request)
        changed['fields']['outer'] = dict(value='17', unit='mm', quantity='diameter')
        self.assertEqual(contracts.normalize(changed), contracts.normalize(self.request))

    def test_bcc_diameter(self):
        request = dict(recipe='bcc', language='en', interface_status='synthetic', fields={
            'cell_side': dict(value=12, unit='mm', quantity='length'),
            'beam': dict(value=1, unit='mm', quantity='radius')})
        self.assertEqual(contracts.normalize(request)['parameters_mm'], [12, 2])

    def test_unknown_interfaces_refuse(self):
        request = json.loads((ROOT/'examples/unverified.json').read_text())
        self.assertEqual(contracts.normalize(request)['recipe'], 'needs_measurement')

    def test_invalid_inputs_fail_closed(self):
        for key, value in [('value', True), ('value', '1,000.1'), ('value', float('nan')),
                           ('quantity', 'length'), ('unit', 'inch')]:
            request = copy.deepcopy(self.request)
            request['fields']['outer'][key] = value
            with self.assertRaises(ValueError):
                contracts.normalize(request)

    def test_duplicate_keys_and_incomplete_generation(self):
        with self.assertRaises(ValueError):
            contracts.parse('{"recipe":"pipe","recipe":"pipe","parameters_mm":[12,8.5,2],"missing":[]}')
        correct = json.dumps(contracts.normalize(self.request))
        with self.assertRaises(ValueError):
            contracts.accepted(correct, 'length', self.request)
        with self.assertRaises(ValueError):
            contracts.accepted(correct.replace('8.5', '8.0'), 'stop', self.request)

    def test_bad_geometry_bounds(self):
        for recipe, params in [('pipe', [12, 2, 3]), ('bcc', [12, 5]), ('thread', [20, 8, 2, 1]), ('cylinder', [25, 2])]:
            with self.assertRaises(ValueError):
                contracts.parse(json.dumps(dict(recipe=recipe, parameters_mm=params, missing=[])))

    def test_changed_or_escaping_weights_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder/'weights').write_text('original')
            sha = infer.digest(folder/'weights')
            infer.verify_files(folder, {'weights': sha})
            (folder/'weights').write_text('tampered')
            with self.assertRaises(ValueError):
                infer.verify_files(folder, {'weights': sha})
            with self.assertRaises(ValueError):
                infer.verify_files(folder, {'../weights': sha})

    def test_all_exported_intents_match(self):
        for case in json.loads((ROOT/'data/planner/cases.json').read_text()):
            self.assertEqual(contracts.normalize(case['request']), case['expected'], case['id'])
            self.assertTrue(contracts.matches(contracts.parse(case['messages'][2]['content']), case['expected']))

    def test_native_metrics_survive_disposal_diagnostics(self):
        metrics = dict(volume=2595.0, triangles=100, roundtrip_triangles=100,
                       material_inside=True, distant_point_inside=False, axis_inside=False)
        stdout = json.dumps(metrics)+'\nDisposing Library\nDone Disposing Library\n'
        with patch('evaluate.subprocess.run', return_value=SimpleNamespace(stdout=stdout)):
            result = evaluate.native(contracts.normalize(self.request), Path('host.dll'))
            self.assertLess(result['relative_volume_error'], 0.15)
        with patch('evaluate.subprocess.run', return_value=SimpleNamespace(stdout=stdout+json.dumps(metrics))):
            with self.assertRaises(ValueError):
                evaluate.native(contracts.normalize(self.request), Path('host.dll'))

    def test_native_output_directory_is_preserved_and_never_reused(self):
        metrics = dict(volume=2595.0, triangles=100, roundtrip_triangles=100,
                       material_inside=True, distant_point_inside=False, axis_inside=False)
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)/'native'
            with patch('evaluate.subprocess.run', return_value=SimpleNamespace(stdout=json.dumps(metrics))):
                evaluate.native(contracts.normalize(self.request), Path('host.dll'), folder)
            self.assertEqual(json.loads((folder/'plan.json').read_text()), contracts.normalize(self.request))
            with self.assertRaises(FileExistsError):
                evaluate.native(contracts.normalize(self.request), Path('host.dll'), folder)


if __name__ == '__main__':
    unittest.main()
