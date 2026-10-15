"""Real-engine tests in the pinned PyMesh image; independent checks in geometry image."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
import scan_pymesh
from scan_mesh import digest, pymesh_intake


class PyMeshRegistration(unittest.TestCase):
    def test_required_worker_and_runtime_are_hash_bound(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root/'config/scan-demo.json').read_text())
        self.assertEqual(manifest['pymesh_runtime']['version'], '0.3')
        self.assertIn('@sha256:', manifest['pymesh_runtime']['image'])
        self.assertEqual(manifest['sources_sha256']['scripts/scan_pymesh.py'], digest(root/'scripts/scan_pymesh.py'))
        receipt = json.loads((root/'evidence/scan-demo/pymesh-integration-20261015.json').read_text())
        self.assertEqual(receipt['sources_sha256'], manifest['sources_sha256'])
        self.assertEqual(receipt['runtime'], manifest['pymesh_runtime'])
        self.assertEqual(receipt['status'], 'demo_geometry_passed')
        self.assertTrue(all(receipt['checks'].values()))
        self.assertFalse(receipt['manufacturing_qualified'])


@unittest.skipUnless(importlib.util.find_spec('pymesh'), 'Requires the pinned PyMesh image')
class PyMeshEngineTests(unittest.TestCase):
    def intake(self, root):
        import numpy as np
        root.mkdir()
        vertices = np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,0.],[9.,9.,9.]])
        faces = np.array([[0,1,2],[3,1,2]])
        np.savez_compressed(str(root/'prepared.npz'), vertices=vertices, faces=faces)
        (root/'intake.json').write_text(json.dumps({'prepared_npz_sha256': digest(root/'prepared.npz')}))
        return vertices, faces

    def test_real_cleanup_maps_to_unchanged_input_coordinates_and_faces(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            vertices, faces = self.intake(root/'intake')
            result = scan_pymesh.prepare(root/'intake', root/'clean')
            self.assertEqual(result['pymesh_version'], '0.3')
            self.assertEqual(result['merged_vertices'], 1)
            self.assertEqual(result['removed_isolated_vertices'], 1)
            self.assertEqual(result['output_faces'], 1)
            with np.load(str(root/'clean/cleaned.npz'), allow_pickle=False) as data:
                self.assertTrue(np.array_equal(data['vertices'], vertices[data['input_vertex_indices']]))
                self.assertTrue(np.array_equal(data['vertices'][data['faces']], vertices[faces[data['input_face_indices']]]))
            with self.assertRaises(ValueError):
                scan_pymesh.prepare(root/'intake', root/'clean')

    def test_changed_coordinates_binding_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); self.intake(root/'intake')
            with (root/'intake/prepared.npz').open('ab') as stream:
                stream.write(b'changed')
            with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                scan_pymesh.prepare(root/'intake', root/'clean')

    def test_opposite_duplicate_faces_do_not_silently_erase_a_surface(self):
        import numpy as np
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); vertices, _ = self.intake(root/'intake')
            np.savez_compressed(str(root/'intake/prepared.npz'), vertices=vertices, faces=[[0,1,2],[0,2,1]])
            (root/'intake/intake.json').write_text(json.dumps({'prepared_npz_sha256': digest(root/'intake/prepared.npz')}))
            with self.assertRaisesRegex(ValueError, 'entire acquired surface'):
                scan_pymesh.prepare(root/'intake', root/'clean')

    def test_actual_intersection_detector_and_unchanged_stl(self):
        import numpy as np
        import pymesh
        cases = [
            (np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]),
             np.array([[0,2,1],[0,1,3],[0,3,2],[1,2,3]]), False),
            (np.array([[0.,0.,0.],[2.,0.,0.],[0.,2.,0.],[.5,.5,-1.],[.5,.5,1.],[1.5,.5,0.]]),
             np.array([[0,1,2],[3,4,5]]), True),
        ]
        for vertices, faces, intersects in cases:
            with self.subTest(intersects=intersects), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); native = root/'native'; native.mkdir()
                pymesh.save_mesh(str(native/'candidate.stl'), pymesh.form_mesh(vertices, faces))
                before = digest(native/'candidate.stl')
                (native/'native.json').write_text(json.dumps({'output_sha256': before}))
                result = scan_pymesh.audit(native, root/'audit')
                self.assertEqual(result['self_intersection_pairs'] > 0, intersects)
                self.assertEqual(digest(native/'candidate.stl'), before)
                self.assertFalse(result['repair_performed'])
                (native/'native.json').write_text(json.dumps({'output_sha256': '0'*64}))
                with self.assertRaisesRegex(ValueError, 'hash mismatch'):
                    scan_pymesh.audit(native, root/'bad-audit')


@unittest.skipUnless(importlib.util.find_spec('trimesh'), 'Requires the separate geometry image')
class IndependentPyMeshChecks(unittest.TestCase):
    def fixture(self, root):
        import numpy as np
        source = root/'intake'; cleaned = root/'pymesh'; source.mkdir(); cleaned.mkdir()
        vertices = np.array([[0.,0.,0.],[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]])
        faces = np.array([[0,2,1],[0,1,3],[0,3,2],[1,2,3]])
        np.savez_compressed(source/'prepared.npz', vertices=vertices, faces=faces)
        (source/'intake.json').write_text(json.dumps({'prepared_npz_sha256': digest(source/'prepared.npz')}))
        return source, cleaned, vertices, faces

    def write_clean(self, source, cleaned, vertices, faces, vi, fi):
        import numpy as np
        np.savez_compressed(cleaned/'cleaned.npz', vertices=vertices, faces=faces,
                            input_vertex_indices=vi, input_face_indices=fi)
        (cleaned/'pymesh.json').write_text(json.dumps({'input_npz_sha256': digest(source/'prepared.npz'),
            'output_npz_sha256': digest(cleaned/'cleaned.npz'), 'duplicate_vertex_tolerance': 0.0}))

    def test_surface_preserved_and_topology_recomputed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source, cleaned, v, f = self.fixture(root)
            self.write_clean(source, cleaned, v, f, list(range(4)), list(range(4)))
            result = pymesh_intake(source, cleaned, root/'verified')
            self.assertEqual(result['boundary_edges'], 0)
            self.assertEqual(result['triangles'], 4)
            self.assertTrue(result['cleanup_preserves_acquired_surface'])
            self.assertFalse(result['cleanup_vertices_moved'])

    def test_moved_vertex_missing_surface_and_orientation_changes_are_rejected(self):
        for defect in ['move', 'missing', 'orientation', 'bad-map', 'duplicate', 'opposing-source']:
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                root = Path(tmp); source, cleaned, v, f = self.fixture(root)
                vi, fi = list(range(4)), list(range(4))
                if defect == 'move': v[0,0] += .001
                elif defect == 'missing': f, fi = f[:-1], fi[:-1]
                elif defect == 'orientation': f[0] = f[0][::-1]
                elif defect == 'bad-map': vi[0] = 99
                elif defect == 'duplicate':
                    import numpy as np
                    f = np.vstack([f, f[0]]); fi += [0]
                elif defect == 'opposing-source':
                    import numpy as np
                    np.savez_compressed(source/'prepared.npz', vertices=v, faces=np.vstack([f, f[0][::-1]]))
                    (source/'intake.json').write_text(json.dumps({'prepared_npz_sha256': digest(source/'prepared.npz')}))
                self.write_clean(source, cleaned, v, f, vi, fi)
                with self.assertRaises(ValueError):
                    pymesh_intake(source, cleaned, root/'verified')
