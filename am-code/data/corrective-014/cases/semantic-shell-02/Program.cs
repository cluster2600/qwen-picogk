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
if (Directory.Exists(args[1]) && Directory.EnumerateFileSystemEntries(args[1]).Any())
throw new IOException("Use an empty output directory.");
Directory.CreateDirectory(args[1]);
using PicoGK.Library lib = new(0.2f);
using PicoGK.Lattice seed=new(lib);
seed.AddSphere(new Vector3(-0.90000f,0.30000f,0.50000f),3.06000f);
using PicoGK.Voxels body=new(seed);
using PicoGK.Voxels cavity=new(body);
cavity.Offset(-1.22000f); // Coupon wall assumption, resolved with at least five voxels.
body.BoolSubtract(cavity);
body.CalculateProperties(out float volume, out PicoGK.BBox3 measured);
if (!float.IsFinite(volume) || volume <= 0) throw new InvalidDataException("Empty solid.");
body.SaveToVdbFile(Path.Combine(args[1], "part.vdb"));
using PicoGK.Mesh raw = new(body);
using PicoGK.Mesh clean = new(lib);
for (int i = 0; i < raw.nTriangleCount(); i++)
{
raw.GetTriangle(i, out Vector3 a, out Vector3 b, out Vector3 c);
double ux = (double)b.X-a.X, uy = (double)b.Y-a.Y, uz = (double)b.Z-a.Z;
double vx = (double)c.X-a.X, vy = (double)c.Y-a.Y, vz = (double)c.Z-a.Z;
if (uy*vz != uz*vy || uz*vx != ux*vz || ux*vy != uy*vx) clean.nAddTriangle(a,b,c);
}
if (clean.nTriangleCount() == 0) throw new InvalidDataException("Empty surface.");
clean.SaveToStlFile(Path.Combine(args[1], "part.stl"), PicoGK.Mesh.EStlUnit.MM);
File.WriteAllText(Path.Combine(args[1], "report.json"), JsonSerializer.Serialize(new {
status="geometric_candidate", qualification="geometry_only", manufacturing_authorized=false }));
}
}
