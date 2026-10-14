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
        // Refusal requires no PicoGK initialization or native geometry.
        bool valid=true;
        try { ReadXYZ(args[0]); }
        catch(FormatException) { valid=false; }
        catch(InvalidDataException) { valid=false; }
        // Valid unsigned XYZ still lacks the evidence needed for signed range fusion.
        File.WriteAllText(Path.Combine(args[1],"refused.json"),JsonSerializer.Serialize(new {
            status="needs_measurement",manufacturing_authorized=false,input_valid=valid,
            missing=new[]{"registered_range_samples","outward_normal_frame","visibility_confidence"} }));

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
