import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from check_beam_code import admitted


class BeamCodeChecks(unittest.TestCase):
    def setUp(self):
        self.request=dict(vertices_mm={'A':[0,0,0],'B':[8,0,0]},edges=[['A','B']],
                          start_diameter_mm=3,end_diameter_mm=5)
        self.code='lattice.AddBeam(new Vector3(0f, 0f, 0f), 1.5f, new Vector3(8f, 0f, 0f), 2.5f, true);'

    def test_required_graph_is_admitted(self):
        self.assertEqual(admitted(self.code,'stop',self.request)[0][3],1.5)

    def test_extra_code_wrong_radii_duplicates_and_truncation_rejected(self):
        for text,finish in [(self.code+' System.IO.File.Delete("x");','stop'),
                            (self.code.replace('1.5f','3f'),'stop'),
                            (self.code+self.code,'stop'),(self.code,'length')]:
            with self.assertRaises(ValueError):admitted(text,finish,self.request)
