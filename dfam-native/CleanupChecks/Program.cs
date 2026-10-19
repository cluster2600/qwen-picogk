using System.Numerics;
using System.Text.Json;

static void Require(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}
static void Reject(Action action)
{
    try { action(); }
    catch (ArgumentException) { return; }
    catch (OverflowException) { return; }
    throw new InvalidOperationException("Invalid input was accepted");
}

// Closed tetrahedron, with an acquired near-duplicate vertex at its apex.
Vector3 a = new(0, 0, 0), b = new(1, 0, 0), c = new(0, 1, 0), d = new(0, 0, 1);
Vector3 nearD = d + new Vector3(0.00001f, 0, 0);
var raw = new List<(Vector3 A, Vector3 B, Vector3 C)>
{
    (a, c, b), (a, b, d), (a, nearD, c), (b, c, d),
    (a, a + new Vector3(0.00001f, 0, 0), b), // weld-collapsed face
    (a, b, new Vector3(2, 0, 0))             // exact collinear face
};
var clean = MeshCleanup.WeldAndFilter(raw, 0.0001f, out int removed, out float movement);
Require(removed == 2 && clean.Count == 4, "Wrong degenerate removal count");
Require(movement > 0 && movement <= MathF.Sqrt(3) * 0.0001f, "Unbounded vertex movement");
var edges = new Dictionary<(Vector3, Vector3), int>();
foreach (var t in clean)
    foreach (var e in new[] { (t.A, t.B), (t.B, t.C), (t.C, t.A) })
        edges[e] = edges.GetValueOrDefault(e) + 1;
Require(edges.Count == 12 && edges.All(e => e.Value == 1 && edges.ContainsKey((e.Key.Item2, e.Key.Item1))),
        "Welded tetrahedron has a hole, duplicate edge or wrong orientation");
// Near-duplicates on either side of a cell boundary must weld too, or they leave needles.
Vector3 acrossD = d + new Vector3(0, 0.00006f, 0);           // rounds into the next cell, 0.06 um away
var crossRaw = new List<(Vector3 A, Vector3 B, Vector3 C)> { (a, c, b), (a, b, d), (a, acrossD, c), (b, c, d) };
var crossClean = MeshCleanup.WeldAndFilter(crossRaw, 0.0001f, out int crossRemoved, out float crossMoved);
Require(crossClean.Count == 4 && crossRemoved == 0 && crossClean[2] == (a, d, c) && crossMoved <= 0.0001f,
        "Near-duplicate across a cell boundary was not welded");
Vector3 p = new(0.00004f, 0, 0), pAcross = new(0.00006f, 0, 0), q = new(1, 0, 0.001f);
var needle = MeshCleanup.WeldAndFilter(new[] { (p, pAcross, q) }, 0.0001f, out int needleRemoved, out _);
Require(needle.Count == 0 && needleRemoved == 1, "Needle across a cell boundary survived");
Vector3 pFar = new(0.000145f, 0, 0);                          // next cell, but beyond the tolerance
var apart = MeshCleanup.WeldAndFilter(new[] { (p, pFar, q) }, 0.0001f, out int apartRemoved, out float apartMoved);
Require(apart.Single() == (p, pFar, q) && apartRemoved == 0 && apartMoved == 0, "Vertices beyond the tolerance were merged");
var again = MeshCleanup.WeldAndFilter(clean, 0.0001f, out int removedAgain, out float movementAgain);
Require(again.SequenceEqual(clean) && removedAgain == 0 && movementAgain == 0, "Cleanup is not idempotent");
var untouched = MeshCleanup.WeldAndFilter(new[] { (a, b, c) }, 0.0001f, out int r, out float m);
Require(untouched.Single() == (a, b, c) && r == 0 && m == 0, "Valid triangle was changed");
foreach (float bad in new[] { 0f, -1f, float.NaN, float.PositiveInfinity, float.Epsilon, float.MaxValue })
    Reject(() => MeshCleanup.WeldAndFilter(raw, bad, out _, out _));
Reject(() => MeshCleanup.WeldAndFilter(new[] { (a, b, new Vector3(float.NaN, 0, 0)) }, 0.0001f, out _, out _));
Reject(() => MeshCleanup.WeldAndFilter(new[] { (a, b, new Vector3(float.MaxValue, 0, 0)) }, 0.0001f, out _, out _));
// At large coordinates, adjacent floats can quantize into the same cell.
float x1 = MathF.BitIncrement(14000f), x2 = MathF.BitIncrement(x1);
Require(MathF.Round(x1 * 10000f) == MathF.Round(x2 * 10000f), "Precision fixture no longer collides");
Reject(() => MeshCleanup.WeldAndFilter(new[] { (new Vector3(x1, 0, 0), new Vector3(x2, 0, 0), a) },
                                      0.0001f, out _, out _));
Console.WriteLine(JsonSerializer.Serialize(new
{
    passed = true, tests = 18, synthetic_only = true,
    picogk_loaded = false, corpus_native_verification = false,
    removed_triangles = removed, max_vertex_displacement_mm = movement
}));
