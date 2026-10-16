"""Phase 3 harness checks that need neither Docker nor adamantine."""
import base64
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'physics/adamantine'))
import run_case  # noqa: E402

EVIDENCE = ROOT / 'evidence/process'


class AdamantineHarnessTest(unittest.TestCase):
    def test_vtu_block_decoding_round_trip(self):
        values = [300.0, 301.5, 473.8, 0.0]
        raw = struct.pack('<4f', *values)
        packed = zlib.compress(raw)
        header = struct.pack('<4I', 1, len(raw), len(raw), len(packed))
        encoded = base64.b64encode(header).decode() + base64.b64encode(packed).decode()
        self.assertEqual([round(v, 3) for v in run_case.decode_block(encoded)], [300.0, 301.5, 473.8, 0.0])

    def test_smoke_verdicts_follow_from_the_recorded_statistics(self):
        record = json.loads((EVIDENCE / 'adamantine-smoke-demo-316-short.json').read_text())
        self.assertEqual(record['image'], run_case.IMAGE)
        s, g = record['temperature_vertices'], record['gold_dofs']
        self.assertEqual(record['checks'], {
            'all_in_285_580': 285 < s['min'] and s['max'] < 580,
            'max_within_10pct_of_gold': abs(s['max'] - g['max']) <= 0.1 * g['max'],
            'mean_within_10pct_of_gold': abs(s['mean'] - g['mean']) <= 0.1 * g['mean']})
        self.assertTrue(record['passed'])

    def test_pipeline_energy_converges_and_mesh_keeps_volume(self):
        coarse = json.loads((EVIDENCE / 'adamantine-pipeline-dfam-001-1.0mm.json').read_text())
        fine = json.loads((EVIDENCE / 'adamantine-pipeline-dfam-001-0.5mm.json').read_text())
        for record in (coarse, fine):
            ratio = record['logged_absorbed_energy_j'] / record['expected_absorbed_energy_j']
            self.assertAlmostEqual(record['energy_ratio'], round(ratio, 4), places=4)
            self.assertEqual(record['checks']['energy_within_5pct'], abs(record['energy_ratio'] - 1) <= 0.05)
            self.assertLess(abs(record['mesh']['volume_ratio'] - 1), 0.01)
            self.assertFalse(record['manufacturing_qualified'])
        # The documented outcome: 1.0 mm cells over-deposit heat, 0.5 mm cells close the balance.
        self.assertFalse(coarse['passed'])
        self.assertTrue(fine['passed'])
        self.assertEqual(coarse['stl_sha256'], fine['stl_sha256'])

    def test_hexmesh_keeps_the_volume_of_a_cube(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('numpy not installed; the Phase 3 tools install it separately')
        import hexmesh
        corners = np.array([[x, y, z] for z in (0, 1) for y in (0, 1) for x in (0, 1)], float) * 10.0
        quads = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
        tris = corners[np.array([t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))])]
        grid, origin = hexmesh.occupancy(tris, 1.0)
        self.assertEqual(int(grid.sum()), 1000)                  # 10 x 10 x 10 one-millimetre cells
        with tempfile.TemporaryDirectory() as tmp:
            nodes, cells = hexmesh.write_gmsh(Path(tmp) / 'cube.msh', grid, origin, 1.0)
        self.assertEqual((nodes, cells), (11 ** 3, 1000))


    def test_layer_input_keeps_the_validation_workaround(self):
        # adamantine 1.1 rejects file-based deposition unless this literal root key exists.
        first = run_case.LAYERS_INFO.splitlines()[0]
        self.assertEqual(first, 'geometry.material_deposition_file layers.txt')
        self.assertIn('material_deposition_file layers.txt', run_case.LAYERS_INFO.split('geometry\n', 1)[1])
        self.assertIn('boundary_1 {{ type convective,radiative,clamped }}', run_case.LAYERS_INFO)

    def test_plate_adds_clamped_bottom_faces(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('numpy not installed; the Phase 3 tools install it separately')
        import hexmesh
        corners = np.array([[x, y, z] for z in (0, 1) for y in (0, 1) for x in (0, 1)], float) * 10.0
        quads = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
        tris = corners[np.array([t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))])]
        grid, origin = hexmesh.occupancy(tris, 1.0)
        nz, ny, nx = grid.shape
        grid, origin, layers = hexmesh.add_plate(grid, origin, 1.0, 3.0)
        self.assertEqual(layers, 3)
        self.assertAlmostEqual(origin[2] + layers * 1.0, 0.0, places=6)    # plate top at the part bottom
        self.assertEqual(int(grid[:layers].sum()), layers * ny * nx)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'plate.msh'
            hexmesh.write_gmsh(path, grid, origin, 1.0, clamp_bottom=True)
            lines = path.read_text().split('$Elements\n')[1].splitlines()
        quads_written = [l for l in lines[1:] if l.split()[1:2] == ['3']]
        self.assertEqual(len(quads_written), ny * nx)                      # one face per bottom cell
        self.assertTrue(all(l.split()[3] == '1' for l in quads_written))  # physical tag -> boundary id 1

    def test_layer_comparison_records_its_limits(self):
        record = json.loads((EVIDENCE / 'adamantine-layers-comparison.json').read_text())
        self.assertTrue(record['displacement_not_von_mises'])
        self.assertEqual(record['baseline'], 'solid')
        for name, checks in record['checks'].items():
            self.assertTrue(checks['plate_bottom_clamped'], name)
            self.assertFalse(checks['cooled_below_600_k'], name)       # the documented hot snapshot
            row = record['variants'][name]
            self.assertEqual(checks['cooled_below_600_k'], row['final_temperature_active']['max'] < 600.0)
            self.assertEqual(row['plate_bottom_max_displacement_mm'], 0.0)

    def test_grid_offset_keeps_the_part_and_the_plate_alignment(self):
        try:
            import numpy as np
        except ImportError:
            self.skipTest('numpy not installed; the Phase 3 tools install it separately')
        import hexmesh
        corners = np.array([[x, y, z] for z in (0, 1) for y in (0, 1) for x in (0, 1)], float) * 10.0
        quads = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
        tris = corners[np.array([t for a, b, c, d in quads for t in ((a, b, c), (a, c, d))])]
        grid, origin = hexmesh.occupancy(tris, 1.0, offset_xy=0.5)
        # Shifted by half a cell, a 10 mm cube covers 10 x 10 cell centres in x and y
        # (the jittered rays sit just past each centre) and keeps its 10 layers in z.
        self.assertEqual(int(grid.sum()), 1000)
        self.assertAlmostEqual(origin[2], -1.0)                            # z is not shifted
        grid, origin, layers = hexmesh.add_plate(grid, origin, 1.0, 2.0)
        self.assertAlmostEqual(origin[2] + layers * 1.0, 0.0, places=6)

if __name__ == '__main__':
    unittest.main()
