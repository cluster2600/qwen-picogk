using System;
using System.Globalization;
using System.IO;
using System.Numerics;
using System.Reflection;
using PicoGK;

namespace AmDatasetValidation;

public static class Runner
{
    public static int Main(string[] args)
    {
        if (args.Length == 4 && args[0] == "screen-fixture")
            return ScreenFixture(args[1], args[2], args[3]);
        if (args.Length != 3 || !int.TryParse(args[0], out int id) || id < 1 || id > 150)
        {
            Console.Error.WriteLine("Usage: AmDatasetValidation <id 1..150> <synthetic input> <output directory>");
            return 2;
        }

        // Invariant output makes geometric receipts comparable across local cultures.
        CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
        CultureInfo.CurrentUICulture = CultureInfo.InvariantCulture;
        Type example = Assembly.GetExecutingAssembly().GetType($"AmDataset.Ex{id:D3}.Program")
            ?? throw new InvalidOperationException($"Example {id:D3} was not compiled.");
        MethodInfo entry = example.GetMethod("Main", BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static)
            ?? throw new InvalidOperationException($"Example {id:D3} has no static Main.");
        try
        {
            object? result = entry.Invoke(null, new object[] { new[] { args[1], args[2] } });
            return result is int exitCode ? exitCode : 0;
        }
        catch (TargetInvocationException failure) when (failure.InnerException is not null)
        {
            Console.Error.WriteLine(failure.InnerException);
            return 1;
        }
    }

    private static int ScreenFixture(string shape, string input, string output)
    {
        if (shape != "cube" && shape != "sealed" && shape != "drained" && shape != "floating" && shape != "below")
            throw new ArgumentException("Unknown synthetic screen fixture.");
        if (Directory.Exists(output)) throw new IOException("Preserve the previous synthetic fixture output.");
        Directory.CreateDirectory(output);
        using Library lib = new(0.2f);
        using Mesh sourceMesh = Mesh.mshFromStlFile(input, Mesh.EStlUnit.MM, libSet: lib);
        float displacement = shape == "floating" ? 0.1f : shape == "below" ? -0.2f : 0;
        using Mesh mesh = sourceMesh.mshCreateTransformed(Vector3.One, new Vector3(0, 0, displacement));
        using Voxels scan = new(mesh);
        using Voxels candidate = new(scan);
        if (shape == "sealed" || shape == "drained")
        {
            using Voxels cavity = new(scan);
            cavity.Offset(-1.0f);
            candidate.BoolSubtract(cavity);
        }
        if (shape == "drained")
        {
            using Lattice drill = new(lib);
            drill.AddBeam(new Vector3(0, 0, -1), 1.5f, new Vector3(0, 0, 2.5f), 1.5f, false);
            using Voxels cutter = new(drill);
            candidate.BoolSubtract(cutter);
        }
        // Invoke the actual dataset screen, so assertions test the training code's shared logic.
        Type example = Assembly.GetExecutingAssembly().GetType("AmDataset.Ex136.Program")!;
        MethodInfo screen = example.GetMethod("Screen", BindingFlags.NonPublic | BindingFlags.Static)!;
        screen.Invoke(null, new object[] { candidate, output, 0.2f, 1.0f });
        return 0;
    }
}
