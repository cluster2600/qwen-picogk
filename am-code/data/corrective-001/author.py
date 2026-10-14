#!/usr/bin/env python3
"""Author compact, synthetic teaching variants without using held-out task data."""
import hashlib
import json
from pathlib import Path
import struct

ROOT = Path(__file__).resolve().parent
CARD = ('PicoGK 2.3 API: new Library(0.2f); new Lattice(lib); lattice.AddSphere(Vector3,float); '
        'lattice.AddBeam(Vector3,float,Vector3,float,bool); new Voxels(lattice); new Voxels(existingVoxels); '
        'new Voxels(lib,IImplicit,BBox3); IImplicit.fSignedDistance(in Vector3); voxels.Offset(float) '
        '(positive expands); voxels.BoolSubtract(other); voxels.Trim(BBox3); new Mesh(voxels); new Mesh(lib); '
        'mesh.GetTriangle(i,out Vector3 a,out Vector3 b,out Vector3 c); mesh.nAddTriangle(a,b,c); '
        'voxels.SaveToVdbFile(path); mesh.SaveToStlFile(path,Mesh.EStlUnit.MM). '
        'AddSphere/AddBeam belong to Lattice; VDB export belongs to Voxels.\n'
        'Answer with at most two expert explanation sentences followed by exactly one complete ```csharp '
        'code fence. Write a compact standalone Main(string[] args). args[0] names the synthetic input; '
        'args[1] names an empty output directory. Use an explicit headless Library with scoped disposal. '
        'Export the SAME actual solid to part.vdb and part.stl; remove exactly zero-area STL triangles. '
        'Write report.json exactly {"status":"geometric_candidate","qualification":"geometry_only",'
        '"manufacturing_authorized":false}. Refusals instead write refused.json and no geometry. '
        'All dimensions are synthetic millimetres; geometric checks do not authorize manufacture.\n')

HEADER = '''using System;
using System.IO;
using System.Linq;
using System.Numerics;
using System.Globalization;
using System.Collections.Generic;
using System.Text.Json;
using PicoGK;

public static class Program
{
    public static void Main(string[] args)
    {
        if (args.Length != 2) throw new ArgumentException("input output-directory");
        // Preserve prior evidence instead of overwriting a populated output folder.
        if (Directory.Exists(args[1]) && Directory.EnumerateFileSystemEntries(args[1]).Any())
            throw new IOException("Use an empty output directory.");
        Directory.CreateDirectory(args[1]);
        // Native geometry is disposed before this explicitly owned context.
        using Library lib = new(0.2f);
__BODY__
__FINISH__
    }
__HELPERS__
}
__CLASSES__
'''
EXPORT = '''        part.CalculateProperties(out float volume, out BBox3 measured);
        if (!float.IsFinite(volume) || volume <= 0) throw new InvalidDataException("Empty solid.");
        // Voxels owns VDB serialization; the mesh below comes from that same object.
        part.SaveToVdbFile(Path.Combine(args[1], "part.vdb"));
        using Mesh raw = new(part);
        using Mesh clean = new(lib);
        for (int i = 0; i < raw.nTriangleCount(); i++)
        {
            raw.GetTriangle(i, out Vector3 a, out Vector3 b, out Vector3 c);
            // Compare double-precision cross products: remove zero area, not small valid facets.
            double ux = (double)b.X-a.X, uy = (double)b.Y-a.Y, uz = (double)b.Z-a.Z;
            double vx = (double)c.X-a.X, vy = (double)c.Y-a.Y, vz = (double)c.Z-a.Z;
            if (uy*vz != uz*vy || uz*vx != ux*vz || ux*vy != uy*vx) clean.nAddTriangle(a,b,c);
        }
        if (clean.nTriangleCount() == 0) throw new InvalidDataException("Empty surface.");
        clean.SaveToStlFile(Path.Combine(args[1], "part.stl"), Mesh.EStlUnit.MM);
        File.WriteAllText(Path.Combine(args[1], "report.json"), JsonSerializer.Serialize(new {
            status="geometric_candidate", qualification="geometry_only", manufacturing_authorized=false }));'''
