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
        // Input contract: independently surveyed, closed outward STL in mm.
        using Mesh scan=Mesh.mshFromStlFile(args[0],Mesh.EStlUnit.MM,libSet:lib);
        if(scan.nTriangleCount()==0) throw new InvalidDataException("Empty scan.");
        using Voxels part=new(scan);
        using Voxels cavity=new(part); cavity.Offset(-1.36000f);
        part.BoolSubtract(cavity);
        BBox3 bounds=part.oCalculateBoundingBox();
        Vector3 mid=(bounds.vecMin+bounds.vecMax)/2;
        using Lattice drill=new(lib);
        // Open the nominated -Z low point; connectivity alone is not physical powder removal.
        drill.AddBeam(new(mid.X,mid.Y,bounds.vecMin.Z-.6f),1.96000f,new(mid.X,mid.Y,mid.Z),1.96000f,false);
        using Voxels cutter=new(drill); part.BoolSubtract(cutter);
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
