using System;
using System.IO;
using System.Numerics;
using System.Globalization;
using System.Text.Json;
using System.Collections.Generic;
using PicoGK;
public static class Program {
public static void Main(string[] args) {
if (args.Length != 2) throw new ArgumentException("input output-directory");
Directory.CreateDirectory(args[1]);
using Library lib = new(0.2f);
var samples=new List<(Vector3 p,Vector3 n)>();
foreach(string raw in File.ReadLines(args[0])) {
string s=raw.Trim();if(s.Length==0||s.StartsWith("#")||s=="x,y,z,nx,ny,nz")continue;
string[] a=s.Split(',');if(a.Length!=6)throw new InvalidDataException("six columns required");
float[] v=new float[6];for(int i=0;i<6;i++) {v[i]=float.Parse(a[i],CultureInfo.InvariantCulture);if(!float.IsFinite(v[i]))throw new InvalidDataException("finite values required");}
Vector3 p=new(v[0],v[1],v[2]),n=new(v[3],v[4],v[5]);
if(n.LengthSquared()<.01f)throw new InvalidDataException("nonzero outward normals required");
samples.Add((p,Vector3.Normalize(n)));
}
if(samples.Count!=6)throw new InvalidDataException("six registered tangent plane observations required");
using Voxels part=new(lib,new OrientedHull(samples),new BBox3(new Vector3(-6),new Vector3(6)));

part.SaveToVdbFile(Path.Combine(args[1], "part.vdb"));
using Mesh rawMesh = new(part);
using Mesh mesh = new(lib);
// Exact zero-area facets can occur at Boolean zero-set coincidences.
for(int i=0;i<rawMesh.nTriangleCount();i++) {
rawMesh.GetTriangle(i,out Vector3 a,out Vector3 b,out Vector3 c);
double ux=(double)b.X-a.X,uy=(double)b.Y-a.Y,uz=(double)b.Z-a.Z;
double vx=(double)c.X-a.X,vy=(double)c.Y-a.Y,vz=(double)c.Z-a.Z;
double nx=uy*vz-uz*vy,ny=uz*vx-ux*vz,nz=ux*vy-uy*vx;
if(nx*nx+ny*ny+nz*nz>0)mesh.nAddTriangle(a,b,c);
}
mesh.SaveToStlFile(Path.Combine(args[1], "part.stl"), Mesh.EStlUnit.MM);
} }
public sealed class OrientedHull(List<(Vector3 p,Vector3 n)> samples) : IImplicit {
public float fSignedDistance(in Vector3 p) {float d=float.NegativeInfinity;foreach(var s in samples)d=MathF.Max(d,Vector3.Dot(p-s.p,s.n));return d;}
}