BOX = '''public sealed class Box(Vector3 centre, Vector3 half) : IImplicit
{
    public float fSignedDistance(in Vector3 p)
    {
        Vector3 q = Vector3.Abs(p-centre)-half;
        return Vector3.Max(q,Vector3.Zero).Length()+MathF.Min(MathF.Max(q.X,MathF.Max(q.Y,q.Z)),0);
    }
}
'''
CRACK = '''public sealed class Crack(Vector3 centre, float half, float gap) : IImplicit
{
    public float fSignedDistance(in Vector3 p)
    {
        Vector3 q = Vector3.Abs(p-centre);
        return MathF.Max(MathF.Max(q.X,MathF.Max(q.Y,q.Z))-half,gap/2-q.X);
    }
}
'''
TPMS = '''public sealed class Phase(Vector3 origin, float cell, int kind) : IImplicit
{
    public float fSignedDistance(in Vector3 p)
    {
        Vector3 q = (p-origin)*(2*MathF.PI/cell);
        // von Schnering & Nesper (1991): dimensionless Fourier nodal approximations.
        float x=q.X,y=q.Y,z=q.Z;
        float value = kind switch {
            0 => MathF.Sin(x)*MathF.Cos(y)+MathF.Sin(y)*MathF.Cos(z)+MathF.Sin(z)*MathF.Cos(x),
            1 => MathF.Sin(x)*MathF.Sin(y)*MathF.Sin(z)+MathF.Sin(x)*MathF.Cos(y)*MathF.Cos(z)
                 +MathF.Cos(x)*MathF.Sin(y)*MathF.Cos(z)+MathF.Cos(x)*MathF.Cos(y)*MathF.Sin(z),
            _ => MathF.Cos(x)+MathF.Cos(y)+MathF.Cos(z) };
        return value*cell/(2*MathF.PI); // A sign carrier, not an exact distance.
    }
}
'''
CONE = '''public sealed class Roof(Vector3 origin, float radius, float floor, float shoulder, float rise) : IImplicit
{
    public float fSignedDistance(in Vector3 p)
    {
        Vector3 q=p-origin;
        float radial=MathF.Sqrt(q.X*q.X+q.Y*q.Y);
        float roofRadius=radius*MathF.Min(1,1-(q.Z-shoulder)/rise);
        return MathF.Max(radial-roofRadius,MathF.Max(floor-q.Z,q.Z-shoulder-rise));
    }
}
'''
XYZ = '''    static List<Vector3> ReadXYZ(string path)
    {
        var points=new List<Vector3>();
        foreach (string raw in File.ReadLines(path))
        {
            string row=raw.Trim(); if(row.Length==0 || row.StartsWith("#")) continue;
            string[] a=row.Split(new[]{',',';',' ','\\t'},StringSplitOptions.RemoveEmptyEntries);
            if(a.Length==3 && a[0].Equals("x",StringComparison.OrdinalIgnoreCase)
                && a[1].Equals("y",StringComparison.OrdinalIgnoreCase) && a[2].Equals("z",StringComparison.OrdinalIgnoreCase)) continue;
            if(a.Length!=3) throw new InvalidDataException("Three XYZ coordinates required.");
            float[] v=a.Select(s=>float.Parse(s,NumberStyles.Float,CultureInfo.InvariantCulture)).ToArray();
            if(v.Any(x=>!float.IsFinite(x) || MathF.Abs(x)>8)) throw new InvalidDataException("Finite bounded mm coordinates required.");
            points.Add(new(v[0],v[1],v[2]));
            if(points.Count>10000) throw new InvalidDataException("Tile larger point sets.");
        }
        if(points.Count==0) throw new InvalidDataException("Empty point set.");
        return points;
    }
'''
NORMALS = '''    static List<(Vector3 point,Vector3 normal)> ReadPlanes(string path)
    {
        string[] lines=File.ReadLines(path).Where(s=>s.Trim().Length>0 && !s.Trim().StartsWith("#")).ToArray();
        if(lines.Length!=7) throw new InvalidDataException("Header plus six registered planes required.");
        string[] header=lines[0].Split(';');
        string[] names={"x","y","z","nx","ny","nz"};
        if(header.Length!=6 || header.Distinct().Count()!=6 || names.Any(n=>!header.Contains(n)))
            throw new InvalidDataException("Six named semicolon-separated columns required.");
        var planes=new List<(Vector3 point,Vector3 normal)>();
        var directions=new HashSet<Vector3>();
        foreach(string row in lines.Skip(1))
        {
            string[] a=row.Split(';'); if(a.Length!=6) throw new InvalidDataException("Six values required.");
            float[] v=a.Select(s=>float.Parse(s,NumberStyles.Float,CultureInfo.InvariantCulture)).ToArray();
            if(v.Any(x=>!float.IsFinite(x))) throw new InvalidDataException("Finite observations required.");
            float Get(string name)=>v[Array.IndexOf(header,name)];
            Vector3 p=new(Get("x"),Get("y"),Get("z")),n=new(Get("nx"),Get("ny"),Get("nz"));
            if(n.LengthSquared()<.01f || MathF.Max(MathF.Abs(p.X),MathF.Max(MathF.Abs(p.Y),MathF.Abs(p.Z)))>8)
                throw new InvalidDataException("Bounded points and nonzero outward normals required.");
            n=Vector3.Normalize(n);
            // This teaching input is a convex axis-aligned six-face survey, not a general scanner.
            if(MathF.Abs(n.X)+MathF.Abs(n.Y)+MathF.Abs(n.Z)!=1 || !directions.Add(n))
                throw new InvalidDataException("Six distinct axis directions required.");
            planes.Add((p,n));
        }
        return planes;
    }
'''
HULL = '''public sealed class Hull(List<(Vector3 point,Vector3 normal)> planes) : IImplicit
{
    public float fSignedDistance(in Vector3 p)
    {
        float result=float.NegativeInfinity;
        foreach(var plane in planes) result=MathF.Max(result,Vector3.Dot(p-plane.point,plane.normal));
        return result; // Convex half-space reconstruction; no calibrated range-image fusion.
    }
}
'''

