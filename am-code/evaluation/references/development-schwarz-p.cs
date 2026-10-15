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
BBox3 bounds=new(new Vector3(-7),new Vector3(7));
using Voxels phase=new(lib,new Phase(2,5.30000f),bounds);
using Mesh pm=new(phase); using Voxels distance=new(pm);
using Voxels part=new(lib);
for(int slice=0;slice<4;slice++) {
float wall=1.20000f+.05f*slice;
using Voxels outer=new(distance);using Voxels inner=new(distance);
outer.Offset(wall/2);inner.Offset(-wall/2);outer.BoolSubtract(inner);
outer.Trim(new BBox3(new Vector3(-4,-4,-4+2*slice),new Vector3(4,4,-2+2*slice)));
part.BoolAdd(outer);
}

// A sub-voxel closing removes exact Boolean contacts; re-screen wall geometry.
part.Offset(.05f);part.Offset(-.05f);
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
public sealed class Phase(int kind,float cell) : IImplicit {
public float fSignedDistance(in Vector3 p) {
Vector3 q=p+new Vector3(.111f,.071f,.123f);
float k=2*MathF.PI/cell,x=k*q.X,y=k*q.Y,z=k*q.Z;
float value=kind switch {
0=>MathF.Sin(x)*MathF.Cos(y)+MathF.Sin(y)*MathF.Cos(z)+MathF.Sin(z)*MathF.Cos(x),
1=>MathF.Cos(z)*MathF.Sin(x+y)+MathF.Sin(z)*MathF.Cos(x-y),
_=>MathF.Cos(x)+MathF.Cos(y)+MathF.Cos(z)};
return value/k;
} }
