using System;
using System.IO;
using System.Globalization;
using System.Text.Json;

public static class Program
{
    public static void Main(string[] args)
    {
        if (args.Length != 2) throw new ArgumentException("input output-directory");
        bool inputValid = true;
        int points = 0;
        foreach (string line in File.ReadLines(args[0]))
        {
            string row = line.Trim();
            if (row.Length == 0 || row.StartsWith("#") || row.Equals("x,y,z", StringComparison.OrdinalIgnoreCase)) continue;
            string[] fields = row.Split(new[] { ',', ' ', '\t' }, StringSplitOptions.RemoveEmptyEntries);
            if (fields.Length != 3) { inputValid = false; continue; }
            foreach (string field in fields)
                if (!float.TryParse(field, NumberStyles.Float, CultureInfo.InvariantCulture, out float value) ||
                    !float.IsFinite(value)) inputValid = false;
            points++;
        }
        inputValid = inputValid && points > 0;
        // Even valid unsigned XYZ lacks the orientation, ranges and poses needed for a signed fusion.
        Directory.CreateDirectory(args[1]);
        File.WriteAllText(Path.Combine(args[1], "refused.json"), JsonSerializer.Serialize(new {
            status = "needs_measurement", manufacturing_authorized = false, input_valid = inputValid,
            missing = new[] { "validated_oriented_samples", "range_observations", "sensor_poses" }
        }));
    }
}
