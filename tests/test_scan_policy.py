import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from scan_policy import admit, expected, execution_plan
from scan_mesh import fresh


class ScanPolicyTests(unittest.TestCase):
    def setUp(self):
        self.request=dict(triangles=1240000,boundary_edges=8600,connected_surface_components=2,
                          mm_per_source_unit_assumed=1.,voxel_mm_assumed=.5,user_allows_demo_assumptions=True)

    def test_open_and_closed_scan_policy(self):
        p=expected(self.request)
        self.assertEqual(admit(json.dumps(p),'stop',self.request)['method'],'screened_poisson')
        self.request['boundary_edges']=0
        self.assertEqual(expected(self.request)['method'],'direct_voxelization')

    def test_wrong_method_scale_resolution_qualification_and_truncation_fail(self):
        p=expected(self.request)
        for field,value in [('method','direct_voxelization'),('voxel_mm',5.),('mm_per_source_unit',2.),
                            ('manufacturing_qualified',True),('poisson_depth',9.)]:
            bad=dict(p);bad[field]=value
            with self.assertRaises(ValueError):admit(json.dumps(bad),'stop',self.request)
        with self.assertRaises(ValueError):admit(json.dumps(p),'length',self.request)
        with self.assertRaises(ValueError):admit(json.dumps(p)[:-1]+',"voxel_mm":0.5}','stop',self.request)
        self.request['user_allows_demo_assumptions']=False
        with self.assertRaises(ValueError):expected(self.request)

    def test_private_output_and_no_overwrite(self):
        with tempfile.TemporaryDirectory()as tmp:
            root=Path(tmp);(root/'.git').mkdir()
            with self.assertRaises(ValueError):fresh(root/'published')
            private=fresh(root/'work/demo')
            self.assertTrue(private.is_dir())
            with self.assertRaises(ValueError):fresh(private)

    def test_execution_budget_is_bounded_without_changing_exact_preset_score(self):
        p=expected(self.request);p['target_faces']=300000
        with self.assertRaises(ValueError):admit(json.dumps(p),'stop',self.request)
        self.assertEqual(execution_plan(json.dumps(p),'stop',self.request)['target_faces'],300000)
        for key,value in [('target_faces',450000),('voxel_mm',5),('method','direct_voxelization'),('mm_per_source_unit',True)]:
            bad={**p,key:value}
            with self.assertRaises(ValueError):execution_plan(json.dumps(bad),'stop',self.request)
