using System;
using System.IO;
using System.Linq;
using System.Text.Json;

public static class Program
{
    public static void Main(string[] args)
    {
        if (args.Length != 2) throw new ArgumentException("input output-directory");
        // Preserve earlier evidence rather than overwriting an existing output.
        if (Directory.Exists(args[1]) && Directory.EnumerateFileSystemEntries(args[1]).Any())
            throw new IOException("Use an empty output directory.");
        Directory.CreateDirectory(args[1]);
        // The prompt supplies the missing evidence IDs. No input file is read.
        // No PicoGK context, native object or geometry is justified for this refusal.
        File.WriteAllText(Path.Combine(args[1], "refused.json"), JsonSerializer.Serialize(new {
            decision="needs_measurement", missing_measurements=new[]{"datum_reference_frame","hole_axis_locations","mating_stack_limits"}, fabrication_authorized=false }));
    }
}
