"""Author new synthetic API/Boolean correction cases; never read held-out tasks."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]
spec = importlib.util.spec_from_file_location('prior_teaching_author', WORK / 'data/corrective-001/author.py')
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def generate():
    if (ROOT / 'cases').exists() or (ROOT / 'train.jsonl').exists():
        raise FileExistsError('Preserve authored cases; use a separate revision.')
    (ROOT / 'cases').mkdir()
    rows, cases = [], []

    def add(label, family, variant, body, classes, oracle, task, explanation,
            helpers='', fixture=None, kind='geometry'):
        ident = f'correction-{label}-{variant+1:02d}'
        folder = ROOT / 'cases' / ident
        folder.mkdir()
        name = 'input.dat' if fixture is None else fixture[0]
        if fixture is None:
            (folder / name).write_text('synthetic unused input\n')
        elif isinstance(fixture[1], bytes):
            (folder / name).write_bytes(fixture[1])
        else:
            (folder / name).write_text(fixture[1])
        header = old.HEADER
        if kind == 'refusal':
            header = header.replace('        // Native geometry is disposed before this explicitly owned context.\n        using Library lib = new(0.2f);',
                                    '        // Unsigned observations do not justify native geometry.')
        code = header.replace('__BODY__', body).replace('__FINISH__', old.EXPORT if kind == 'geometry' else '')
        code = code.replace('__HELPERS__', helpers).replace('__CLASSES__', classes).rstrip() + '\n'
        (folder / 'Program.cs').write_text(code)
        card = old.CARD
        if kind == 'refusal':
            card = card.replace('Use an explicit headless Library with scoped disposal. ',
                                'Do not initialize PicoGK for a refusal. ')
        prompt = card + task
        answer = explanation + '\n\n```csharp\n' + code + '```'
        rows.append({'messages': [{'role': 'user', 'content': prompt}, {'role': 'assistant', 'content': answer}]})
        cases.append(dict(id=ident, family=family, variant=variant+1, kind=kind,
            source=str((folder / 'Program.cs').relative_to(ROOT)), source_sha256=sha(folder / 'Program.cs'),
            input=str((folder / name).relative_to(ROOT)), input_sha256=sha(folder / name), oracle=oracle))

    centres = [[.6, -1.6, .8], [-1.4, .6, -.6], [1., 1.4, -.2], [-.2, -.8, 1.2]]
    delegate = '''public sealed class ValueField(Func<Vector3,float> value) : IImplicit
{
    public float fSignedDistance(in Vector3 p) => value(p);
}
'''
    safe_hull = '''public sealed class CaptureSafeHull(List<(Vector3 point,Vector3 normal)> planes) : IImplicit
{
    public float fSignedDistance(in Vector3 p)
    {
        // Copy the readonly-reference argument before a lambda captures its value.
        Vector3 sample=p;
        return planes.Max(plane=>Vector3.Dot(sample-plane.point,plane.normal));
    }
}
'''
    for i, centre in enumerate(centres):
        v, f = old.vec, old.f
        half = [3.12+.16*i, 3.44+.12*i, 2.86+.18*i]
        box_oracle = dict(shape='box', centre=centre, half=half)
        bbox = 'new BBox3(new Vector3(-8),new Vector3(8))'
        task_dims = f'Centre {centre} mm, half-extents {half} mm; render [-8,8]^3 mm.'
        body = f'''        Vector3 centre={v(centre)}, half={v(half)};
        // Func<Vector3,float> takes Vector3 by value, unlike the IImplicit method.
        Func<Vector3,float> distance=p=>
        {{
            Vector3 q=Vector3.Abs(p-centre)-half;
            return Vector3.Max(q,Vector3.Zero).Length()+MathF.Min(MathF.Max(q.X,MathF.Max(q.Y,q.Z)),0f);
        }};
        using Voxels part=new(lib,new ValueField(distance),{bbox});'''
        add('value-lambda', 'value-lambda', i, body, delegate, box_oracle,
            'Correct a Func<Vector3,float> lambda incorrectly declaring its argument with in; implement the complete value-delegate adapter to IImplicit and export a box. '+task_dims,
            'Func uses a value argument; IImplicit alone declares its method argument with in. Both exports come from the same box field.')
        planes = []
        for axis in range(3):
            for sign in (-1, 1):
                point = centre.copy(); point[axis] += sign*half[axis]
                normal = [0, 0, 0]; normal[axis] = sign
                planes.append(f'({v(point)},{v(normal)})')
        body = f'''        var planes=new List<(Vector3 point,Vector3 normal)> {{ {','.join(planes)} }};
        using Voxels part=new(lib,new CaptureSafeHull(planes),{bbox});'''
        add('reference-capture', 'reference-capture', i, body, safe_hull, box_oracle,
            'Fix CS1628 in IImplicit.fSignedDistance(in Vector3 p): a Max lambda must not capture p directly. Copy its value locally; intersect six axis-aligned outward tangent planes for this box. '+task_dims,
            'A local value copy permits the lambda while preserving the required readonly-reference interface. This convex teaching hull is not general calibrated scan fusion.')
        radius = [2.74, 3.06, 3.34, 3.58][i]
        wall = [1.08, 1.16, 1.24, 1.32][i]
        body = f'''        using Lattice seed=new(lib);
        seed.AddSphere({v(centre)},{f(radius)});
        using Voxels part=new(seed);
        // Preserve the outer envelope; erode only this independent copy.
        using Voxels cavity=new(part); cavity.Offset(-{f(wall)});
        part.BoolSubtract(cavity);'''
        add('outer-copy', 'shell', i, body, '', dict(shape='shell', centre=centre, radius=radius, wall=wall),
            f'A shell vanished because its outer sphere was eroded before subtracting an identical inner sphere. Keep the outer radius {radius} mm at {centre}, subtract only a separately eroded copy, wall {wall} mm.',
            'Eroding the outer sphere and then subtracting the same inner sphere removes everything. A copied cavity preserves the outer envelope; this sealed coupon has no powder-evacuation approval.')
        vent = [1.62, 1.76, 1.88, 2.02][i]
        body = f'''        using Voxels part=new(lib,new Box({v(centre)},{v(half)}),{bbox});
        using Voxels cavity=new(part); cavity.Offset(-{f(wall)}); part.BoolSubtract(cavity);
        // A fresh lattice contains only the drain; never reuse a lattice holding the envelope.
        using Lattice drill=new(lib);
        drill.AddBeam({v([centre[0],centre[1],centre[2]-half[2]-.6])},{f(vent)},
                      {v(centre)},{f(vent)},false);
        using Voxels cutter=new(drill); part.BoolSubtract(cutter);'''
        add('fresh-cutter', 'vent', i, body, old.BOX,
            dict(shape='vent', centre=centre, half=half, wall=wall, vent_radius=vent),
            f'A drain subtraction erased the part because its cutter lattice also contained the full envelope. Make a fresh cutter-only lattice, hollow a box with wall {wall} mm, and subtract a flat bottom port radius {vent} mm. '+task_dims,
            'Primitive unions remain in their lattice, so an independent cutter prevents subtracting the envelope itself. Digital connectivity does not prove physical powder evacuation.')
        body = f'        using Voxels part=new(lib,new Box({v(centre)},{v(half)}),{bbox});'
        add('box-api', 'debug-api', i, body, old.BOX, box_oracle,
            'Replace nonexistent Lattice.AddBox and Lattice.AddImplicit calls with a complete Box : IImplicit rendered through Voxels(lib,field,bounds). Export the specified box, not a sphere or cylinder. '+task_dims,
            'Lattice has no AddBox or AddImplicit in this pinned API. Render the specified implicit box directly and mesh that same field for STL.')
        for which, family in enumerate(('gyroid', 'diamond', 'schwarz-p')):
            cell = [5.92, 6.28, 6.62, 7.08][i]
            extent = 3.48+.14*i
            origin = [x-cell/4 for x in centre] if which == 2 else centre
            body = f'''        using Voxels phase=new(lib,new Phase({v(origin)},{f(cell)},{which}),{bbox});
        using Mesh zeroSet=new(phase); using Voxels distance=new(zeroSet);
        using Voxels part=new(distance); using Voxels inner=new(distance);
        part.Offset({f(wall/2)}); inner.Offset(-{f(wall/2)}); part.BoolSubtract(inner);
        part.Trim(new BBox3({v([x-extent for x in centre])},{v([x+extent for x in centre])}));
        part.Offset(.05f); part.Offset(-.05f);'''
            add('float-'+family, family, i, body, old.TPMS,
                dict(shape='tpms', kind=which, centre=centre, origin=origin, cell=cell, wall=wall, extent=extent),
                f'Fix a {family} implementation using nonexistent Mathf and double-valued literals in a float-returning field. Use MathF and float constants, full IImplicit helper, period {cell} mm, phase origin {origin}, sheet width {wall} mm; re-distance before offsets and clip about {centre} to half-side {extent} mm. Do not call Lattice.AddImplicit.',
                'MathF keeps the Fourier carrier in float arithmetic; Mesh-to-Voxels re-distances before millimetre offsets. Von Schnering–Nesper (1991) nodal geometry supplies neither Sigmund optimization nor an LPBF support-free guarantee.')
        fixture_path = ROOT / f'temporary-{i}.stl'
        old.stl(fixture_path, centre, half)
        fixture_bytes = fixture_path.read_bytes(); fixture_path.unlink()
        mesh_body = '''        using Mesh scan=Mesh.mshFromStlFile(args[0],Mesh.EStlUnit.MM,libSet:lib);
        if(scan.nTriangleCount()==0) throw new InvalidDataException("Empty scan.");
        using Voxels part=new(scan);'''
        add('mesh-rebuild', 'stl-roundtrip', i, mesh_body, '', box_oracle,
            'Fix nonexistent Mesh.Clear: load the actual closed outward millimetre STL, voxelize it, construct a new clean mesh from those Voxels, and append only nonzero-area triangles. Preserve input pose and support replacement input geometry; no hardcoded replacement.',
            'Construct a new Mesh(lib) instead of clearing a mesh. The exports represent the voxelized input, with only exactly zero-area triangles omitted.', fixture=('scan.stl', fixture_bytes))
        body = mesh_body + f'''
        using Voxels cavity=new(part); cavity.Offset(-{f(wall)}); part.BoolSubtract(cavity);
        BBox3 bounds=part.oCalculateBoundingBox();
        // BBox3 exposes vecMin/vecMax, not min/max; derive the drain from actual input bounds.
        Vector3 mid=(bounds.vecMin+bounds.vecMax)/2f;
        using Lattice drill=new(lib);
        drill.AddBeam(new(mid.X,mid.Y,bounds.vecMin.Z-.6f),{f(vent)},new(mid.X,mid.Y,mid.Z),{f(vent)},false);
        using Voxels cutter=new(drill); part.BoolSubtract(cutter);'''
        add('bbox-members', 'stl-skin-vent', i, body, '',
            dict(shape='vent', centre=centre, half=half, wall=wall, vent_radius=vent),
            f'Fix BBox3.min/max member errors using vecMin/vecMax. Load the actual closed outward STL in mm, hollow it with wall {wall} mm and create a fresh flat bottom cutter radius {vent} mm from actual bounds. Do not substitute a fixed box or recenter input.',
            'Use the actual BBox3 vector members and an independent drain lattice. Wall thickness and a digital opening alone do not establish powder removal or Mercelis–Kruth (2006) residual-stress control.', fixture=('scan.stl', fixture_bytes))
        points = [[centre[0]-2.2,centre[1],centre[2]], [centre[0]+2.2,centre[1],centre[2]],
                  [centre[0],centre[1]-2.4,centre[2]+1.1], [centre[0],centre[1]+2.4,centre[2]-1.1]]
        delim = [';', ',', ' ', '\t'][i]
        text = '# synthetic unsigned samples\n'+delim.join(('X','Y','Z'))+'\n'+''.join(delim.join(str(x) for x in p)+'\n' for p in points)
        splat = [.78, .90, 1.02, 1.14][i]
        body = f'''        var points=ReadXYZ(args[0]);
        using Lattice samples=new(lib);
        foreach(Vector3 sample in points) samples.AddSphere(sample,{f(splat)});
        using Voxels part=new(samples);'''
        add('safe-xyz', 'xyz-occupancy', i, body, '',
            dict(shape='splats', points=points, radius=splat, parser='xyz'),
            f'Replace StreamReader with File.ReadLines and use only System.Collections.Generic for collections. Parse actual unsigned XYZ, all four separators and optional header, reject malformed/nonfinite/empty data. Preserve disconnected sample balls radius {splat} mm; no signed reconstruction.',
            'File.ReadLines follows the permitted API; coordinates are validated before geometry. Unoriented splats are occupancy proxies, not Curless–Levoy (1996) signed range integration.',
            helpers=old.XYZ, fixture=('observations.xyz', text))
        missing = [['calibrated_depth_images','camera_extrinsics','oriented_samples'],
                   ['registered_camera_poses','depth_confidence','outward_normals'],
                   ['range_pixel_calibration','ray_origins','normal_orientation'],
                   ['depth_visibility','camera_intrinsics','signed_observations']][i]
        body = '''        bool valid=true;
        try { ReadXYZ(args[0]); }
        catch(FormatException) { valid=false; }
        catch(InvalidDataException) { valid=false; }
        File.WriteAllText(Path.Combine(args[1],"refused.json"),JsonSerializer.Serialize(new {
            status="needs_measurement",manufacturing_authorized=false,input_valid=valid,
            missing=__MISSING__ }));'''.replace('__MISSING__', 'new[]{'+','.join(json.dumps(x) for x in missing)+'}')
        add('safe-refusal', 'signed-range-refusal', i, body, '',
            dict(shape='unsigned-refusal', missing=missing, input_valid=True),
            f'Use File.ReadLines, System.Collections.Generic, and no prohibited namespaces to validate unsigned XYZ. Always refuse signed reconstruction with input_valid and missing exactly {missing}; never create geometry or initialize PicoGK, even if syntax is valid.',
            'Unsigned XYZ lacks orientation and calibrated visibility for Curless–Levoy (1996) integration. The refusal reports missing evidence without inventing a signed surface.',
            helpers=old.XYZ, fixture=('unsigned.xyz', text), kind='refusal')
    assert len(cases) == len(rows) == 48
    output = ROOT / 'train.jsonl'
    output.write_text(''.join(json.dumps(row, ensure_ascii=False, separators=(',',':'))+'\n' for row in rows))
    manifest = dict(schema='picogk.am.compact-teaching@1', count=48, train_sha256=sha(output),
        author_sha256=sha(Path(__file__)), reused_author_sha256=sha(WORK/'data/corrective-001/author.py'),
        source_of_parameters='New synthetic dimensions; generic development-failure classes only, no final tasks or captured-answer repair.',
        final_contents_read=False, native_validation='pending; only passing cases may enter training', cases=cases)
    (ROOT / 'cases.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(dict(cases=48, train_sha256=sha(output), native_validation='pending')))


if __name__ == '__main__':
    generate()
