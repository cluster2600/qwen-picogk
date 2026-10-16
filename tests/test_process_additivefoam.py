"""Phase 2 harness checks that need neither Docker nor AdditiveFOAM."""
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'physics/additivefoam'))
import run_track  # noqa: E402


class ProcessHarnessTest(unittest.TestCase):
    def test_steady_window_uses_only_the_middle_of_the_track(self):
        speed = 0.8
        # Sample times sit between the window edges, so rounding cannot decide membership.
        times = [(i + 0.5) * 1e-5 for i in range(300)]
        rows = [{'t': t, 'length': 3e-4 if 1e-3 <= t <= 2.25e-3 else 9e-4,
                 'width': 1.2e-4, 'depth': 4e-5} for t in times]
        result = run_track.steady(rows, speed)
        self.assertAlmostEqual(result['length_um'], 300.0)
        self.assertEqual(result['length_sd_um'], 0.0)
        self.assertEqual(result['window_s'], [0.001, 0.00225])
        with self.assertRaises(ValueError):
            run_track.steady(rows[:50], speed)

    def test_lack_of_fusion_and_conduction_indicators(self):
        # Tang, Pistorius and Beuth (2017): (h/W)^2 + (L/D)^2 <= 1 for full overlap.
        ok = run_track.indicators(width_um=200, depth_um=80, layer_m=40e-6, hatch_m=100e-6)
        self.assertAlmostEqual(ok['lack_of_fusion_criterion'], 0.5)
        self.assertFalse(ok['lack_of_fusion_risk'])
        self.assertFalse(ok['beyond_conduction_model'])
        risky = run_track.indicators(width_um=100, depth_um=30, layer_m=40e-6, hatch_m=100e-6)
        self.assertTrue(risky['lack_of_fusion_risk'])
        self.assertTrue(run_track.indicators(width_um=100, depth_um=60)['beyond_conduction_model'])

    def test_dimension_csv_is_read_in_metres(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / '1709.csv'
            path.write_text('time(s),length(m),width(m),depth(m)\n0.001,3e-4,1.2e-4,4e-5\n')
            self.assertEqual(run_track.read_dimensions(path),
                             [{'t': 0.001, 'length': 3e-4, 'width': 1.2e-4, 'depth': 4e-5}])

    def test_published_evidence_is_consistent(self):
        smoke = json.loads((ROOT / 'evidence/process/additivefoam-smoke-amb2018-02-b-20um.json').read_text())
        comparison = smoke['comparison']
        self.assertEqual(comparison['measured_length_um'], 359.0)
        self.assertFalse(comparison['within_2sd'])                     # the documented failure stays visible
        self.assertEqual(smoke['provenance']['additivefoam_commit'], run_track.ADDITIVEFOAM_COMMIT)
        sweep = json.loads((ROOT / 'evidence/process/additivefoam-316l-single-track-sweep.json').read_text())
        self.assertTrue(sweep['uncalibrated_for_any_machine'])
        self.assertFalse(sweep['manufacturing_qualified'])
        self.assertEqual(len(sweep['cases']), 25)
        for case in sweep['cases']:
            pool = case['melt_pool']['1709']
            expect = run_track.indicators(pool['width_um'], pool['depth_um'], sweep['layer_m'], sweep['hatch_m'])
            self.assertEqual(case['indicators'], expect)

    def test_validation_verdicts_follow_from_recorded_numbers(self):
        record = json.loads((ROOT / 'evidence/process/additivefoam-amb2018-02-abc-validation.json').read_text())
        self.assertIn('fixed before cases A and C were run', record['acceptance'])
        iso = f"{record['isotherm_k']:g}"
        self.assertEqual(iso, '1563.15')                                 # NIST's 1290 degC threshold
        verdicts = {}
        for case in record['cases']:
            name, ref, pool = case['case'][-1].upper(), case['reference'], case['melt_pool'][iso]
            self.assertEqual(ref, run_track.AMMT[name])
            length_ok = abs(pool['length_um'] - ref['length_um']) <= 2 * ref['length_sd_um']
            self.assertEqual(case['checks']['length_within_2sd'], length_ok)
            for key in ('width', 'depth'):
                ok = abs(pool[f'{key}_um'] - ref[f'{key}_um']) <= 0.10 * ref[f'{key}_um']
                self.assertEqual(case['checks'][f'{key}_within_10pct'], ok)
            verdicts[name] = (length_ok, case['checks']['width_within_10pct'], case['checks']['depth_within_10pct'])
        # The documented outcome: width passes everywhere, length nowhere, depth fails for A.
        self.assertEqual(verdicts, {'A': (False, True, False), 'B': (False, True, True), 'C': (False, True, True)})

    def test_dockerfile_pins_base_key_and_commit(self):
        text = (ROOT / 'physics/additivefoam/Dockerfile').read_text()
        self.assertIn('ubuntu:24.04@sha256:', text)
        self.assertIn(f'ADDITIVEFOAM_COMMIT={run_track.ADDITIVEFOAM_COMMIT}', text)
        self.assertRegex(text, r'OPENFOAM_KEY_SHA256=[0-9a-f]{64}')


if __name__ == '__main__':
    unittest.main()
