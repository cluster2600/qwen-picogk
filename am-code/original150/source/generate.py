#!/usr/bin/env python3
"""Build the requested ChatML JSONL from reviewed, self-contained C# lessons."""
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

HEADER = r'''using System;
using System.IO;
using System.Linq;
using System.Numerics;
using System.Collections.Generic;
using System.Globalization;
using System.Text.Json;
using PicoGK;

namespace AmDataset.Ex__ID__;

public static class Program
{
    public static void Main(string[] args)
    {
        if (args.Length != 2) throw new ArgumentException("Usage: input.xyz|csv|stl output-directory; all dimensions in mm.");
        string input = args[0], output = args[1];
        if (!File.Exists(input)) throw new FileNotFoundException("Scan input missing", input);
        if (Directory.Exists(output) && Directory.EnumerateFileSystemEntries(output).Any())
            throw new IOException("Choose an empty output directory; preserve earlier evidence.");
        Directory.CreateDirectory(output);
        // Explicit headless PicoGK 2.3 context; geometry is disposed before its library.
        using Library lib = new(0.2f);
        float h = lib.fVoxelSize;
        const float minWall = 1.0f; // Coupon assumption; calibrate for the actual alloy/machine.
        if (minWall / h < 5) throw new ArgumentException("Resolve nominal walls with at least five voxels.");
        using Voxels scan = LoadScan(lib, input, h, "__LOAD__");
        BBox3 bounds = scan.oCalculateBoundingBox();
        Vector3 lo = bounds.vecMin, hi = bounds.vecMax;
        if (!Finite(lo) || !Finite(hi) || (hi - lo).Length() < minWall)
            throw new InvalidDataException("Empty or invalid reconstruction.");
__BODY__
        Screen(part, output, h, minWall);
    }

    static bool Finite(Vector3 p) => float.IsFinite(p.X) && float.IsFinite(p.Y) && float.IsFinite(p.Z);
    static void CheckBounds(BBox3 bounds, float h)
    {
        Vector3 span=bounds.vecMax-bounds.vecMin;
        if (!Finite(bounds.vecMin) || !Finite(bounds.vecMax) || !Finite(span) || span.X<=0 || span.Y<=0 || span.Z<=0)
            throw new InvalidDataException("Invalid finite reconstruction bounds.");
        double cells=(Math.Ceiling(span.X/h)+1)*(Math.Ceiling(span.Y/h)+1)*(Math.Ceiling(span.Z/h)+1);
        if (cells>4000000) throw new InvalidDataException("Tile this scan before allocating the bounded teaching grid.");
    }
    static Voxels Render(Library lib, IImplicit field, BBox3 bounds)
    {
        CheckBounds(bounds,lib.fVoxelSize);
        return new(lib,field,bounds);
    }
__LOADER__
__HELPERS__
__SCREEN__
}
__CLASSES__
'''

POINT_READER = r'''
    readonly record struct Sample(Vector3 P, Vector3 N, float W, Vector3 Sensor);

    static List<Sample> ReadPoints(string path, bool signed, bool range)
    {
        var points = new List<Sample>();
        int line = 0;
        foreach (string raw in File.ReadLines(path))
        {
            line++;
            string s = raw.Trim();
            if (s.Length == 0 || s.StartsWith('#')) continue;
            if (line == 1 && s == "x,y,z,nx,ny,nz,w,sx,sy,sz") continue;
            string[] a = s.Contains(',') ? s.Split(',') : s.Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
            if (a.Length != 3 && a.Length != 10) throw new InvalidDataException($"Line {line}: expected 3 XYZ or 10 oriented/range columns.");
            float[] v = a.Select(x => float.Parse(x, NumberStyles.Float, CultureInfo.InvariantCulture)).ToArray();
            if (v.Any(x => !float.IsFinite(x))) throw new InvalidDataException($"Line {line}: nonfinite coordinate.");
            Vector3 p = new(v[0], v[1], v[2]);
            Vector3 n = a.Length == 10 ? new(v[3], v[4], v[5]) : Vector3.Zero;
            float w = a.Length == 10 ? v[6] : 1;
            Vector3 sensor = a.Length == 10 ? new(v[7], v[8], v[9]) : Vector3.Zero;
            if (w <= 0 || w > 1 || (signed && (a.Length != 10 || n.Length() < 0.5f || n.Length() > 1.5f)))
                throw new InvalidDataException($"Line {line}: require outward normals and confidence in (0,1].");
            if (range && (sensor - p).Length() < 0.1f) throw new InvalidDataException("Range ray origin equals measured point.");
            if (range && Vector3.Dot(p-sensor,n) >= 0) throw new InvalidDataException("Range ray contradicts the outward normal.");
            points.Add(new(p, n.Length() > 0 ? Vector3.Normalize(n) : n, w, sensor));
            if (points.Count > 100000) throw new InvalidDataException("Bounded teaching implementation: tile larger scans.");
        }
        if (points.Count < 4) throw new InvalidDataException("Insufficient observations.");
        return points;
    }
'''

