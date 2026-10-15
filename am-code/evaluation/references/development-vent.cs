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
using Voxels part=new(lib,new SolidBox(4.20000f),new BBox3(new Vector3(-5.20000f),new Vector3(5.20000f)));
using Voxels cavity=new(part); cavity.Offset(-1.20000f); part.BoolSubtract(cavity);
using Lattice drill=new(lib); drill.AddBeam(new Vector3(0,0,-5.20000f),1.6f,Vector3.Zero,1.6f,false);
using Voxels vent=new(drill); part.BoolSubtract(vent);

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
public sealed class SolidBox(float half) : IImplicit {
public float fSignedDistance(in Vector3 p) => MathF.Max(MathF.Max(MathF.Abs(p.X),MathF.Abs(p.Y)),MathF.Abs(p.Z))-half;
}
