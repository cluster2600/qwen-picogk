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
File.WriteAllText(Path.Combine(args[1],"refused.json"),JsonSerializer.Serialize(new {status="needs_measurement",manufacturing_authorized=false,missing=new[]{"measured_hole_pattern","mating_faces","load_cases"}}));
} }