def loader(mode):
    if mode == "mesh":
        return r'''
    static Voxels LoadScan(Library lib, string input, float h, string mode)
    {
        // Closed, consistently oriented STL in mm is an explicit input contract.
        // Do not assume that voxelization repairs an open scan or preserves interfaces.
        using Mesh mesh = Mesh.mshFromStlFile(input, Mesh.EStlUnit.MM, libSet: lib);
        if (mesh.nTriangleCount() == 0) throw new InvalidDataException("Empty mesh.");
        for (int i=0; i<mesh.nTriangleCount(); i++)
        {
            mesh.GetTriangle(i,out Vector3 a,out Vector3 b,out Vector3 c);
            if (!Finite(a) || !Finite(b) || !Finite(c)) throw new InvalidDataException("Nonfinite STL vertex.");
        }
        CheckBounds(mesh.oBoundingBox(),h);
        return new Voxels(mesh);
    }
''', ""
    reader = POINT_READER
    if mode == "splats":
        return reader + r'''
    static Voxels LoadScan(Library lib, string input, float h, string mode)
    {
        List<Sample> samples = ReadPoints(input, false, false);
        Vector3 low=samples.Select(s=>s.P).Aggregate(Vector3.Min)-Vector3.One*0.65f;
        Vector3 high=samples.Select(s=>s.P).Aggregate(Vector3.Max)+Vector3.One*0.65f;
        CheckBounds(new BBox3(low,high),h);
        using Lattice splats = new(lib);
        // Occupancy of sampled balls, NOT Curless-Levoy signed range integration.
        // shortcut: O(n) ball splats do not infer the interior, add oriented/range evidence for a solid.
        foreach (Sample s in samples) splats.AddSphere(s.P, 0.65f);
        return new Voxels(splats);
    }
''', ""
    if mode == "oriented":
        return reader + r'''
    static Voxels LoadScan(Library lib, string input, float h, string mode)
    {
        List<Sample> samples = ReadPoints(input, true, false);
        Vector3 lo = samples.Select(s => s.P).Aggregate(Vector3.Min) - Vector3.One;
        Vector3 hi = samples.Select(s => s.P).Aggregate(Vector3.Max) + Vector3.One;
        // Local tangent-plane sign reconstruction needs registered, outward-oriented samples.
        // This is a point-normal approximation, not a claim of full Curless-Levoy integration.
        using Voxels provisional = Render(lib, new OrientedField(samples), new BBox3(lo, hi));
        using Mesh surface = new(provisional);
        return new Voxels(surface); // Re-distance the extracted surface before mm offsets.
    }

    sealed class OrientedField(List<Sample> samples) : IImplicit
    {
        public float fSignedDistance(in Vector3 q)
        {
            float best = float.PositiveInfinity;
            // shortcut: O(n) nearest-plane lookup, replace with spatial bins for production-size scans.
            foreach (Sample s in samples)
            {
                float d = Vector3.DistanceSquared(q, s.P);
                if (d < best) best=d;
            }
            float signed=float.NegativeInfinity;
            foreach (Sample s in samples)
                if (Vector3.DistanceSquared(q,s.P)<=best+1e-5f*MathF.Max(1,best))
                    signed=MathF.Max(signed,Vector3.Dot(q-s.P,s.N));
            // Intersect tied tangent half-spaces at convex corners; concave corners need range/mesh evidence.
            // This conservative local sign approximation is not a globally exact SDF reconstruction.
            return signed;
        }
    }
''', ""
    if mode == "range":
        return reader + r'''
    static Voxels LoadScan(Library lib, string input, float h, string mode)
    {
        List<Sample> samples = ReadPoints(input, true, true);
        Vector3 lo = samples.Select(s => s.P).Aggregate(Vector3.Min) - Vector3.One;
        Vector3 hi = samples.Select(s => s.P).Aggregate(Vector3.Max) + Vector3.One;
        using Voxels observed = Render(lib, new RangeField(samples), new BBox3(lo, hi));
        using Mesh surface = new(observed);
        Console.WriteLine("TSDF unknown samples are excluded; missing visibility is not reconstructed evidence.");
        return new Voxels(surface);
    }

    sealed class RangeField(List<Sample> samples) : IImplicit
    {
        public float fSignedDistance(in Vector3 q)
        {
            const float mu = 0.8f, footprint = 1.1f;
            float distance = 0, weight = 0;
            // Curless & Levoy 1996, DOI:10.1145/237170.237269; weighted signed ray observations.
            // shortcut: ray tubes approximate finite pixel footprints, use calibrated camera projection for real range images.
            foreach (Sample s in samples)
            {
                Vector3 ray = Vector3.Normalize(s.P - s.Sensor);
                float along = Vector3.Dot(q - s.Sensor, ray);
                if (along <= 0) continue;
                Vector3 lateral = q - s.Sensor - along * ray;
                float d = (s.P - s.Sensor).Length() - along;
                if (lateral.LengthSquared() > footprint * footprint || d < -mu) continue;
                float w = s.W * MathF.Max(0, 1 - lateral.Length() / footprint);
                if (w <= 0) continue;
                distance = (weight * distance + w * Math.Clamp(d, -mu, mu)) / (weight + w);
                weight += w;
            }
            return weight > 0 ? distance : mu; // Unknown has zero weight, never invented as solid.
        }
    }
''', ""
    raise ValueError(mode)