def f(x): return f'{x:.5f}f'
def vec(v): return 'new Vector3('+','.join(f(x) for x in v)+')'
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def stl(path,centre,half):
    lo=[a-b for a,b in zip(centre,half)];hi=[a+b for a,b in zip(centre,half)]
    vertices=[(lo[0],lo[1],lo[2]),(hi[0],lo[1],lo[2]),(hi[0],hi[1],lo[2]),(lo[0],hi[1],lo[2]),
              (lo[0],lo[1],hi[2]),(hi[0],lo[1],hi[2]),(hi[0],hi[1],hi[2]),(lo[0],hi[1],hi[2])]
    faces=[(0,2,1),(0,3,2),(4,5,6),(4,6,7),(0,1,5),(0,5,4),(1,2,6),(1,6,5),
           (2,3,7),(2,7,6),(3,0,4),(3,4,7)]
    data=bytearray(b'Synthetic independent teaching fixture'.ljust(80,b' ')+struct.pack('<I',12))
    for face in faces:data.extend(struct.pack('<12fH',0,0,0,*sum((vertices[i] for i in face),()),0))
    path.write_bytes(data)


def generate():
    (ROOT/'cases').mkdir(parents=True,exist_ok=True)
    rows=[];cases=[]
    families=['initialize','offset-sign','closing','shell','vent','cone-roof','gyroid','diamond','schwarz-p',
              'scan-normals','debug-api','missing-interfaces','stl-roundtrip','stl-skin-vent','xyz-occupancy','signed-range-refusal']
    for family in families:
        for variant in range(4):
            ident=f'compact-{family}-{variant+1:02d}';directory=ROOT/'cases'/ident;directory.mkdir(exist_ok=True)
            centre=[[-1.2,.8,.4],[-.8,-1.2,.8],[.8,.4,-.8],[1.2,-.8,.4]][variant]
            body='';classes='';helpers='';finish=EXPORT;kind='geometry';oracle={};input_name='input.dat'
            radius=[2.62,2.88,3.18,3.46][variant];wall=[1.04,1.12,1.28,1.36][variant]
            common=f' Use centre {centre}; keep all rendered geometry within [-8,8] mm.'
            explanation='The explicit Library owns native allocations; Lattice creates primitives, Voxels exports VDB and Mesh exports STL.'
            if family in ('initialize','offset-sign','shell'):
                operation={'initialize':'create the solid','offset-sign':f'erode it by {[.46,.58,.72,.84][variant]} mm','shell':f'form a hollow skin of nominal {wall} mm'}[family]
                task=f'Create a radius {radius} mm sphere and {operation}.'+common
                body=f'        using Lattice seed=new(lib);\n        seed.AddSphere({vec(centre)},{f(radius)});\n        using Voxels part=new(seed);'
                oracle={'shape':'sphere','centre':centre,'radius':radius}
                if family=='offset-sign':
                    shrink=[.46,.58,.72,.84][variant];body+=f'\n        part.Offset(-{f(shrink)}); // Negative erodes; positive expands.';oracle['radius']-=shrink
                    explanation='A negative Offset erodes an already re-distanced sphere; this is a geometric change rather than recovered scan accuracy.'
                if family=='shell':
                    body+=f'\n        using Voxels cavity=new(part);\n        cavity.Offset(-{f(wall)}); // Coupon wall assumption, resolved with at least five voxels.\n        part.BoolSubtract(cavity);'
                    oracle.update(shape='shell',wall=wall)
                    explanation='Subtract an eroded copy to leave the nominal skin; this sealed coupon still needs a vent. Wall size alone does not resolve Mercelis–Kruth (2006) residual stress.'
            elif family=='closing':
                half=[2.82,3.06,3.38,3.62][variant];gap=[.26,.34,.46,.58][variant];closing=[.62,.74,.86,.98][variant]
                task=f'Close a central X fissure of width {gap} mm in a cube of half-side {half} mm using closing radius {closing} mm.'+common
                body=f'        using Voxels part=new(lib,new Crack({vec(centre)},{f(half)},{f(gap)}),new BBox3(new Vector3(-8),new Vector3(8)));\n        // Dilation then erosion closes the crack and can round the envelope.\n        part.Offset({f(closing)}); part.Offset(-{f(closing)});'
                classes=CRACK;oracle={'shape':'closing','centre':centre,'half':half}
                explanation='Closing is dilation followed by erosion; protected datums still need metrology. These offsets do not reproduce Curless–Levoy (1996) calibrated range integration.'
            elif family in ('vent','stl-roundtrip','stl-skin-vent'):
                half=[3.24+.18*variant,3.52+.16*variant,2.68+.22*variant];vent=[1.58,1.72,1.84,1.96][variant]
                if family=='vent':
                    body=f'        using Voxels part=new(lib,new Box({vec(centre)},{vec(half)}),new BBox3(new Vector3(-8),new Vector3(8)));';classes=BOX
                    task=f'Make a hollow box with half-extents {half}, nominal skin {wall} mm and a bottom vent radius {vent} mm.'+common
                else:
                    input_name='scan.stl';stl(directory/input_name,centre,half)
                    body='        // Input contract: independently surveyed, closed outward STL in mm.\n        using Mesh scan=Mesh.mshFromStlFile(args[0],Mesh.EStlUnit.MM,libSet:lib);\n        if(scan.nTriangleCount()==0) throw new InvalidDataException("Empty scan.");\n        using Voxels part=new(scan);'
                    task=(f'Read the synthetic closed outward STL with surveyed centre {centre} and half-extents {half}, without changing its world pose.' if family=='stl-roundtrip' else
                          f'Read the synthetic closed outward STL, retain a {wall} mm shell and drill a bottom port radius {vent} mm. Derive the lowest point from its bounds.')
                oracle={'shape':'box','centre':centre,'half':half}
                if family!='stl-roundtrip':
                    body+=f'''\n        using Voxels cavity=new(part); cavity.Offset(-{f(wall)});
        part.BoolSubtract(cavity);
        BBox3 bounds=part.oCalculateBoundingBox();
        Vector3 mid=(bounds.vecMin+bounds.vecMax)/2;
        using Lattice drill=new(lib);
        // Open the nominated -Z low point; connectivity alone is not physical powder removal.
        drill.AddBeam(new(mid.X,mid.Y,bounds.vecMin.Z-.6f),{f(vent)},new(mid.X,mid.Y,mid.Z),{f(vent)},false);
        using Voxels cutter=new(drill); part.BoolSubtract(cutter);'''
                    oracle.update(shape='vent',wall=wall,vent_radius=vent)
                    explanation='BoolSubtract cuts a floor-connected port; digital access does not prove drainage, clearance or support elimination. Opening limits such as Materialise C465 guidance are service specific.'
            elif family=='cone-roof':
                cone_radius=[1.46,1.62,1.78,1.94][variant];rise=[3.94,4.18,4.46,4.74][variant];shoulder=[1.66,1.82,1.98,2.14][variant]
                origin=[centre[0],centre[1],0];half=[3.54,3.78,4.24];blockcentre=[origin[0],origin[1],half[2]];port=[1.18,1.26,1.34,1.42][variant]
                task=f'Cut a conical-roof chamber of radius {cone_radius}, floor Z=1.06, shoulder Z={shoulder}, roof rise {rise} mm inside a block from Z=0 to 8.48; drill a floor port radius {port} mm. Place the chamber at XY={origin[:2]}.'
                body=f'''        using Voxels part=new(lib,new Box({vec(blockcentre)},{vec(half)}),new BBox3(new Vector3(-8),new Vector3(8.8f)));
        using Voxels chamber=new(lib,new Roof({vec(origin)},{f(cone_radius)},1.06f,{f(shoulder)},{f(rise)}),new BBox3(new Vector3(-8),new Vector3(8.8f)));
        part.BoolSubtract(chamber);
        using Lattice drill=new(lib);
        drill.AddBeam({vec([origin[0],origin[1],-.6])},{f(port)},{vec([origin[0],origin[1],shoulder+.2])},{f(port)},false);
        using Voxels cutter=new(drill); part.BoolSubtract(cutter);'''
                classes=BOX+CONE;oracle={'shape':'cone','centre':blockcentre,'half':half,'origin':origin,'radius':cone_radius,'rise':rise,'shoulder':shoulder,'port':port,'floor':1.06}
                explanation='The analytic roof rises atan(rise/radius)>45°; Cloots et al. (2013) remains process dependent. Boolean seams and final facets require screening before any support or powder-removal claim.'
            elif family in ('gyroid','diamond','schwarz-p'):
                which=['gyroid','diamond','schwarz-p'].index(family);cell=[5.74,6.06,6.42,6.86][variant];extent=3.44+.12*variant
                # Quarter-period Schwarz phase places its nodal surface at the nominated centre.
                origin=[c-cell/4 for c in centre] if which==2 else centre
                task=f'Create a {family} Fourier sheet with cell {cell} mm and nominal physical width {wall} mm, clipped to half-side {extent} mm about {centre}. Re-distance the phase before symmetric offsets.'
                body=f'''        BBox3 padded=new(new Vector3(-8),new Vector3(8));
        using Voxels phase=new(lib,new Phase({vec(origin)},{f(cell)},{which}),padded);
        using Mesh zeroSet=new(phase); using Voxels distance=new(zeroSet);
        // The nodal carrier is not an SDF: reconstruct distances before millimetre offsets.
        using Voxels part=new(distance); using Voxels inner=new(distance);
        part.Offset({f(wall/2)}); inner.Offset(-{f(wall/2)}); part.BoolSubtract(inner);
        part.Trim(new BBox3({vec([c-extent for c in centre])},{vec([c+extent for c in centre])}));
        // Sub-voxel closing resolves exact Boolean contacts; final dimensions remain screened.
        part.Offset(.05f); part.Offset(-.05f);'''
                classes=TPMS;oracle={'shape':'tpms','kind':which,'centre':centre,'origin':origin,'cell':cell,'wall':wall,'extent':extent}
                explanation='Von Schnering–Nesper (1991) nodal functions are dimensionless; re-distance before prescribing millimetre sheet width. This is neither Sigmund FE optimization nor verified support-free LPBF geometry.'
            elif family=='scan-normals':
                half=[2.46+.18*variant,2.74+.16*variant,3.02+.14*variant];input_name='planes.csv'
                layouts=[['nx','z','x','ny','y','nz'],['z','ny','x','nz','y','nx'],['ny','x','nz','z','nx','y'],['y','nz','nx','x','z','ny']];names=layouts[variant]
                observations=[]
                for axis in range(3):
                    for sign in (-1,1):
                        p=centre.copy();p[axis]+=sign*half[axis];n=[0,0,0];n[axis]=sign
                        entry=dict(zip(['x','y','z','nx','ny','nz'],p+n));observations.append(';'.join(str(entry[name]) for name in names))
                (directory/input_name).write_text(';'.join(names)+'\n'+'\n'.join(observations)+'\n')
                body='        var planes=ReadPlanes(args[0]);\n        using Voxels part=new(lib,new Hull(planes),new BBox3(new Vector3(-8),new Vector3(8)));'
                helpers=NORMALS;classes=HULL;oracle={'shape':'box','centre':centre,'half':half,'parser':'planes','header':names}
                task=f'Reconstruct a convex axis-aligned six-face synthetic survey. The semicolon CSV header is {names}, supplying six outward unit axis directions about centre {centre}; infer geometry from the input, reject malformed/nonfinite/zero-normal rows.'
                explanation='Six registered convex tangent half-spaces infer this bounded teaching hull. Point-normal reconstruction does not reproduce complete Curless–Levoy (1996) calibrated range fusion or establish scanner accuracy.'
            elif family=='debug-api':
                beam_radius=[1.34,1.46,1.58,1.74][variant];height=[2.48,2.68,2.88,3.08][variant]
                task=f'Fix code that adds a beam to Voxels and tries Mesh.SaveToVdbFile. Create a flat-ended Z cylinder with radius {beam_radius} and half-height {height} mm.'+common
                body=f'        using Lattice beams=new(lib);\n        // AddBeam takes radii; false selects flat ends.\n        beams.AddBeam({vec([centre[0],centre[1],centre[2]-height])},{f(beam_radius)},{vec([centre[0],centre[1],centre[2]+height])},{f(beam_radius)},false);\n        using Voxels part=new(beams);'
                oracle={'shape':'cylinder','centre':centre,'radius':beam_radius,'half_height':height}
                explanation='AddBeam belongs to Lattice and its arguments are radii; convert to Voxels before VDB export. Mesh receives the same resulting solid for STL.'
            elif family=='xyz-occupancy':
                input_name='observations.xyz';points=[[centre[0]-2.1,centre[1],centre[2]],[centre[0]+2.1,centre[1],centre[2]],[centre[0],centre[1]-2.3,centre[2]+1.2],[centre[0],centre[1]+2.3,centre[2]-1.2]]
                splat=[.72,.84,.96,1.08][variant];delimiter=[';',' ', ',','\t'][variant]
                (directory/input_name).write_text('# synthetic unsigned samples\n'+delimiter.join(['X','Y','Z'])+'\n'+'\n'.join(delimiter.join(str(x) for x in p) for p in points)+'\n')
                body=f'        var points=ReadXYZ(args[0]);\n        using Lattice balls=new(lib);\n        foreach(Vector3 p in points) balls.AddSphere(p,{f(splat)});\n        using Voxels part=new(balls);'
                helpers=XYZ;oracle={'shape':'splats','points':points,'radius':splat,'parser':'xyz'}
                task=f'Load the unsigned XYZ observations with comma/semicolon/space/tab separators and optional XYZ header. Form balls radius {splat} mm at measured positions; reject malformed/nonfinite/empty input and preserve disconnected components.'
                explanation='Unoriented sphere splats are occupancy proxies, not signed Curless–Levoy (1996) reconstruction. Finite coordinates supply no interior, visibility or manufacturing evidence.'
            elif family=='missing-interfaces':
                kind='refusal';input_name='requirements.json'
                required=[['datum_height_mm','bolt_pitch_x_mm','register_radius_mm'],['pad_span_mm','axis_offset_mm','hole_clearance_mm'],['boss_height_mm','seat_span_mm','flange_thickness_mm'],['support_span_mm','bore_offset_mm','mount_depth_mm']][variant]
                measurements={required[0]:2.14+variant*.18,required[1]:None}
                (directory/input_name).write_text(json.dumps({'required_measurements':required,'measurements':measurements})+'\n')
                body='''        // Required fields come from the new input contract, never an OEM guess.
        using JsonDocument document=JsonDocument.Parse(string.Join("\\n",File.ReadLines(args[0])));
        JsonElement root=document.RootElement;
        if(!root.TryGetProperty("measurements",out JsonElement values) || values.ValueKind!=JsonValueKind.Object
            || !root.TryGetProperty("required_measurements",out JsonElement requiredArray) || requiredArray.ValueKind!=JsonValueKind.Array)
            throw new InvalidDataException("Required names and measurement object required.");
        string[] required=requiredArray.EnumerateArray().Select(x=>x.GetString()!).ToArray();
        if(required.Length==0 || required.Any(string.IsNullOrWhiteSpace) || required.Distinct().Count()!=required.Length)
            throw new InvalidDataException("Distinct required scalar measurement names required.");
        var missing=new List<string>();
        foreach(string name in required)
            if(!values.TryGetProperty(name,out JsonElement value) || value.ValueKind!=JsonValueKind.Number
                || !value.TryGetDouble(out double scalar) || !double.IsFinite(scalar)) missing.Add(name);
        File.WriteAllText(Path.Combine(args[1],"refused.json"),JsonSerializer.Serialize(new {
            status=missing.Count>0 ? "needs_measurement" : "needs_engineering_review",
            manufacturing_authorized=false, missing=missing.ToArray() }));'''
                finish='';oracle={'shape':'refusal','missing':required[1:],'required':required}
                task=f'The input JSON has required_measurements={required} and a measurements object of finite scalar values or null. Report precisely the absent/null/nonfinite required fields, no geometry; if all are present still require engineering review.'
                explanation='The required list is read from the new measurement contract; absent or null quantities remain missing. Recorded scalars alone never authorize a functional part.'
            elif family=='signed-range-refusal':
                kind='refusal';input_name='unsigned.xyz';(directory/input_name).write_text(f'X;Y;Z\n{variant+.14};.26;-.38\n-.62;.74;{variant+.46}\n')
                missing=[['oriented_surface_records','registered_camera_frame','signed_depth_frames'],['scanner_pixel_model','outward_sample_directions','camera_ray_origins'],['depth_image_calibration','surface_orientation_map','sensor_extrinsics'],['registered_range_samples','outward_normal_frame','visibility_confidence']][variant]
                body='''        bool valid=true;
        try { ReadXYZ(args[0]); }
        catch(FormatException) { valid=false; }
        catch(InvalidDataException) { valid=false; }
        // Valid unsigned XYZ still lacks the evidence needed for signed range fusion.
        File.WriteAllText(Path.Combine(args[1],"refused.json"),JsonSerializer.Serialize(new {
            status="needs_measurement",manufacturing_authorized=false,input_valid=valid,
            missing=__MISSING__ }));'''.replace('__MISSING__','new[]{'+','.join(json.dumps(x) for x in missing)+'}')
                helpers=XYZ;finish='';oracle={'shape':'unsigned-refusal','missing':missing,'input_valid':True}
                task=f'Validate unsigned XYZ syntax, but refuse to infer a signed surface. Write input_valid and exactly these missing measurement classes: {missing}; no STL or VDB even for valid coordinates.'
                explanation='Syntactic XYZ validity supplies neither normal orientation nor calibrated range visibility. Curless–Levoy (1996) signed integration therefore remains unavailable.'
            header=HEADER
            if kind=='refusal':
                header=header.replace('        // Native geometry is disposed before this explicitly owned context.\n        using Library lib = new(0.2f);',
                    '        // Refusal requires no PicoGK initialization or native geometry.')
            code=header.replace('__BODY__',body).replace('__FINISH__',finish).replace('__HELPERS__',helpers).replace('__CLASSES__',classes).rstrip()+'\n'
            (directory/'Program.cs').write_text(code)
            fixture=directory/input_name
            if not fixture.exists():fixture.write_text('synthetic unused input\n')
            card=CARD
            if kind=='refusal':
                card=card.replace('Use an explicit headless Library with scoped disposal. ',
                    'Do not initialize PicoGK for this refusal; no geometry is justified. ')
            prompt=card+task
            answer=explanation+'\n\n```csharp\n'+code+'```'
            assert answer.count('```')==2 and answer.count('```csharp')==1
            rows.append({'messages':[{'role':'user','content':prompt},{'role':'assistant','content':answer}]})
            cases.append({'id':ident,'family':family,'variant':variant+1,'kind':kind,'input':str(fixture.relative_to(ROOT)),
                          'source':str((directory/'Program.cs').relative_to(ROOT)),'source_sha256':sha(directory/'Program.cs'),
                          'input_sha256':sha(fixture),'oracle':oracle})
    assert len(rows)==len(cases)==64
    assert len({r['messages'][0]['content'] for r in rows})==64
    assert len({c['source_sha256'] for c in cases})>=55  # Input-driven readers legitimately share code.
    output=ROOT/'train.jsonl';data=''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in rows)
    if output.exists() and output.read_text()!=data:raise FileExistsError('Preserve prior corrective corpus.')
    output.write_text(data)
    (ROOT/'cases.json').write_text(json.dumps({'schema':'picogk.am.compact-teaching@1','count':64,'families':families,
        'train_sha256':sha(output),'author_sha256':sha(Path(__file__)),'cases':cases},indent=2)+'\n')
    print(json.dumps({'count':64,'train_sha256':sha(output),'native_validation':'pending'}))


if __name__=='__main__':generate()
