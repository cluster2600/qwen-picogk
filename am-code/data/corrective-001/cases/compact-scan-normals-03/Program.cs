using System;
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
        var planes=ReadPlanes(args[0]);
        using Voxels part=new(lib,new Hull(planes),new BBox3(new Vector3(-8),new Vector3(8)));
        part.CalculateProperties(out float volume, out BBox3 measured);
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
            status="geometric_candidate", qualification="geometry_only", manufacturing_authorized=false }));
    }
    static List<(Vector3 point,Vector3 normal)> ReadPlanes(string path)
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

}
public sealed class Hull(List<(Vector3 point,Vector3 normal)> planes) : IImplicit
{
    public float fSignedDistance(in Vector3 p)
    {
        float result=float.NegativeInfinity;
        foreach(var plane in planes) result=MathF.Max(result,Vector3.Dot(p-plane.point,plane.normal));
        return result; // Convex half-space reconstruction; no calibrated range-image fusion.
    }
}