BOX = r'''
public sealed class Box(Vector3 lo, Vector3 hi) : IImplicit
{
    public float fSignedDistance(in Vector3 p)
    {
        Vector3 q = Vector3.Abs(p - (lo + hi) / 2) - (hi - lo) / 2;
        return Vector3.Max(q, Vector3.Zero).Length() + MathF.Min(MathF.Max(q.X, MathF.Max(q.Y, q.Z)), 0);
    }
}
'''
ROOF = r'''
public sealed class RoofVoid(Vector3 lo, Vector3 hi) : IImplicit
{
    public float fSignedDistance(in Vector3 p)
    {
        float x = MathF.Abs(p.X - (lo.X + hi.X) / 2);
        float slope = MathF.Tan(55 * MathF.PI / 180);
        float roof = (p.Z - hi.Z + slope * x) / MathF.Sqrt(1 + slope * slope);
        // Vertical sides + 55-degree roof. Boolean seams still require final screening.
        return MathF.Max(MathF.Max(x - (hi.X - lo.X) / 2, MathF.Max(lo.Y - p.Y, p.Y - hi.Y)),
                         MathF.Max(lo.Z - p.Z, roof));
    }
}
'''

SCREEN = r'''
    static void Screen(Voxels part, string output, float h, float minWall)
    {
        using Mesh mesh = new(part);
        if (mesh.nTriangleCount() == 0) throw new InvalidDataException("Candidate is empty.");
        BBox3 b = mesh.oBoundingBox();
        Vector3 lo = b.vecMin - Vector3.One * h, hi = b.vecMax + Vector3.One * h;
        int unsupported = 0, degenerate = 0, thin = 0, unresolved = 0, plateContact = 0, belowPlate = 0;
        float worstWall = float.PositiveInfinity;
        var edgeCounts = new Dictionary<(Vector3, Vector3), int>();
        var edgeDirections = new Dictionary<(Vector3, Vector3), int>();
        static int Compare(Vector3 a, Vector3 c) => a.X != c.X ? a.X.CompareTo(c.X) : a.Y != c.Y ? a.Y.CompareTo(c.Y) : a.Z.CompareTo(c.Z);
        void Edge(Vector3 a, Vector3 c)
        {
            bool forward = Compare(a, c) < 0;
            var key = forward ? (a, c) : (c, a);
            edgeCounts[key] = edgeCounts.GetValueOrDefault(key) + 1;
            edgeDirections[key] = edgeDirections.GetValueOrDefault(key) + (forward ? 1 : -1);
        }
        for (int i = 0; i < mesh.nTriangleCount(); i++)
        {
            mesh.GetTriangle(i, out Vector3 a, out Vector3 c, out Vector3 d);
            Edge(a, c); Edge(c, d); Edge(d, a);
            Vector3 cross = Vector3.Cross(c - a, d - a);
            if (cross.LengthSquared() < 1e-16f) { degenerate++; continue; }
            Vector3 normal = Vector3.Normalize(cross), p = (a + c + d) / 3;
            // Cloots et al. 2013: process-dependent support limits. Here strict >45 degrees, +Z build.
            // Only a flat patch entirely on z=0 is plate contact, never an internal cavity floor.
            bool plate = MathF.Abs(a.Z) <= h*0.001f && MathF.Abs(c.Z) <= h*0.001f && MathF.Abs(d.Z) <= h*0.001f
                && MathF.Max(a.Z,MathF.Max(c.Z,d.Z))-MathF.Min(a.Z,MathF.Min(c.Z,d.Z)) < h*0.01f;
            if (plate && normal.Z < -0.99f) plateContact++;
            if (MathF.Min(a.Z,MathF.Min(c.Z,d.Z)) < -h*0.001f) belowPlate++;
            if (!plate && normal.Z <= -MathF.Cos(MathF.PI / 4)) unsupported++;
            // Ray screen on EVERY triangle centre; finite-resolution estimate, not a global thickness certificate.
            float step = h / 2, length = 0;
            bool entered = false, exited = false;
            for (float t = step; t <= 2 * minWall; t += step)
            {
                bool inside = part.bIsInside(p - normal * t);
                if (inside) { entered = true; length = t; }
                else if (entered) { exited = true; break; }
                else if (t >= h) break;
            }
            if (!entered) unresolved++;
            else if (exited) { worstWall = MathF.Min(worstWall, length); if (length < minWall) thin++; }
        }
        int nx = (int)MathF.Ceiling((hi.X - lo.X) / h) + 1;
        int ny = (int)MathF.Ceiling((hi.Y - lo.Y) / h) + 1;
        int nz = (int)MathF.Ceiling((hi.Z - lo.Z) / h) + 1;
        long count = (long)nx * ny * nz;
        if (count > 4000000) throw new InvalidDataException("Tile the dense connectivity screen for larger candidates.");
        var solid = new bool[(int)count];
        int Index(int x, int y, int z) => x + nx * (y + ny * z);
        for (int z = 0; z < nz; z++) for (int y = 0; y < ny; y++) for (int x = 0; x < nx; x++)
            solid[Index(x,y,z)] = part.bIsInside(lo + h * new Vector3(x,y,z));
        var visited = new bool[solid.Length];
        var queue = new Queue<int>();
        (int x,int y,int z) Decode(int i) => (i % nx, (i / nx) % ny, i / (nx * ny));
        IEnumerable<int> Neighbours(int i)
        {
            var (x,y,z) = Decode(i);
            if (x > 0) yield return i-1; if (x+1 < nx) yield return i+1;
            if (y > 0) yield return i-nx; if (y+1 < ny) yield return i+nx;
            if (z > 0) yield return i-nx*ny; if (z+1 < nz) yield return i+nx*ny;
        }
        int Flood(int start, bool material)
        {
            int size = 0; queue.Enqueue(start); visited[start] = true;
            while (queue.Count > 0)
            {
                int i = queue.Dequeue(); size++;
                foreach (int j in Neighbours(i)) if (!visited[j] && solid[j] == material) { visited[j] = true; queue.Enqueue(j); }
            }
            return size;
        }
        // Flood outside void from all bounding faces; trapped voids are disconnected powder pockets.
        for (int i = 0; i < solid.Length; i++)
        {
            var (x,y,z) = Decode(i);
            if (!solid[i] && !visited[i] && (x==0 || y==0 || z==0 || x==nx-1 || y==ny-1 || z==nz-1)) Flood(i, false);
        }
        int trapped = 0, pockets = 0;
        for (int i = 0; i < solid.Length; i++) if (!solid[i] && !visited[i]) { pockets++; trapped += Flood(i, false); }
        Array.Clear(visited);
        int components = 0;
        for (int i = 0; i < solid.Length; i++) if (solid[i] && !visited[i]) { components++; Flood(i, true); }
        // Previous-layer footprint test detects islands; it is separate from the angle check.
        int islands = 0;
        for (int z = 1; z < nz; z++) for (int y = 0; y < ny; y++) for (int x = 0; x < nx; x++)
        {
            int i = Index(x,y,z);
            if (!solid[i] || lo.Z + z*h <= h*0.001f) continue;
            bool below = false;
            for (int dy=-1; dy<=1; dy++) for (int dx=-1; dx<=1; dx++)
                if (x+dx>=0 && x+dx<nx && y+dy>=0 && y+dy<ny && solid[Index(x+dx,y+dy,z-1)]) below = true;
            if (!below) islands++;
        }
        bool topology = degenerate == 0 && edgeCounts.All(e => e.Value == 2 && edgeDirections[e.Key] == 0) && components == 1;
        bool geometricPass = topology && plateContact > 0 && belowPlate == 0 && unsupported == 0 && thin == 0 && unresolved == 0 && pockets == 0 && islands == 0;
        // Every candidate is preserved for review. This filename NEVER denotes a manufacturing release.
        mesh.SaveToStlFile(Path.Combine(output, "candidate.stl"), Mesh.EStlUnit.MM);
        var report = new { voxel_mm=h, nominal_min_wall_mm=minWall, triangles=mesh.nTriangleCount(),
            degenerate_triangles=degenerate, nonmanifold_edges=edgeCounts.Count(e => e.Value != 2),
            inconsistent_edges=edgeDirections.Count(e => e.Value != 0), solid_components=components,
            unsupported_triangles=unsupported, thin_ray_samples=thin, unresolved_ray_samples=unresolved,
            plate_contact_triangles=plateContact, below_plate_triangles=belowPlate,
            minimum_resolved_ray_mm=float.IsFinite(worstWall) ? (float?)worstWall : null,
            trapped_void_voxels=trapped, trapped_void_components=pockets, layer_unsupported_voxels=islands,
            geometry_screen_pass=geometricPass, manufacturing_authorized=false,
            limits="Finite-grid topology, point-ray wall samples and void connectivity; clearance, actual gravity drainage, metrology, fatigue and process calibration remain open." };
        File.WriteAllText(Path.Combine(output, "screen.json"), JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented=true }));
        // Mercelis & Kruth 2006 DOI:10.1108/13552540610707013: wall limits do not predict residual stresses.
        Console.WriteLine(geometricPass ? "Geometry screens pass; physical LPBF validation remains required." : "Geometry screen rejects candidate; inspect screen.json before any build planning.");
    }
'''

