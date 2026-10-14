using System.Globalization;
using System.Security.Cryptography;
using System.Text.Json;
using PicoGK;

// Trusted native step; no generated C# is compiled or executed.
if (args.Length != 5) throw new ArgumentException("Usage: closed.stl SHA256 scale_assumed voxel_mm NEW_PRIVATE_DIR");
string input = Path.GetFullPath(args[0]), output = Path.GetFullPath(args[4]);
string Hash(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
if (Hash(input) != args[1]) throw new InvalidDataException("Closed mesh hash mismatch");
float scale = float.Parse(args[2], CultureInfo.InvariantCulture);
float voxel = float.Parse(args[3], CultureInfo.InvariantCulture);
if (!float.IsFinite(scale) || scale < .1f || scale > 2 || !float.IsFinite(voxel) || voxel < .3f || voxel > 1.2f)
    throw new InvalidDataException("Outside the demo assumptions");
if (Directory.Exists(output) || File.Exists(output)) throw new IOException("Use a new private directory");
for (DirectoryInfo? parent = new(output); parent != null; parent = parent.Parent)
    if (File.Exists(Path.Combine(parent.FullName,".git")) || Directory.Exists(Path.Combine(parent.FullName,".git")))
    {
        if (!Path.GetRelativePath(parent.FullName,output).StartsWith("work"+Path.DirectorySeparatorChar,StringComparison.Ordinal))
            throw new IOException("Scan derivatives inside Git must stay under ignored work/");
        break;
    }
Directory.CreateDirectory(output);
using Library library = new(voxel);
using Mesh source = Mesh.mshFromStlFile(input,Mesh.EStlUnit.MM,libSet:library);
// Input was already scaled by the geometry worker; scale is recorded, not applied twice.
using Voxels solid = new(source);
solid.CalculateProperties(out float volume,out _);
using Mesh mesh = solid.mshAsMesh();
if (!float.IsFinite(volume) || volume <= 0 || mesh.nTriangleCount() == 0)
    throw new InvalidDataException("Empty native reconstruction");
string path = Path.Combine(output,"candidate.stl");
mesh.SaveToStlFile(path,Mesh.EStlUnit.MM);
using Mesh roundtrip = Mesh.mshFromStlFile(path,Mesh.EStlUnit.MM,libSet:library);
if (roundtrip.nTriangleCount()!=mesh.nTriangleCount() || Hash(input)!=args[1])
    throw new InvalidDataException("Changed input or STL roundtrip mismatch");
File.WriteAllText(Path.Combine(output,"native.json"),JsonSerializer.Serialize(new {
    input_sha256=args[1], output_sha256=Hash(path), triangles=mesh.nTriangleCount(),
    roundtrip_triangles=roundtrip.nTriangleCount(), volume_mm3_assumed=volume,
    mm_per_source_unit_assumed=scale, voxel_mm_assumed=voxel,
    runtime=new {name=Library.strName(),version=Library.strVersion(),build=Library.strBuildInfo()},
    manufacturing_qualified=false, generated_code_executed=false
},new JsonSerializerOptions {WriteIndented=true})+"\n");
