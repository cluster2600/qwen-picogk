using System;
using System.Collections.Generic;
using System.Numerics;

// Numerical export cleanup, independent of PicoGK and physical qualification.
// The corpus embeds this exact source so its C# example stays self-contained.
public static class MeshCleanup
{
    // Weld onto the first vertex in each quantized cell, preserving winding.
    // Vertices are actually replaced; merely dropping tiny faces could leave holes.
    public static List<(Vector3 A, Vector3 B, Vector3 C)> WeldAndFilter(
        IEnumerable<(Vector3 A, Vector3 B, Vector3 C)> input, float tolerance,
        out int removed, out float maxDisplacement)
    {
        if (!float.IsFinite(tolerance) || tolerance <= 0 || !float.IsFinite(1f / tolerance) ||
            !float.IsFinite(MathF.Sqrt(3) * tolerance))
            throw new ArgumentOutOfRangeException(nameof(tolerance));
        float scale = 1f / tolerance;
        var vertices = new Dictionary<(long, long, long), Vector3>();
        var result = new List<(Vector3, Vector3, Vector3)>();
        int dropped = 0;
        float moved = 0;

        Vector3 Weld(Vector3 v)
        {
            if (!float.IsFinite(v.X) || !float.IsFinite(v.Y) || !float.IsFinite(v.Z))
                throw new ArgumentException("Nonfinite mesh vertex");
            // Same rounded-cell convention as the independent STL checker.
            var key = (checked((long)MathF.Round(v.X * scale)),
                       checked((long)MathF.Round(v.Y * scale)),
                       checked((long)MathF.Round(v.Z * scale)));
            if (!vertices.TryGetValue(key, out Vector3 canonical))
                vertices[key] = canonical = v;
            float displacement = Vector3.Distance(v, canonical);
            // Large coordinates can lose precision during float quantization.
            // Refuse a weld that exceeds the cell-diagonal movement budget.
            if (!float.IsFinite(displacement) || displacement > MathF.Sqrt(3) * tolerance)
                throw new ArgumentException("Vertex weld exceeds the declared tolerance budget");
            moved = MathF.Max(moved, displacement);
            return canonical;
        }

        foreach (var t in input)
        {
            Vector3 a = Weld(t.A), b = Weld(t.B), c = Weld(t.C);
            Vector3 cross = Vector3.Cross(b - a, c - a);
            if (!float.IsFinite(cross.X) || !float.IsFinite(cross.Y) || !float.IsFinite(cross.Z))
                throw new ArgumentException("Nonfinite triangle area");
            // Remove collapsed and numerically zero-area faces after welding.
            if (a == b || b == c || a == c || cross.LengthSquared() == 0)
            {
                dropped++;
                continue;
            }
            result.Add((a, b, c));
        }
        removed = dropped;
        maxDisplacement = moved;
        return result;
    }
}
