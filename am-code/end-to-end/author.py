"""Register fresh scan development fixtures; these cases are never training rows."""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent
API = 'PicoGK 2.3: Mesh.mshFromStlFile(args[0],Mesh.EStlUnit.MM,libSet:lib); new Voxels(mesh); new Mesh(voxels); new Mesh(lib); mesh.nTriangleCount(); mesh.GetTriangle(i,out Vector3 a,out Vector3 b,out Vector3 c); mesh.nAddTriangle(a,b,c); voxels.CalculateProperties(out float volume,out BBox3 bounds); new Voxels(existing); voxels.Offset(float) (positive outward); voxels.BoolSubtract(other); new Lattice(lib); lattice.AddSphere(Vector3,float); lattice.AddBeam(Vector3,float,Vector3,float,bool); new Voxels(lattice); mesh.SaveToStlFile(path,Mesh.EStlUnit.MM); voxels.SaveToVdbFile(path). Real types are Voxels and Mesh; VoxelMatrix and PolyMesh do not exist. '
CONTRACT = ('Return an expert explanation and exactly one complete C# program in a csharp fence. '
            'Use Main(string[] args), args[0] supplied input file, args[1] empty output directory. '
            'No absolute paths, network, reflection, subprocesses, unsafe code or GUI. '
            'Allowed namespaces are System, System.IO, System.Numerics, System.Globalization, '
            'System.Collections.Generic, System.Text.Json, System.Linq and PicoGK. '
            'Geometry uses Library(0.2f), all native resources disposed before Library. '
            'Export the actual native field as part.vdb and its mesh as part.stl in millimetres. '
            'Copy mesh triangles into a new Mesh(lib), dropping exactly zero-area facets using a double-precision cross product. '
            'Export report.json with status geometric_candidate, '
            'qualification geometry_only and manufacturing_authorized false. '
            'All inputs and dimensions are synthetic. Input fixtures can vary between executions; '
            'derive geometry from their actual contents. Import the supplied file, preserve translation, '
            'and never hardcode a replacement shape. Keep the complete response below 6144 tokens. ')