TPMS = r'''
public sealed class Tpms(int kind, float cell, int warp, Vector3 centre) : IImplicit
{
    public float fSignedDistance(in Vector3 p)
    {
        Vector3 q = p - centre;
        float k = 2 * MathF.PI / cell, x = k*q.X, y = k*q.Y, z = k*q.Z;
        if (warp == 1)
        {
            // Integrated phase: local axial period a(z)=cell*(1+0.03*z), not k(z)*z.
            float u = 1 + 0.03f*q.Z;
            // The render domain is validated before entering the native callback.
            z = k * MathF.Log(u) / 0.03f;
        }
        if (warp == 2) { x = k*(0.8660254f*q.X + 0.5f*q.Y); y = k*(-0.5f*q.X + 0.8660254f*q.Y); }
        if (warp == 3) z *= 0.65f; // Characterized anisotropic phase; screen the final slopes.
        // von Schnering & Nesper 1991 DOI:10.1007/BF01313411: dimensionless Fourier nodal approximations.
        float f = kind switch {
            0 => MathF.Sin(x)*MathF.Cos(y) + MathF.Sin(y)*MathF.Cos(z) + MathF.Sin(z)*MathF.Cos(x),
            1 => MathF.Cos(z)*MathF.Sin(x+y) + MathF.Sin(z)*MathF.Cos(x-y),
            _ => MathF.Cos(x) + MathF.Cos(y) + MathF.Cos(z) };
        // shortcut: f/k is a zero-set carrier rather than exact SDF, re-distance its mesh before offsets.
        return f / k;
    }
}
'''
SHEET_HELPER = r'''
    static Voxels Sheet(Library lib, BBox3 bounds, int kind, float cell, int warp, float wall)
    {
        Vector3 pad = Vector3.One * (wall + 2 * lib.fVoxelSize);
        float bottom = bounds.vecMin.Z-pad.Z-(bounds.vecMin.Z+bounds.vecMax.Z)/2;
        if (warp==1 && 1+0.03f*bottom <= 0) throw new ArgumentException("Graded period becomes nonpositive in render bounds.");
        using Voxels phase = Render(lib, new Tpms(kind, cell, warp, (bounds.vecMin+bounds.vecMax)/2),
            new BBox3(bounds.vecMin-pad, bounds.vecMax+pad));
        using Mesh phaseMesh = new(phase);
        using Voxels distance = new(phaseMesh);
        using Voxels inner = new(distance);
        using Voxels outer = new(distance);
        inner.Offset(-wall/2); outer.Offset(wall/2);
        outer.BoolSubtract(inner); // Symmetric sheet of nominal wall mm, independent of |F| threshold.
        return new Voxels(outer);
    }

    static Voxels ShellAndCore(Library lib, Voxels scan, Voxels infill, float skin)
    {
        using Voxels core = new(scan); core.Offset(-skin);
        if (core.bIsEmpty()) throw new InvalidDataException("No resolved core remains for this infill.");
        using Voxels clipped = new(infill); clipped.BoolIntersect(core);
        using Voxels shell = new(scan); shell.BoolSubtract(core); shell.BoolAdd(clipped);
        return new Voxels(shell);
    }

    static void FloorPort(Library lib, Voxels part, Vector3 lo, Vector3 hi, float x, float y, float radius)
    {
        if (!float.IsFinite(radius) || radius<=0) throw new ArgumentOutOfRangeException(nameof(radius));
        using Lattice drill = new(lib);
        // Materialise C465 design guide: service-specific powder access, here a nominal 3 mm orifice.
        // Open through the floor and all internal layers at the nominated low point, +Z build/-Z gravity.
        drill.AddBeam(new(x,y,lo.Z-1), radius, new(x,y,hi.Z+1), radius, false);
        using Voxels cutter = new(drill);
        part.BoolSubtract(cutter); // PicoGK 2.3 equivalent of the requested voxels.Sub.
    }
'''

