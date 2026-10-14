import tempfile
from pathlib import Path
import unittest

from fixtures import fixture_points, generate
from runtime_validate import mesh_screen


class FixtureTests(unittest.TestCase):
    def test_cube_is_outward_closed_and_512_mm3(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            generate(directory)
            report = mesh_screen(directory / "input.stl")
            self.assertTrue(report["closed_edge_incidence"])
            self.assertEqual(report["degenerate_triangles"], 0)
            self.assertAlmostEqual(report["signed_volume_mm3"], 512.0)

    def test_sensor_origin_is_outside_in_normal_direction(self):
        points = fixture_points()
        self.assertEqual(len(points), 150)
        for point in points:
            for axis in range(3):
                self.assertEqual(point[7 + axis] - point[axis], 4.0 * point[3 + axis])

    def test_empty_mesh_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "empty.stl"
            path.write_bytes(b"solid empty\nendsolid empty\n")
            with self.assertRaisesRegex(ValueError, "no triangles"):
                mesh_screen(path)


if __name__ == "__main__":
    unittest.main()
