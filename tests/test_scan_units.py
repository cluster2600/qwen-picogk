"""Unit handling, checked independently of reconstruction quality.

The same 2 x 3 x 4 mm box is written in several declared units, normalized
explicitly, and compared by dimensions and volume. A companion fixture with no
declared unit must keep an unknown-scale result. Neither establishes physical accuracy.
"""
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))
from scan_units import MM_PER_UNIT, normalize, resolve_scale, rewrite_obj

EXTENTS_MM = (2., 3., 4.)
OFFSET_MM = (10., -20., 30.)
VOLUME_MM3 = 24.
REL_TOL = 1e-9  # float rounding only; a wrong or repeated conversion is off by >= 10 %
CORNERS = [(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1)]
# Outward-oriented triangles, 1-based; negative indices exercise relative OBJ references.
FACES = [(1,3,2),(1,4,3),(5,6,7),(5,7,8),(1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,4,8),(3,8,7),(4,1,5),(4,5,8)]


def write_box(path, mm_per_unit):
    lines = ['# synthetic 2 x 3 x 4 mm box', 'o box', 'mtllib never-opened.mtl']
    for corner in CORNERS:
        lines.append('v %r %r %r' % tuple((o+c*e)/mm_per_unit for o, c, e in zip(OFFSET_MM, corner, EXTENTS_MM)))
    lines.append('vn 0 0 1')
    lines += ['f %d %d %d' % tuple(i-9 for i in face) for face in FACES]
    Path(path).write_text('\n'.join(lines)+'\n')


def measure(path):
    """Axis-aligned extents, minimum corner and enclosed volume of a triangle OBJ."""
    vertices, faces = [], []
    for line in Path(path).read_text().splitlines():
        f = line.split()
        if f and f[0] == 'v':
            vertices.append([float(x) for x in f[1:]])
        elif f and f[0] == 'f':
            faces.append([int(x.split('/')[0]) for x in f[1:]])
    faces = [[i-1 if i > 0 else len(vertices)+i for i in face] for face in faces]
    low = [min(v[k] for v in vertices) for k in range(3)]
    high = [max(v[k] for v in vertices) for k in range(3)]
    volume = 0.
    for a, b, c in faces:
        (ax,ay,az), (bx,by,bz), (cx,cy,cz) = vertices[a], vertices[b], vertices[c]
        volume += (ax*(by*cz-bz*cy) - ay*(bx*cz-bz*cx) + az*(bx*cy-by*cx))/6
    return dict(extents=[h-l for l, h in zip(low, high)], low=low, volume=volume)


class UnitNormalizationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def assertBox(self, measured):
        for got, want in zip(measured['extents']+measured['low'], EXTENTS_MM+OFFSET_MM):
            self.assertTrue(math.isclose(got, want, rel_tol=REL_TOL), (got, want))
        self.assertTrue(math.isclose(measured['volume'], VOLUME_MM3, rel_tol=REL_TOL), measured['volume'])

    def test_same_box_in_every_declared_unit_normalizes_to_the_same_millimetres(self):
        results = {}
        for unit, factor in MM_PER_UNIT.items():
            source = self.root/(unit+'.obj')
            write_box(source, factor)
            receipt = normalize(source, self.root/('out-'+unit), unit=unit)
            self.assertEqual(receipt['scale']['basis'], 'declared_unit')
            self.assertEqual(receipt['scale']['mm_per_source_unit'], factor)
            self.assertEqual(receipt['coordinates_unit'], 'mm')
            self.assertEqual(json.loads((self.root/('out-'+unit)/'scale.json').read_text()), receipt)
            results[unit] = measure(self.root/('out-'+unit)/'normalized.obj')
            self.assertBox(results[unit])
            # Faces, references and ignored records are untouched.
            keep = lambda p: [l for l in Path(p).read_text().splitlines() if not l.startswith('v ')]
            self.assertEqual(keep(source), keep(self.root/('out-'+unit)/'normalized.obj'))
        unscaled = measure(self.root/'m.obj')
        self.assertTrue(math.isclose(unscaled['volume'], VOLUME_MM3/1e9, rel_tol=REL_TOL))

    def test_the_tolerance_catches_a_missing_or_repeated_conversion(self):
        write_box(self.root/'cm.obj', 10.)
        normalize(self.root/'cm.obj', self.root/'wrong', unit='mm')
        normalize(self.root/'cm.obj', self.root/'once', unit='cm')
        normalize(self.root/'once/normalized.obj', self.root/'twice', unit='cm')
        for name, factor in [('wrong', .1), ('twice', 10.)]:
            measured = measure(self.root/name/'normalized.obj')
            with self.assertRaises(AssertionError):
                self.assertBox(measured)
            self.assertTrue(math.isclose(measured['volume'], VOLUME_MM3*factor**3, rel_tol=REL_TOL))

    def test_no_declared_unit_preserves_unknown_scale(self):
        write_box(self.root/'undeclared.obj', 1/1000)  # e.g. micrometres; nothing says so
        receipt = normalize(self.root/'undeclared.obj', self.root/'unknown')
        self.assertEqual(receipt['scale'], dict(status='unknown_scale', basis='unknown', declared_unit=None,
                         mm_per_source_unit=None, conversion_verified=False, physical_scale_verified=False))
        self.assertIsNone(receipt['coordinates_unit'])
        self.assertIsNone(receipt['normalized_obj_sha256'])
        self.assertFalse((self.root/'unknown/normalized.obj').exists())
        self.assertIsNone(receipt['downstream_mm_per_unit'])
        # Source-unit bounds remain available for a person to declare the unit.
        for got, want in zip(receipt['bounds_source_units'][0], OFFSET_MM):
            self.assertTrue(math.isclose(got, want*1000, rel_tol=REL_TOL))

    def test_receipt_distinguishes_verified_conversion_from_supplied_assumption(self):
        declared, assumed = resolve_scale(unit='cm'), resolve_scale(assumed_mm_per_unit=1)
        self.assertEqual((declared['basis'], declared['conversion_verified']), ('declared_unit', True))
        self.assertEqual((assumed['basis'], assumed['conversion_verified']), ('supplied_assumption', False))
        self.assertEqual(assumed['mm_per_source_unit'], 1.)
        self.assertFalse(declared['physical_scale_verified'] or assumed['physical_scale_verified'])

    def test_conflicting_unsupported_or_malformed_scale_is_refused(self):
        bad = [dict(unit='cm', assumed_mm_per_unit=1.), dict(unit='ft'), dict(unit='CM'),
               dict(assumed_mm_per_unit=True), dict(assumed_mm_per_unit=math.nan),
               dict(assumed_mm_per_unit=0.), dict(assumed_mm_per_unit=25.4), dict(assumed_mm_per_unit='1')]
        for kwargs in bad:
            with self.assertRaises(ValueError, msg=kwargs):
                resolve_scale(**kwargs)
        source = self.root/'bad.obj'
        for text in ['v 0 0 0 1\n', 'v nan 0 0\n', 'v 0 0\n', 'f 1 2 3\n']:
            source.write_text(text)
            with self.assertRaises(ValueError, msg=text):
                rewrite_obj(source)
        source.write_text('v 1e306 0 0\n')
        with self.assertRaises(ValueError):
            normalize(source, self.root/'overflow', unit='m')
        self.assertFalse((self.root/'overflow').exists())

    def test_output_directory_must_be_new(self):
        write_box(self.root/'mm.obj', 1.)
        normalize(self.root/'mm.obj', self.root/'out', unit='mm')
        with self.assertRaises(ValueError):
            normalize(self.root/'mm.obj', self.root/'out', unit='mm')


@unittest.skipUnless(importlib.util.find_spec('trimesh') and importlib.util.find_spec('pymeshlab'),
                     'Requires the separate geometry runtime')
class NormalizedChainTests(unittest.TestCase):
    """Normalized inputs pass the unchanged intake and direct reconstruction once, at 1 mm/unit."""

    def test_reconstructed_dimensions_and_volume_match_across_declared_units(self):
        import trimesh
        from scan_mesh import inspect, reconstruct
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for unit, factor in MM_PER_UNIT.items():
                write_box(root/(unit+'.obj'), factor)
                receipt = normalize(root/(unit+'.obj'), root/unit, unit=unit)
                metadata = inspect(root/unit/'normalized.obj', root/unit/'intake')
                self.assertEqual(metadata['input_sha256'], receipt['normalized_obj_sha256'])
                request = dict(triangles=metadata['triangles'], boundary_edges=metadata['boundary_edges'],
                               connected_surface_components=metadata['connected_surface_components'],
                               user_allows_demo_assumptions=True,
                               mm_per_source_unit_assumed=receipt['downstream_mm_per_unit'], voxel_mm_assumed=.5)
                plan = dict(method='direct_voxelization', target_faces=300000, poisson_depth=9,
                            mm_per_source_unit=1., voxel_mm=.5, manufacturing_qualified=False)
                (root/unit/'plan.json').write_text(json.dumps(dict(request=request, raw_response=json.dumps(plan),
                                                                    finish_reason='stop')))
                reconstruct(root/unit/'intake', root/unit/'plan.json', root/unit/'reconstruction')
                mesh = trimesh.load(root/unit/'reconstruction/reconstructed.stl', force='mesh')
                # The rigid PCA pose orders the box axes by extent.
                for got, want in zip(sorted(mesh.extents), sorted(EXTENTS_MM)):
                    self.assertTrue(math.isclose(got, want, rel_tol=1e-6), (unit, got, want))
                self.assertTrue(math.isclose(mesh.volume, VOLUME_MM3, rel_tol=1e-6), (unit, mesh.volume))
