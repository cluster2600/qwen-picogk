import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from scan_mesh import read_obj, inspect, inspect_closed, dominant_demo, reconstruct, digest


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


@unittest.skipUnless(importlib.util.find_spec('trimesh'), 'Requires the separate geometry runtime')
class ClosedEnvelopeTests(unittest.TestCase):
    def test_direct_reconstruction_preserves_small_acquired_closed_mesh(self):
        import json
        import trimesh
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);source=root/'box.obj'
            trimesh.creation.box(extents=[2,3,4]).export(source)
            metadata=inspect(source,root/'intake')
            request=dict(triangles=metadata['triangles'],boundary_edges=metadata['boundary_edges'],
                         connected_surface_components=metadata['connected_surface_components'],
                         user_allows_demo_assumptions=True,mm_per_source_unit_assumed=1.,voxel_mm_assumed=.5)
            plan=dict(method='direct_voxelization',target_faces=300000,poisson_depth=9,
                      mm_per_source_unit=1.,voxel_mm=.5,manufacturing_qualified=False)
            binding=root/'plan.json';binding.write_text(json.dumps(dict(request=request,raw_response=json.dumps(plan),finish_reason='stop')))
            reconstruct(root/'intake',binding,root/'reconstruction')
            result=json.loads((root/'reconstruction/reconstruction.json').read_text())
            self.assertEqual(result['triangles'],12)
            self.assertEqual(result['dust_faces_removed'],0)

    def test_closed_box_metadata_and_open_surface_refusal(self):
        import trimesh
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);p=root/'box.stl'
            mesh=trimesh.creation.box(extents=[2,3,4]);mesh.export(p)
            result=inspect_closed(p,root/'closed')
            self.assertEqual(result['boundary_edges'],0)
            self.assertEqual(result['connected_surface_components'],1)
            mesh.update_faces([True]*11+[False]);mesh.export(p)
            with self.assertRaises(ValueError):inspect_closed(p,root/'open')

    def test_unregistered_minor_surface_is_retained_separately_but_large_assembly_refused(self):
        import json
        import numpy as np
        import trimesh
        with tempfile.TemporaryDirectory()as directory:
            root=Path(directory);intake=root/'intake';intake.mkdir()
            main=trimesh.creation.box(extents=[2,3,4])
            minor=trimesh.Trimesh([[10,0,0],[10,.1,0],[10,0,.1]],[[0,1,2]],process=False)
            def save_mesh(mesh):
                np.savez_compressed(intake/'prepared.npz',vertices=mesh.vertices,faces=mesh.faces)
                (intake/'intake.json').write_text(json.dumps(dict(prepared_npz_sha256=digest(intake/'prepared.npz'))))
            save_mesh(trimesh.util.concatenate([main,minor]))
            result=dominant_demo(intake,root/'dominant')
            self.assertEqual(result['omitted_triangles'],1)
            self.assertTrue((root/'dominant/unregistered-fragments.stl').is_file())
            other=main.copy();other.apply_translation([10,0,0])
            save_mesh(trimesh.util.concatenate([main,other]))
            with self.assertRaises(ValueError):dominant_demo(intake,root/'assembly')
