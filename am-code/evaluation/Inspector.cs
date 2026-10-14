using System;
using System.IO;
using System.Numerics;
using System.Globalization;
using System.Text.Json;
using System.Collections.Generic;
using PicoGK;

// Trusted inspector re-loads exported geometry; it does not trust candidate reports.
public static class Inspector {
public static void Main(string[] args) {
CultureInfo.CurrentCulture=CultureInfo.InvariantCulture;
using Library lib=new(.2f);
using Mesh mesh=Mesh.mshFromStlFile(args[0],Mesh.EStlUnit.MM,libSet:lib);
using Voxels part=Voxels.voxFromVdbFile(lib,Path.ChangeExtension(args[0],".vdb"));
part.CalculateProperties(out float libraryVolume,out BBox3 bounds);
const float step=.4f; const int n=51; const float low=-10;
byte[] occupied=new byte[n*n*n];
for(int z=0;z<n;z++)for(int y=0;y<n;y++)for(int x=0;x<n;x++)
occupied[x+n*(y+n*z)]=part.bIsInside(new Vector3(low+x*step,low+y*step,low+z*step))?(byte)1:(byte)0;
File.WriteAllBytes(Path.Combine(args[1],"occupancy.bin"),occupied);
int filled=0;
for(int z=(int)MathF.Floor(bounds.vecMin.Z/.2f)-1;z<=(int)MathF.Ceiling(bounds.vecMax.Z/.2f)+1;z++)
for(int y=(int)MathF.Floor(bounds.vecMin.Y/.2f)-1;y<=(int)MathF.Ceiling(bounds.vecMax.Y/.2f)+1;y++)
for(int x=(int)MathF.Floor(bounds.vecMin.X/.2f)-1;x<=(int)MathF.Ceiling(bounds.vecMax.X/.2f)+1;x++)
if(part.bIsInside(new Vector3((x+.5f)*.2f,(y+.5f)*.2f,(z+.5f)*.2f)))filled++;
double volume=filled*.008;
int definitelyFilled=0,possiblyFilled=0;
for(int z=1;z<n-1;z++)for(int y=1;y<n-1;y++)for(int x=1;x<n-1;x++) {
bool all=true,any=false;
for(int dz=-1;dz<=1;dz++)for(int dy=-1;dy<=1;dy++)for(int dx=-1;dx<=1;dx++) {
bool inside=occupied[(x+dx)+n*((y+dy)+n*(z+dz))]!=0;all&=inside;any|=inside;
}
if(all)definitelyFilled++;if(any)possiblyFilled++;
}
double[] interval=new[]{definitelyFilled*.064,possiblyFilled*.064};
var thickness=new List<float>(); int unsupported=0,inspected=0;
for(int i=0;i<mesh.nTriangleCount();i++) {
mesh.GetTriangle(i,out Vector3 a,out Vector3 b,out Vector3 c);
Vector3 cross=Vector3.Cross(b-a,c-a);if(cross.LengthSquared()<1e-12f)continue;
Vector3 normal=Vector3.Normalize(cross),p=(a+b+c)/3;
bool baseContact=MathF.Abs(a.Z)<.001f&&MathF.Abs(b.Z)<.001f&&MathF.Abs(c.Z)<.001f;
if(!baseContact&&normal.Z < -MathF.Sqrt(.5f)-.005f)unsupported++;
if(i%7!=0||MathF.Max(MathF.Abs(p.X),MathF.Max(MathF.Abs(p.Y),MathF.Abs(p.Z)))>2.3f)continue;
if(MathF.Min(MathF.Abs(p.Z),MathF.Min(MathF.Abs(p.Z-2),MathF.Abs(p.Z+2)))<.3f)continue;
bool entered=false;float length=0;
for(float t=.05f;t<=3;t+=.05f) {
bool inside=part.bIsInside(p-normal*t);
if(inside){entered=true;length=t;}
else if(entered){thickness.Add(length);break;}
else if(t>.25f)break;
}
inspected++;
}
File.WriteAllText(Path.Combine(args[1],"native.json"),JsonSerializer.Serialize(new {
volume_mm3=volume,library_volume_mm3=libraryVolume,volume_interval_mm3=interval,volume_method="native Boolean raster with one-cell boundary interval",low=new[]{bounds.vecMin.X,bounds.vecMin.Y,bounds.vecMin.Z},
high=new[]{bounds.vecMax.X,bounds.vecMax.Y,bounds.vecMax.Z},triangles=mesh.nTriangleCount(),
unsupported_triangles=unsupported,wall_rays_mm=thickness,inspected_rays=inspected,
grid=new{low,step,n},native_version=Library.strVersion(),manufacturing_authorized=false}));
} }