START = '''using System;
using System.IO;
using System.Numerics;
using System.Globalization;
using System.Text.Json;
using System.Collections.Generic;
using PicoGK;

public static class Program
{
    public static void Main(string[] args)
    {
        if (args.Length != 2) throw new ArgumentException("input output-directory");
        Directory.CreateDirectory(args[1]);
        using Library lib = new(0.2f);
'''
END = '''        part.SaveToVdbFile(Path.Combine(args[1], "part.vdb"));
        using Mesh raw = new(part);
        using Mesh output = new(lib);
        // Boolean zero-set coincidences can create exactly zero-area facets.
        for (int i = 0; i < raw.nTriangleCount(); i++)
        {
            raw.GetTriangle(i, out Vector3 a, out Vector3 b, out Vector3 c);
            double ux = (double)b.X-a.X, uy = (double)b.Y-a.Y, uz = (double)b.Z-a.Z;
            double vx = (double)c.X-a.X, vy = (double)c.Y-a.Y, vz = (double)c.Z-a.Z;
            double x = uy*vz-uz*vy, y = uz*vx-ux*vz, z = ux*vy-uy*vx;
            if (x*x+y*y+z*z > 0) output.nAddTriangle(a,b,c);
        }
        output.SaveToStlFile(Path.Combine(args[1], "part.stl"), Mesh.EStlUnit.MM);
        File.WriteAllText(Path.Combine(args[1], "report.json"), JsonSerializer.Serialize(new {
            status = "geometric_candidate", qualification = "geometry_only",
            manufacturing_authorized = false
        }));
    }
}
'''


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def box_stl(path, centre, size):
    low = [c-s/2 for c,s in zip(centre,size)]
    high = [c+s/2 for c,s in zip(centre,size)]
    vertices = [(low[0],low[1],low[2]),(high[0],low[1],low[2]),
                (high[0],high[1],low[2]),(low[0],high[1],low[2]),
                (low[0],low[1],high[2]),(high[0],low[1],high[2]),
                (high[0],high[1],high[2]),(low[0],high[1],high[2])]
    # Outward orientation is authored independently of native voxelisation.
    faces = [(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),
             (1,2,6),(1,6,5),(2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    payload = bytearray(b'Synthetic translated box; no measured part'.ljust(80,b'\0'))
    payload.extend(struct.pack('<I',len(faces)))
    for face in faces:
        a,b,c = [vertices[i] for i in face]
        u,v = [b[i]-a[i] for i in range(3)],[c[i]-a[i] for i in range(3)]
        cross = [u[1]*v[2]-u[2]*v[1],u[2]*v[0]-u[0]*v[2],u[0]*v[1]-u[1]*v[0]]
        length = math.sqrt(sum(x*x for x in cross))
        normal = [x/length for x in cross]
        payload.extend(struct.pack('<12fH',*normal,*a,*b,*c,0))
    path.write_bytes(payload)
    return low,high


def main():
    if (ROOT/'freeze.json').exists():
        raise ValueError('Registered development cases are immutable; create a new trial to change them')
    for folder in ('inputs','references'):
        (ROOT/folder).mkdir(parents=True,exist_ok=True)
    centre,size = [1.6,-1.2,.8],[6.4,5.6,7.2]
    low,high = box_stl(ROOT/'inputs/translated-box.stl',centre,size)
    alternate_centre,alternate_size = [-1.2,2.,1.6],[5.2,6.8,7.6]
    alternate_low,alternate_high = box_stl(ROOT/'inputs/alternate-box.stl',alternate_centre,alternate_size)
    cloud = [[1.6,-2,1.2],[3.6,-2,1.2],[1.6,0,1.2],[3.6,0,1.2]]
    (ROOT/'inputs/sparse.xyz').write_text('# synthetic millimetres; no normals\nx,y,z\n\n1.6,-2.0,1.2\n3.6 -2 1.2\n1.6\t0\t1.2\n3.6,0,1.2\n')
    alternate_cloud=[[-2.8,1.2,0],[-.8,1.2,0],[-2.8,3.2,0]]
    (ROOT/'inputs/alternate-sparse.xyz').write_text('# distinct translation and point count\nx,y,z\n-2.8,1.2,0\n-0.8 1.2 0\n-2.8\t3.2\t0\n')
    malformed = '# no sensor poses or oriented observations\nx,y,z\n1.6,-2,1.2\nNaN,0,0\n3.6,0,1.2,42\n'
    (ROOT/'inputs/malformed-unoriented.xyz').write_text(malformed)
    negative_clouds = {
        'nonfinite':'x,y,z\n1,2,NaN\n',
        'column-count':'x,y,z\n1,2\n',
        'empty':'# empty point set\nx,y,z\n\n'
    }
    for name,text in negative_clouds.items():
        (ROOT/f'inputs/sparse-{name}.xyz').write_text(text)
    import_code = '''        // The fixture is an independently checked, closed outward STL in millimetres.
        using Mesh scan = Mesh.mshFromStlFile(args[0], Mesh.EStlUnit.MM, libSet: lib);
        if (scan.nTriangleCount() == 0) throw new ArgumentException("empty STL");
        using Voxels part = new(scan);
        part.CalculateProperties(out float volume, out BBox3 bounds);
        if (!float.IsFinite(volume) || volume <= 0) throw new ArgumentException("empty solid");
'''
    shell_code = '''        // Import the supplied translated envelope; do not replace it with a centred box.
        using Mesh scan = Mesh.mshFromStlFile(args[0], Mesh.EStlUnit.MM, libSet: lib);
        using Voxels part = new(scan);
        part.CalculateProperties(out float volume, out BBox3 bounds);
        if (!float.IsFinite(volume) || volume <= 0) throw new ArgumentException("empty solid");
        const float wall = 1.4f;
        using Voxels cavity = new(part);
        cavity.Offset(-wall); // Negative offset forms the inward cavity in millimetres.
        cavity.CalculateProperties(out float cavityVolume, out BBox3 cavityBounds);
        if (cavityVolume <= 0) throw new ArgumentException("skin consumes the chamber");
        part.BoolSubtract(cavity);
        float cx = (bounds.vecMin.X + bounds.vecMax.X) / 2;
        float cy = (bounds.vecMin.Y + bounds.vecMax.Y) / 2;
        using Lattice drain = new(lib);
        // Flat-ended cutter crosses the bottom skin and overlaps the computed cavity.
        drain.AddBeam(new Vector3(cx, cy, bounds.vecMin.Z - 0.8f), 1.0f,
                      new Vector3(cx, cy, bounds.vecMin.Z + wall + 0.6f), 1.0f, false);
        using Voxels vent = new(drain);
        part.BoolSubtract(vent);
'''
    cloud_code = '''        var points = new List<Vector3>();
        int lineNumber = 0;
        foreach (string line in File.ReadLines(args[0]))
        {
            lineNumber++;
            string row = line.Trim();
            if (row.Length == 0 || row.StartsWith("#") || row.Equals("x,y,z", StringComparison.OrdinalIgnoreCase)) continue;
            string[] fields = row.Split(new[] { ',', ' ', '\\t' }, StringSplitOptions.RemoveEmptyEntries);
            if (fields.Length != 3) throw new FormatException("exactly three columns at line " + lineNumber);
            float[] values = new float[3];
            for (int i = 0; i < 3; i++)
                if (!float.TryParse(fields[i], NumberStyles.Float, CultureInfo.InvariantCulture, out values[i]) ||
                    !float.IsFinite(values[i])) throw new FormatException("finite invariant coordinate required");
            points.Add(new Vector3(values[0], values[1], values[2]));
        }
        if (points.Count == 0) throw new FormatException("empty point cloud");
        using Lattice samples = new(lib);
        foreach (Vector3 point in points) samples.AddSphere(point, 0.8f);
        using Voxels part = new(samples);
        // Unsigned splats are occupancy proxies; do not invent a signed interior or bridge gaps.
'''
    refuse_code = '''using System;
using System.IO;
using System.Globalization;
using System.Text.Json;

public static class Program
{
    public static void Main(string[] args)
    {
        if (args.Length != 2) throw new ArgumentException("input output-directory");
        bool inputValid = true;
        int points = 0;
        foreach (string line in File.ReadLines(args[0]))
        {
            string row = line.Trim();
            if (row.Length == 0 || row.StartsWith("#") || row.Equals("x,y,z", StringComparison.OrdinalIgnoreCase)) continue;
            string[] fields = row.Split(new[] { ',', ' ', '\\t' }, StringSplitOptions.RemoveEmptyEntries);
            if (fields.Length != 3) { inputValid = false; continue; }
            foreach (string field in fields)
                if (!float.TryParse(field, NumberStyles.Float, CultureInfo.InvariantCulture, out float value) ||
                    !float.IsFinite(value)) inputValid = false;
            points++;
        }
        inputValid = inputValid && points > 0;
        // Even valid unsigned XYZ lacks the orientation, ranges and poses needed for a signed fusion.
        Directory.CreateDirectory(args[1]);
        File.WriteAllText(Path.Combine(args[1], "refused.json"), JsonSerializer.Serialize(new {
            status = "needs_measurement", manufacturing_authorized = false, input_valid = inputValid,
            missing = new[] { "validated_oriented_samples", "range_observations", "sensor_poses" }
        }));
    }
}
'''
    tasks=[]
    def add(name,prompt,code,fixture,oracle,kind='geometry',explanation=''):
        identifier='development-e2e-'+name
        source=ROOT/f'references/{identifier}.cs'
        source.write_text(code)
        response=ROOT/f'references/{identifier}.txt'
        response.write_text(explanation+'\n\n```csharp\n'+code+'```\n')
        tasks.append(dict(id=identifier,split='development',kind=kind,family=name,
                          prompt=API+CONTRACT+prompt,input=fixture,
                          oracle=oracle,reference=str(source.relative_to(ROOT)),
                          reference_response=str(response.relative_to(ROOT))))
    add('stl-roundtrip',
        'The supplied closed, outward binary STL is a synthetic translated box, centre (1.6,-1.2,0.8) mm and dimensions 6.4 x 5.6 x 7.2 mm. Import the actual STL, voxelize and re-export its solid envelope at 0.2 mm. Preserve translation and dimensions within voxel uncertainty. Do not smooth, hollow, recenter, reconstruct from hardcoded dimensions or claim fitment.',
        START+import_code+END,'inputs/translated-box.stl',
        dict(shape='translated-box',centre=centre,size=size,low=low,high=high,analytic_volume=math.prod(size),
             probes=[dict(point=centre,inside=True),dict(point=[-2.4,-1.2,.8],inside=False),dict(point=[4.4,-1.2,.8],inside=True)]),
        explanation='Import the supplied closed synthetic mesh in millimetres. Voxelisation and remeshing preserve its world coordinates with resolution uncertainty; they do not establish scan accuracy or manufacturing qualification.')
    tasks[-1]['oracle']['additional_inputs']=[dict(input='inputs/alternate-box.stl',oracle=dict(
        shape='translated-box',centre=alternate_centre,size=alternate_size,low=alternate_low,high=alternate_high,
        analytic_volume=math.prod(alternate_size),probes=[dict(point=alternate_centre,inside=True),
        dict(point=[-3.4,2,1.6],inside=True),dict(point=[2,2,1.6],inside=False)]))]
    inner=[s-2*1.4 for s in size]
    add('stl-skin-vent',
        'Use the supplied translated closed STL, centre (1.6,-1.2,0.8) mm and dimensions 6.4 x 5.6 x 7.2 mm. Import it, duplicate its Voxels and apply Offset(-1.4f), then BoolSubtract for a nominal inward 1.4 mm skin. Compute the outer bounds from the imported volume. Place a vertical flat-ended cylindrical drain of radius 1.0 mm at the bounds XY centre; span z=minZ-0.8 to minZ+1.4+0.6. BoolSubtract the drain. The centre must be void and the bottom opening must connect it to the exterior. Explain that this is a geometric cavity-connectivity screen only; Mercelis and Kruth 2006 does not imply that a nominal wall guarantees low residual stress or powder evacuation.',
        START+shell_code+END,'inputs/translated-box.stl',
        dict(shape='translated-skin-vent',centre=centre,size=size,low=low,high=high,wall=1.4,vent_radius=1.,
             analytic_volume=math.prod(size)-math.prod(inner)-math.pi*1.4,require_void_connectivity=True,
             probes=[dict(point=centre,inside=False),dict(point=[1.6,-1.2,-2.4],inside=False),
                     dict(point=[3.6,-1.2,-2.4],inside=True),dict(point=[4.4,-1.2,.8],inside=True),dict(point=[1.6,-1.2,2.8],inside=False)]),
        explanation='The cavity comes from an inward metric offset of the imported envelope. The drain uses imported bounds and overlaps the cavity. A nominal 1.4 mm skin and connected void are geometric candidates; Mercelis and Kruth (2006) motivates calibrated thermal and residual-stress validation, and geometric connectivity does not prove powder removal.')
    alternate_inner=[s-2*1.4 for s in alternate_size]
    tasks[-1]['oracle']['additional_inputs']=[dict(input='inputs/alternate-box.stl',oracle=dict(
        shape='translated-skin-vent',centre=alternate_centre,size=alternate_size,low=alternate_low,high=alternate_high,
        wall=1.4,vent_radius=1.,analytic_volume=math.prod(alternate_size)-math.prod(alternate_inner)-math.pi*1.4,
        require_void_connectivity=True,probes=[dict(point=alternate_centre,inside=False),
        dict(point=[-1.2,2,-1.8],inside=False),dict(point=[.8,2,-1.8],inside=True),dict(point=[-3.4,2,1.6],inside=True)]))]
    add('xyz-occupancy',
        'Read the supplied sparse translated XYZ file in invariant-culture millimetres. Accept blank lines, # comments, the exact x,y,z header and comma/space/tab-separated triples. Require exactly three finite values and a nonempty cloud before generating geometry; malformed, nonfinite or empty data must exit nonzero without an STL. Add one Lattice sphere of radius 0.8 mm per supplied sample, union through Voxels and export the disconnected occupancy proxy. No convex hull, bridge, smoothing, fitted dimensions, normals, signed range fusion or invented closed interior. The fixture has four samples at (1.6,-2,1.2), (3.6,-2,1.2), (1.6,0,1.2), (3.6,0,1.2). Explain why Curless and Levoy 1996 needs additional oriented range observations for signed fusion.',
        START+cloud_code+END,'inputs/sparse.xyz',
        dict(shape='sparse-splats',points=cloud,radius=.8,analytic_volume=4*4*math.pi*.8**3/3,
             low=[.8,-2.8,.4],high=[4.4,.8,2.],negative_inputs=[f'inputs/sparse-{n}.xyz' for n in negative_clouds],
             probes=[dict(point=p,inside=True) for p in cloud]+[dict(point=[2.4,-.8,1.2],inside=False),dict(point=[0,0,0],inside=False)]),
        explanation='These spheres are unsigned sample occupancy proxies and preserve the supplied translation. They neither infer a solid interior nor implement Curless and Levoy (1996) signed range integration; sensor poses, oriented observations and suitable coverage remain missing.')
    tasks[-1]['oracle']['additional_inputs']=[dict(input='inputs/alternate-sparse.xyz',oracle=dict(
        shape='sparse-splats',points=alternate_cloud,radius=.8,analytic_volume=3*4*math.pi*.8**3/3,
        low=[-3.6,.4,-.8],high=[0,4.,.8],probes=[dict(point=p,inside=True) for p in alternate_cloud]+
        [dict(point=[-1.6,2.4,0],inside=False),dict(point=[1.6,-2,1.2],inside=False)]))]
    add('signed-range-refusal',
        'The supplied XYZ contains malformed/nonfinite rows and no normals, range observations or sensor poses. The user asks for a waterproof dimensionally accurate signed-distance reconstruction using Curless and Levoy 1996. Validate the actual unsigned row syntax and finite values, then refuse signed fusion: write only refused.json with status needs_measurement, manufacturing_authorized false, input_valid false for malformed or empty input (true for syntactically valid nonempty unsigned XYZ), and missing exactly [validated_oriented_samples,range_observations,sensor_poses]. Produce no STL or VDB and do not initialize PicoGK or invent geometry. Explain that even syntactically valid unoriented points cannot establish the requested signed-range contract.',
        refuse_code,'inputs/malformed-unoriented.xyz',
        dict(missing=['validated_oriented_samples','range_observations','sensor_poses'],input_valid=False),'refusal',
        explanation='Malformed unsigned input cannot support an accurate signed-distance interior. Curless and Levoy (1996) range integration requires observations with orientation and sensor geometry; no surface is invented. Return a needs_measurement receipt without loading a geometry context.')
    tasks[-1]['oracle']['additional_inputs']=[dict(input='inputs/sparse.xyz',input_valid=True),
                                            dict(input='inputs/sparse-empty.xyz',input_valid=False)]
    document=dict(schema='qwen.picogk.am.scan-development@1',registered_at_utc=datetime.now(timezone.utc).isoformat(),
                  development_only=True,train_allowed=False,authored_without_training_rows=True,
                  generalisation_limit='Four handcrafted development tasks; API and task families are shared with training.',tasks=tasks)
    (ROOT/'development.json').write_text(json.dumps(document,indent=2)+'\n')
    # Public restoration paths: keep both retained adapter tensors bound to the existing release.
    retained=[ROOT.parents[1]/'infer.py',ROOT.parents[1]/'release.json',
              ROOT.parents[1]/'models/planner/adapters.safetensors',
              ROOT.parents[1]/'models/selector/adapters.safetensors']
    local=[ROOT/'development.json',ROOT/'author.py',ROOT/'evaluate.py']+list((ROOT/'inputs').glob('*'))+list((ROOT/'references').glob('*'))
    (ROOT/'freeze.json').write_text(json.dumps(dict(schema='qwen.picogk.am.scan-freeze@1',
        registered_at_utc=document['registered_at_utc'],development_only=True,
        files={str(p.relative_to(ROOT)):digest(p) for p in local},retained_profiles_launchers_adapters=bindings),indent=2)+'\n')
    print(json.dumps(dict(tasks=len(tasks),development_only=True,freeze_sha256=digest(ROOT/'freeze.json')),indent=2))


if __name__=='__main__':
    main()
