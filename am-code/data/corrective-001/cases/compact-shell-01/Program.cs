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
        using Lattice seed=new(lib);
        seed.AddSphere(new Vector3(-1.20000f,0.80000f,0.40000f),2.62000f);
        using Voxels part=new(seed);
        using Voxels cavity=new(part);
        cavity.Offset(-1.04000f); // Coupon wall assumption, resolved with at least five voxels.
        part.BoolSubtract(cavity);
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

}
