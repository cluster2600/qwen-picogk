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
        // Required fields come from the new input contract, never an OEM guess.
        using JsonDocument document=JsonDocument.Parse(string.Join("\n",File.ReadLines(args[0])));
        JsonElement root=document.RootElement;
        if(!root.TryGetProperty("measurements",out JsonElement values) || values.ValueKind!=JsonValueKind.Object
            || !root.TryGetProperty("required_measurements",out JsonElement requiredArray) || requiredArray.ValueKind!=JsonValueKind.Array)
            throw new InvalidDataException("Required names and measurement object required.");
        string[] required=requiredArray.EnumerateArray().Select(x=>x.GetString()!).ToArray();
        if(required.Length==0 || required.Any(string.IsNullOrWhiteSpace) || required.Distinct().Count()!=required.Length)
            throw new InvalidDataException("Distinct required scalar measurement names required.");
        var missing=new List<string>();
        foreach(string name in required)
            if(!values.TryGetProperty(name,out JsonElement value) || value.ValueKind!=JsonValueKind.Number
                || !value.TryGetDouble(out double scalar) || !double.IsFinite(scalar)) missing.Add(name);
        File.WriteAllText(Path.Combine(args[1],"refused.json"),JsonSerializer.Serialize(new {
            status=missing.Count>0 ? "needs_measurement" : "needs_engineering_review",
            manufacturing_authorized=false, missing=missing.ToArray() }));

    }

}