def infills():
    out=[]
    def add(title,task,body,extra="",explanation="",classes=TPMS,helpers=SHEET_HELPER):
        i=46+len(out)
        out.append(dict(id=i,category="infill",title=title,task=task,load_mode="mesh",body=body,
          helpers=helpers,classes=classes,explanation=explanation or extra))
    names=["Gyroid","Diamond","Schwarz P"]
    # 24 TPMS tasks: each change teaches a different geometry or optimization decision.
    for kind,name in enumerate(names):
        for v in range(8):
            cell=[4.5,5.0,4.5,4.5,5.0,4.5,5.0,4.5][v]
            warp={2:1,3:2,4:3}.get(v,0)
            base=f'''        using Voxels infill = Sheet(lib, bounds, {kind}, {cell}f, {warp}, minWall);
        using Voxels part = ShellAndCore(lib, scan, infill, minWall);
'''
            details=[
              ("constant-wall baseline","Replace a dimensionless TPMS band threshold with symmetric millimetre offsets of its re-distanced phase boundary.",""),
              ("two-zone porosity","Increase the lower attachment region wall to 1.2 mm without changing upper-cell pitch.",f'''        using Voxels dense = Sheet(lib, bounds, {kind}, {cell}f, 0, 1.2f);
        using Voxels lower = Render(lib, new Box(lo, new(hi.X,hi.Y,(lo.Z+hi.Z)/2)), bounds);
        dense.BoolIntersect(lower); dense.BoolIntersect(scan); part.BoolAdd(dense);
'''),
              ("integrated axial period","Grade the Z period by integrating 2*pi/a(z); keep phase continuous and reject nonpositive local periods.",""),
              ("rotated phase","Rotate the XY phase by 30 degrees while preserving orthonormal axes; compare final downward facets.",""),
              ("elongated cells","Elongate Z cells through a documented anisotropic phase and retain the strict overhang rejection.",""),
              ("opposed labyrinth access","Provide two independent full-depth powder-access cuts; flood all voids because a sheet separates two labyrinths.",'''        FloorPort(lib, part, lo, hi, lo.X+2, lo.Y+2, 1.5f);
        FloorPort(lib, part, lo, hi, hi.X-2, hi.Y-2, 1.5f);
'''),
              ("solid attachment band","Union an input-derived lower 1.2 mm solid attachment band before drilling; do not invent bolt geometry.",'''        using Voxels land = Render(lib, new Box(lo, new(hi.X,hi.Y,lo.Z+1.2f)), bounds);
        land.BoolIntersect(scan); part.BoolAdd(land);
'''),
              ("central flow keepout","Remove a 3 by 3 mm vertical square keepout from the shell and infill together, after union, so no lattice refills the channel.",'''        Vector3 centre=(lo+hi)/2;
        BBox3 cutBounds=new(new(centre.X-1.5f,centre.Y-1.5f,lo.Z-1),new(centre.X+1.5f,centre.Y+1.5f,hi.Z+1));
        using Voxels channel=Render(lib,new Box(cutBounds.vecMin,cutBounds.vecMax),cutBounds);
        part.BoolSubtract(channel);
''')]
            title,task,tail=details[v]
            if v!=5 and v!=7: tail+='''        FloorPort(lib, part, lo, hi, (lo.X+hi.X)/2, (lo.Y+hi.Y)/2, 1.5f);
'''
            add(f"{name}: {title}",task,base+tail,explanation=f"{name} uses the von Schnering–Nesper Fourier nodal approximation, DOI:10.1007/BF01313411. The raw function is dimensionless; Sheet reconstructs distances and uses offsets in mm. {task} These geometry changes do not implement Sigmund's FE homogenization optimizer (DOI:10.1016/0020-7683(94)90154-6). A standard sheet can fail the >45-degree rule; preserve and reject those cases instead of claiming universal self-support.")
    # 12 load-path and conformal lattice tasks, with geometry genuinely changed.
    for family in range(4):
        for v in range(3):
            titles=["steep cross-braced cells","load-axis trunks","conformal column rings","seeded stochastic foam struts"]
            init='''        using Lattice beams = new(lib);
        Vector3 centre = (lo+hi)/2;
'''
            if family==0:
                geom=f'''        for (float z=lo.Z+minWall; z<hi.Z-minWall-2.5f; z+=2.5f)
        for (float y=lo.Y+1.5f; y<hi.Y-1.5f; y+=2)
        for (float x=lo.X+1.5f; x<hi.X-1.5f; x+=2)
        {{
            Vector3 bottom = new(x,y,z), top = new(x+{0.8+v*.2:.1f}f,y+0.5f,z+2.5f);
            float angle = MathF.Atan2(top.Z-bottom.Z, new Vector2(top.X-bottom.X,top.Y-bottom.Y).Length())*180/MathF.PI;
            if (angle <= 45) throw new InvalidDataException("Strut centreline is too shallow.");
            beams.AddBeam(bottom, 0.6f, top, {0.6+v*.1:.1f}f, false);
            beams.AddBeam(new(top.X,top.Y,z), 0.6f, new(x,y,top.Z), 0.6f, false);
        }}
'''
            elif family==1:
                geom=f'''        for (float y=lo.Y+1.7f; y<hi.Y-1.2f; y+=2.2f)
        for (float x=lo.X+1.7f; x<hi.X-1.2f; x+=2.2f)
        {{
            // Load-direction assumption: +Z compression; this is not a measured stress solution.
            float r = 0.55f + {0.05+v*.05:.2f}f*MathF.Abs(x-centre.X)/MathF.Max(1,hi.X-lo.X);
            beams.AddBeam(new(x,y,lo.Z), r, new(x,y,hi.Z), {0.55+v*.05:.2f}f, false);
        }}
'''
            elif family==2:
                geom=f'''        for (int n=0; n<{6+v*2}; n++)
        {{
            float theta = 2*MathF.PI*n/{6+v*2};
            float radius = MathF.Max(0.5f,MathF.Min(hi.X-lo.X,hi.Y-lo.Y)/2-1.6f);
            Vector3 a = new(centre.X+radius*MathF.Cos(theta),centre.Y+radius*MathF.Sin(theta),lo.Z);
            Vector3 b = new(a.X,a.Y,hi.Z);
            beams.AddBeam(a, 0.6f, b, {0.6+v*.1:.1f}f, false);
        }}
'''
            else:
                geom=f'''        Random random = new({710+v});
        for (int n=0; n<{12+v*4}; n++)
        {{
            float x=lo.X+1.5f+(hi.X-lo.X-3)*(float)random.NextDouble();
            float y=lo.Y+1.5f+(hi.Y-lo.Y-3)*(float)random.NextDouble();
            float dx=0.6f*((float)random.NextDouble()-0.5f);
            float dy=0.6f*((float)random.NextDouble()-0.5f);
            Vector3 a=new(x,y,lo.Z), b=new(x+dx,y+dy,hi.Z);
            beams.AddBeam(a, 0.55f, b, {0.55+v*.05:.2f}f, false);
        }}
'''
            tail='''        using Voxels infill = new(beams);
        using Voxels part = ShellAndCore(lib, scan, infill, minWall);
        FloorPort(lib, part, lo, hi, (lo.X+hi.X)/2, (lo.Y+hi.Y)/2, 1.5f);
'''
            add(f"{titles[family]}: design {v+1}",f"Create {titles[family]} inside a closed scan, using a {['symmetric','graded-radius','denser'][v]} design variant. Keep a 1 mm exterior skin and inspect both beam surface angles and attachment continuity.",init+geom+tail,explanation="Lattice.AddBeam uses physical radii in mm. Steep centrelines alone do not certify the entire curved beam surface or its Boolean junctions. Clip to the eroded scan core, union the intact attachment skin, then cut the powder-access route. This is a load-path hypothesis inspired by Sigmund (1994), DOI:10.1016/0020-7683(94)90154-6, and support minimization by Cloots et al. (2013), not validated stiffness or fatigue optimization.",classes="",helpers=SHEET_HELPER[SHEET_HELPER.index('    static Voxels ShellAndCore'):])
    # 9 open conical/teardrop foam designs, explicitly through-drained.
    for family in range(3):
        for v in range(3):
            if family==0:
                geom=f'''        for (int n=0;n<{3+v};n++)
        {{
            float theta=2*MathF.PI*n/{3+v};
            Vector3 a=new(centre.X+1.7f*MathF.Cos(theta),centre.Y+1.7f*MathF.Sin(theta),lo.Z-1);
            // Radius decreases upwards: conical void roof slope is steeper than 55 degrees.
            beams.AddBeam(a, 0.75f, new(a.X,a.Y,hi.Z-1.2f), 0.0f, false);
        }}
'''
                classes=""
            elif family==1:
                geom=f'''        float shift={-0.4+v*.4:.1f}f;
        using Voxels roof = Render(lib, new RoofVoid(new(centre.X-1.5f+shift,centre.Y-2,lo.Z-1),new(centre.X+1.5f+shift,centre.Y+2,hi.Z-1.2f)), bounds);
        part.BoolSubtract(roof);
'''
                classes=ROOF
            else:
                geom=f'''        Random random=new({821+v});
        for(int n=0;n<{3+v};n++)
        {{
            float x=lo.X+1.6f+(hi.X-lo.X-3.2f)*(float)random.NextDouble();
            float y=lo.Y+1.6f+(hi.Y-lo.Y-3.2f)*(float)random.NextDouble();
            beams.AddBeam(new(x,y,lo.Z-1),0.65f,new(x,y,hi.Z-1.2f),0.0f,false);
        }}
'''
                classes=""
            body='''        using Voxels part = new(scan);
        using Lattice beams = new(lib);
        Vector3 centre=(lo+hi)/2;
'''+geom
            if family!=1: body+='''        using Voxels voids = new(beams); part.BoolSubtract(voids);
'''
            add(f"Open foam: {['conical pores','roofed slot pores','seeded conical pores'][family]} {v+1}","Replace spherical pore roofs with upward-tapering, floor-connected voids. Bound the voids inside the measured envelope and retain the full post-Boolean angle, wall and trapped-powder screen.",body,explanation="Conical pores taper towards the build direction, so the internal roof rises steeply rather than forming a spherical ceiling. Every cut reaches the nominated lower face for -Z evacuation. The number and placement of pores change this finite coupon. Cloots et al. (2013) motivates process-specific support minimization; Materialise guidance motivates accessible openings. A finite-grid connectivity pass is not verified powder removal.",classes=classes,helpers="")
    # 9 finite searches: objective-driven selection without pretending this is FE topology optimization.
    for kind,name in enumerate(names):
        for v in range(3):
            body=f'''        float[] walls = {{1.0f,1.1f,1.2f}};
        float targetDensity = {0.50+v*.10:.2f}f;
        float bestScore = float.PositiveInfinity;
        using Voxels part = new(scan);
        scan.CalculateProperties(out float fullVolume, out _);
        foreach (float wall in walls)
        {{
            using Voxels infill = Sheet(lib,bounds,{kind},5.0f,0,wall);
            using Voxels trial = ShellAndCore(lib,scan,infill,minWall);
            trial.CalculateProperties(out float volume,out _);
            float rho = volume/fullVolume;
            // Sigmund 1994 DOI:10.1016/0020-7683(94)90154-6 motivates constitutive objectives.
            // Toy homogenization surrogate E/Esolid=rho^2, not a calibrated constitutive law.
            float complianceProxy = 1/MathF.Max(rho*rho,1e-6f);
            float score = MathF.Abs(rho-targetDensity)+0.01f*complianceProxy;
            Console.WriteLine($"wall={{wall:F2}} mm density={{rho:F4}} proxy={{complianceProxy:F4}}");
            if (score < bestScore) {{ part.BoolSubtract(part.voxDuplicate()); part.BoolAdd(trial); bestScore=score; }}
        }}
        FloorPort(lib,part,lo,hi,(lo.X+hi.X)/2,(lo.Y+hi.Y)/2,1.5f);
'''
            # Avoid a transient undisposed duplicate in the selection update.
            body=body.replace('part.BoolSubtract(part.voxDuplicate());','using Voxels previous = new(part); part.BoolSubtract(previous);')
            add(f"{name}: finite density objective {v+1}",f"Compare three nominal wall settings against relative-density target {0.50+v*.10:.2f}. Use a stated toy compliance proxy, report every candidate score, and separate surrogate ranking from actual homogenization and printability.",body,explanation="Sigmund (1994), DOI:10.1016/0020-7683(94)90154-6, optimizes microstructures using constitutive targets and FE homogenization. This small example only ranks voxel-measured density with a deliberately labelled rho-squared toy modulus. It does not reproduce Sigmund's optimizer or prove improved stiffness. The selected morphology still must pass the independent final geometric screens.")
    for kind,name in enumerate(names):
        for radial in (False,True):
            body=f'''        Vector3 pad=Vector3.One*1.6f;
        using Voxels phase=Render(lib,new Tpms({kind},4.5f,0,(lo+hi)/2),new BBox3(lo-pad,hi+pad));
        using Mesh surface=new(phase);
        using Voxels redistanced=new(surface);
        using ScalarField distance=new(redistanced);
        using Voxels infill=Render(lib,new GradedSheet(distance,h,lo,hi),bounds);
        using Voxels part=ShellAndCore(lib,scan,infill,minWall);
        FloorPort(lib,part,lo,hi,(lo.X+hi.X)/2,(lo.Y+hi.Y)/2,1.5f);
'''
            grade=('Math.Clamp(new Vector2(p.X-(lo.X+hi.X)/2,p.Y-(lo.Y+hi.Y)/2).Length()/MathF.Max(1,(hi-lo).Length()/2),0,1)'
                if radial else 'Math.Clamp((p.Z-lo.Z)/MathF.Max(1,hi.Z-lo.Z),0,1)')
            classes=TPMS+f'''
public sealed class GradedSheet(ScalarField distance,float h,Vector3 lo,Vector3 hi) : IImplicit
{{
    public float fSignedDistance(in Vector3 p)
    {{
        // ScalarField raw SDF values are in voxel units, not mm.
        // Query only its observed narrow band; missing values are not zero-distance samples.
        if (!distance.bGetValue(p,out float raw)) return 1;
        float grade={grade};
        float wall=1.0f+0.15f*grade; // Missing band samples are excluded; final wall screening is still required.
        return MathF.Abs(raw*h)-wall/2;
    }}
}}
'''
            add(f"{name}: smooth {'radial' if radial else 'axial'} wall grading",
                "Construct a continuously graded 1.00–1.15 mm TPMS sheet from a re-distanced phase. Convert raw ScalarField values from voxel units to mm, handle inactive values explicitly, and measure the final graded wall.",
                body,classes=classes,helpers=SHEET_HELPER[SHEET_HELPER.index('    static Voxels ShellAndCore'):],
                explanation="The periodic nodal surface follows von Schnering & Nesper (1991), DOI:10.1007/BF01313411. A true voxel-distance field supplies the physical sheet width; an axial or radial scalar controls the local nominal wall and hence porosity. Missing narrow-band values are explicitly excluded instead of treated as zero. This is a smooth density prescription, not a solved Sigmund FE optimization. Strong gradients and voxel sampling still require independent final thickness and underside checks.")
    assert len(out)==60
    return out

