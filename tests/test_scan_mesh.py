import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from scan_mesh import read_obj


@unittest.skipUnless(importlib.util.find_spec('numpy'), 'Requires the separate geometry runtime')
class ScanMeshTests(unittest.TestCase):
    def test_triangle_indices_and_materials(self):
        with tempfile.TemporaryDirectory()as directory:
            p=Path(directory)/'scan.obj'
            p.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nf -3 -2 -1\nmtllib ../../never-open-this.mtl\n')
            v,f=read_obj(p)
            self.assertEqual(v.shape,(3,3))
            self.assertEqual(f.tolist(),[[0,1,2]])

    def test_malformed_nonfinite_and_polygon_input_rejected(self):
        with tempfile.TemporaryDirectory()as directory:
            p=Path(directory)/'scan.obj'
            for text in ['v 0 0 0\nf 0 1 1\n','v nan 0 0\nf 1 1 1\n',
                         'v 0 0 0\nf 1 1 1 1\n','v 0 0 0\nf 1 1 2\n']:
                p.write_text(text)
                with self.assertRaises(ValueError):read_obj(p)
