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
        var points=ReadXYZ(args[0]);
        using Lattice balls=new(lib);
        foreach(Vector3 p in points) balls.AddSphere(p,0.72000f);
        using Voxels part=new(balls);
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
    static List<Vector3> ReadXYZ(string path)
    {
        var points=new List<Vector3>();
        foreach (string raw in File.ReadLines(path))
        {
            string row=raw.Trim(); if(row.Length==0 || row.StartsWith("#")) continue;
            string[] a=row.Split(new[]{',',';',' ','\t'},StringSplitOptions.RemoveEmptyEntries);
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

}