def load_module(name):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).with_name(name+".py"))
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def generate():
    specs=load_module("scan_curriculum").examples()+infills()+load_module("dfam_curriculum").examples()
    specs.sort(key=lambda x:x["id"])
    assert [s["id"] for s in specs]==list(range(1,151))
    (ROOT/"data").mkdir(exist_ok=True)
    rows=[]; meta=[]
    for s in specs:
        body=s["body"]
        ld,cl=loader(s["load_mode"])
        helpers=s.get("helpers","")
        classes=cl+s.get("classes","")
        if "new Box(" in body or "new Box(" in helpers: classes+=BOX
        if "new RoofVoid(" in body and "class RoofVoid" not in classes: classes+=ROOF
        code=HEADER.replace("__ID__",f'{s["id"]:03d}').replace("__LOAD__",s["load_mode"]).replace("__BODY__",body.rstrip()).replace("__LOADER__",ld).replace("__HELPERS__",helpers).replace("__SCREEN__",SCREEN).replace("__CLASSES__",classes)
        prompt=(f'Engineering exercise {s["id"]:03d}: {s["title"]}.\n{s["task"]}\n'
          f'Use PicoGK 2.3.0, .NET 9, and an explicit headless 0.2 mm Library. Input contract: '
          +{"mesh":"closed outward-oriented STL in mm", "splats":"unoriented XYZ in mm; do not invent an inside/outside sign", "oriented":"registered CSV x,y,z,nx,ny,nz,w,sx,sy,sz; outward normals; confidence (0,1]", "range":"registered range CSV x,y,z,nx,ny,nz,w,sx,sy,sz; sensor origins in mm; confidence (0,1]"}[s["load_mode"]]
          +'. Build direction is +Z; plate is z=0; default evacuation gravity is -Z unless the exercise specifies another removal pose. Nominal minimum wall is 1.0 mm, a coupon design assumption awaiting process calibration.\nProvide a complete commented C# program with input and output arguments. Preserve review-only candidate.stl, report strict >45-degree underside failures, wall-ray samples, mesh edge incidence, material components, layer islands and powder-void connectivity. Do not label geometric screens as physical, leak-tight, fatigue or manufacturing qualification.')
        explanation=s["explanation"]+'\n\nThe program preserves screened nonempty candidates with a pass or rejection report; invalid input and impossible construction assumptions fail before export. Topology and wall screens are finite-resolution evidence; a watertight mesh does not establish metrological accuracy. Minimum wall thickness does not resolve residual stress (Mercelis & Kruth 2006, DOI:10.1108/13552540610707013). Materialise powder-removal dimensions are service-specific; check clearance and actual extraction on the chosen process.\n\nRun in a new empty output directory. The program requires a project targeting net9.0 with PicoGK 2.3.0 and the matching native runtime. Core types are Mesh and IImplicit; this version has no PolyMesh/VoxelMatrix or Voxels.Sub API.'
        text='<|im_start|>user\n'+prompt+'\n<|im_end|>\n<|im_start|>assistant\n'+explanation+'\n\n```csharp\n'+code.rstrip()+'\n```\n<|im_end|>'
        rows.append({"text":text})
        meta.append({k:s[k] for k in ("id","category","title","load_mode")}|{"code_sha256":hashlib.sha256(code.rstrip().encode()).hexdigest()})
    path=ROOT/"data/picogk-am-150.jsonl"
    path.write_text(''.join(json.dumps(r,ensure_ascii=False,separators=(',',':'))+'\n' for r in rows))
    train=path.with_name("train.jsonl")
    if not train.exists(): train.symlink_to(path.name)
    elif train.resolve()!=path.resolve() and train.read_bytes()!=path.read_bytes():
        raise FileExistsError("Preserve the existing MLX train file.")
    (ROOT/"metadata.json").write_text(json.dumps({"format":"ChatML single text field", "language":"en", "examples":meta},indent=2)+'\n')
    print(json.dumps({"examples":len(rows),"bytes":path.stat().st_size,"path":str(path)}))

if __name__=="__main__": generate()
