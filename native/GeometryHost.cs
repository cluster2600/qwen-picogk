using System.Numerics;
using System.Text.Json;
using PicoGK;
using Leap71.ShapeKernel;
using Leap71.LatticeLibrary;
using Leap71.ConstructionModules;
using PicoGK_Fasteners;

// Only owner-authored recipes run; model responses are numeric data, never C#.
if (args.Length == 1 && args[0] == "--api")
{
    var assemblies = new[]{typeof(Library).Assembly, typeof(BaseCylinder).Assembly};
    var types = assemblies.SelectMany(a => a.GetExportedTypes()).Where(t => t.Namespace != null)
        .OrderBy(t => t.FullName).Select(t => new {
            name = t.FullName,
            constructors = t.GetConstructors().Select(c => c.ToString()).ToArray(),
            methods = t.GetMethods(System.Reflection.BindingFlags.Public | System.Reflection.BindingFlags.Instance |
                                   System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.DeclaredOnly)
                       .Select(m => m.ToString()).OrderBy(x => x).ToArray()
        });
    Console.WriteLine(JsonSerializer.Serialize(types));
    return;
}
if (args.Length != 3) throw new ArgumentException("PLAN OUTPUT_STL VOXEL_MM");
using var document = JsonDocument.Parse(File.ReadAllText(args[0]));
var plan = document.RootElement;
if (plan.ValueKind != JsonValueKind.Object ||
    !plan.EnumerateObject().Select(x => x.Name).OrderBy(x => x)
         .SequenceEqual(new[]{"missing", "parameters_mm", "recipe"}) ||
    plan.GetProperty("missing").ValueKind != JsonValueKind.Array ||
    plan.GetProperty("missing").GetArrayLength() != 0)
    throw new ArgumentException("Only complete, strictly shaped plans can execute");
string recipe = plan.GetProperty("recipe").GetString() ?? "";
float[] p = plan.GetProperty("parameters_mm").EnumerateArray().Select(x => x.GetSingle()).ToArray();
int size = recipe switch { "cylinder" => 2, "pipe" or "washer" => 3, "bcc" => 2, "thread" => 4, _ => 0 };
if (size == 0 || p.Length != size || p.Any(x => !float.IsFinite(x) || x < 0.5f || x > 24f))
    throw new ArgumentException("Invalid recipe parameters");
if ((recipe is "pipe" or "washer") && p[2] >= p[1]) throw new ArgumentException("Bore must be smaller");
if (recipe == "bcc" && (p[1] > p[0] / 3 || p[0] > 18)) throw new ArgumentException("Lattice bounds");
if (recipe == "thread" && (p[2] >= p[1] || p[3] < 2 || p[0] / p[3] > 6)) throw new ArgumentException("Thread bounds");
float voxel = float.Parse(args[2], System.Globalization.CultureInfo.InvariantCulture);
if (voxel != 0.5f && voxel != 1f) throw new ArgumentException("Registered resolutions only");
using Library lib = new(voxel);
Library.RegisterGlobalLibrary(lib);
try
{
    LocalFrame frame = new(Vector3.Zero);
    Voxels solid;
    if (recipe == "cylinder") solid = new BaseCylinder(frame, p[0], p[1]).voxConstruct();
    else if (recipe == "pipe") solid = new BasePipe(frame, p[0], p[2], p[1]).voxConstruct();
    else if (recipe == "washer")
        solid = new Fastener(sDiscription: "Synthetic training witness", fWasherThickness: p[0],
                            fWasherDiameter: 2*p[1], fCloseFit: 2*p[2]).Washer(frame);
    else if (recipe == "thread") solid = new ThreadCutter(frame, p[0], p[1], p[2], p[3]).voxConstruct();
    else
    {
        Lattice lattice = new(lib);
        var cell = new RegularUnitCell(p[0], p[0], p[0], 0).aGetUnitCells().Single();
        new BodyCentreLattice().AddCell(ref lattice, cell, new ConstantBeamThickness(p[1]), 2);
        solid = new Voxels(lattice);
        lattice.Dispose();
    }
    using (solid)
    using (Mesh mesh = new(solid))
    {
        solid.CalculateProperties(out float volume, out BBox3 box);
        mesh.SaveToStlFile(args[1], Mesh.EStlUnit.MM);
        using Mesh roundtrip = Mesh.mshFromStlFile(args[1], Mesh.EStlUnit.MM, libSet: lib);
        Vector3 axis = new(0, 0, p[0]/2);
        Vector3 material = recipe switch {
            "pipe" or "washer" => new((p[1]+p[2])/2, 0, p[0]/2),
            _ => axis
        };
        Console.WriteLine(JsonSerializer.Serialize(new {
            recipe, volume, triangles = mesh.nTriangleCount(), roundtrip_triangles = roundtrip.nTriangleCount(),
            min = new[]{box.vecMin.X,box.vecMin.Y,box.vecMin.Z}, max = new[]{box.vecMax.X,box.vecMax.Y,box.vecMax.Z},
            material_inside = solid.bIsInside(material), axis_inside = solid.bIsInside(axis),
            distant_point_inside = solid.bIsInside(new Vector3(1000,1000,1000)), voxel_mm = voxel
        }));
    }
}
finally { Library.UnregisterGlobalLibrary(); }
