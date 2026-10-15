using System.Globalization;
using System.Numerics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using PicoGK;

// Trusted side of the DfAM code corpus. This program creates deterministic
// synthetic scan fixtures and measures output meshes. It never compiles,
// loads or executes corpus code, so a corpus example cannot grade itself.
//
//   fixtures NEW_DIR VOXEL_MM
//   check    OUTPUT.stl FIXTURES.json VOXEL_MM MIN_WALL_MM [THICKNESS.bin]
//   selftest
CultureInfo.DefaultThreadCurrentCulture = CultureInfo.InvariantCulture;
CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
if (args.Length == 3 && args[0] == "fixtures")
    return Fixtures.Write(Path.GetFullPath(args[1]), float.Parse(args[2]));
if ((args.Length == 5 || args.Length == 6) && args[0] == "check")
    return Checks.Run(args[1], args[2], float.Parse(args[3]), float.Parse(args[4]), args.Length == 6 ? args[5] : null);
if (args.Length == 1 && args[0] == "selftest")
    return WallThickness.SelfTest();
Console.Error.WriteLine("Usage: fixtures NEW_DIR VOXEL_MM | check OUTPUT.stl FIXTURES.json VOXEL_MM MIN_WALL_MM [THICKNESS.bin] | selftest");
return 2;

/// <summary>
/// Generic synthetic "scanned" blank: a rounded slab with a bored boss and a
/// smaller pin boss, blended with a smooth minimum. It is not a vehicle part.
/// The slab bottom lies on z = 0, the build plate.
/// </summary>
sealed class FixtureShape : IBoundedImplicit
{
    public BBox3 oBounds => new(new Vector3(-38, -25, -2), new Vector3(38, 25, 32));

    static float fRoundBox(Vector3 p, Vector3 c, Vector3 h, float r)
    {
        Vector3 q = Vector3.Abs(p - c) - (h - new Vector3(r));
        return Vector3.Max(q, Vector3.Zero).Length() + MathF.Min(MathF.Max(q.X, MathF.Max(q.Y, q.Z)), 0) - r;
    }

    static float fCylinderZ(Vector3 p, float x, float y, float r, float z0, float z1)
    {
        Vector2 d = new(new Vector2(p.X - x, p.Y - y).Length() - r, MathF.Abs(p.Z - 0.5f * (z0 + z1)) - 0.5f * (z1 - z0));
        return MathF.Min(MathF.Max(d.X, d.Y), 0) + Vector2.Max(d, Vector2.Zero).Length();
    }

    static float fSmoothMin(float a, float b, float k)
    {
        float h = Math.Clamp(0.5f + 0.5f * (b - a) / k, 0, 1);
        return b + (a - b) * h - k * h * (1 - h);
    }

    public float fSignedDistance(in Vector3 p)
    {
        float slab = fRoundBox(p, new Vector3(0, 0, 8), new Vector3(35, 22, 8), 4);
        float boss = fCylinderZ(p, 20, 0, 11, 0, 30);
        float pin  = fCylinderZ(p, -22, 0, 7, 0, 22);
        float body = fSmoothMin(fSmoothMin(slab, boss, 3), pin, 3);
        float bore = fCylinderZ(p, 20, 0, 4.5f, -5, 35);
        // Clip the blend bulge so the part sits flat on the plate at z = 0.
        return MathF.Max(MathF.Max(body, -bore), -p.Z);
    }
}

static class Fixtures
{
    public static int Write(string dir, float voxel)
    {
        if (Directory.Exists(dir) || File.Exists(dir)) throw new IOException("Use a new fixture directory");
        Directory.CreateDirectory(dir);
        using Library lib = new(voxel);
        using Voxels vox = new(lib, new FixtureShape());
        using Mesh msh = vox.mshAsMesh();
        vox.CalculateProperties(out float volume, out BBox3 box);
        msh.SaveToStlFile(Path.Combine(dir, "part.stl"), Mesh.EStlUnit.MM);

        // Orientation sign, so sampled normals point outward.
        float sign = Checks.fSignedVolume(msh) >= 0 ? 1 : -1;
        int n = msh.nTriangleCount();
        double[] cumulative = new double[n];
        double total = 0;
        for (int i = 0; i < n; i++)
        {
            msh.GetTriangle(i, out Vector3 a, out Vector3 b, out Vector3 c);
            total += 0.5 * Vector3.Cross(b - a, c - a).Length();
            cumulative[i] = total;
        }

        // Scanner gaps: points inside these spheres are dropped, and the open
        // STL loses the triangles inside them.
        Vector3[] gaps = { new(0, 22, 9), new(20, 0, 30), new(-30, -10, 16) };
        const float gapRadius = 3.5f;
        bool bInGap(Vector3 p) => gaps.Any(g => Vector3.Distance(g, p) < gapRadius);

        Random rnd = new(9931014);
        float Gauss() => (float)(Math.Sqrt(-2 * Math.Log(1 - rnd.NextDouble())) * Math.Cos(2 * Math.PI * rnd.NextDouble()));
        StringBuilder xyz = new("# synthetic scan fixture, millimetres, columns: x y z\n");
        StringBuilder xyzn = new("# synthetic scan fixture, millimetres, columns: x y z nx ny nz\n");
        StringBuilder csv = new("x,y,z,nx,ny,nz\n");
        int points = 0, outliers = 0;
        BBox3 grown = box; grown.Grow(5);
        for (int k = 0; k < 90000; k++)
        {
            Vector3 p, nrm;
            if (rnd.NextDouble() < 0.005)
            {
                // Isolated outliers, as left by reflections and fixture clutter.
                p = grown.vecRandomVectorInside(ref rnd);
                nrm = Vector3.Normalize(new Vector3(Gauss(), Gauss(), Gauss()));
                outliers++;
            }
            else
            {
                int i = Array.BinarySearch(cumulative, rnd.NextDouble() * total);
                if (i < 0) i = ~i;
                i = Math.Min(i, n - 1);
                msh.GetTriangle(i, out Vector3 a, out Vector3 b, out Vector3 c);
                float u = (float)rnd.NextDouble(), v = (float)rnd.NextDouble();
                if (u + v > 1) { u = 1 - u; v = 1 - v; }
                Vector3 face = Vector3.Normalize(Vector3.Cross(b - a, c - a)) * sign;
                p = a + u * (b - a) + v * (c - a);
                if (bInGap(p)) continue;
                // Range noise along the normal and a little lateral jitter.
                p += face * (0.06f * Gauss()) + new Vector3(Gauss(), Gauss(), Gauss()) * 0.02f;
                nrm = Vector3.Normalize(face + new Vector3(Gauss(), Gauss(), Gauss()) * 0.05f);
            }
            xyz.Append(FormattableString.Invariant($"{p.X:F4} {p.Y:F4} {p.Z:F4}\n"));
            xyzn.Append(FormattableString.Invariant($"{p.X:F4} {p.Y:F4} {p.Z:F4} {nrm.X:F5} {nrm.Y:F5} {nrm.Z:F5}\n"));
            csv.Append(FormattableString.Invariant($"{p.X:F4},{p.Y:F4},{p.Z:F4},{nrm.X:F5},{nrm.Y:F5},{nrm.Z:F5}\n"));
            points++;
        }
        File.WriteAllText(Path.Combine(dir, "scan.xyz"), xyz.ToString());
        File.WriteAllText(Path.Combine(dir, "scan_normals.xyz"), xyzn.ToString());
        File.WriteAllText(Path.Combine(dir, "scan.csv"), csv.ToString());

        using Mesh open = new(lib);
        for (int i = 0; i < n; i++)
        {
            msh.GetTriangle(i, out Vector3 a, out Vector3 b, out Vector3 c);
            if (!bInGap((a + b + c) / 3)) open.nAddTriangle(a, b, c);
        }
        open.SaveToStlFile(Path.Combine(dir, "part_open.stl"), Mesh.EStlUnit.MM);

        var files = new SortedDictionary<string, string>();
        foreach (string f in new[] { "part.stl", "part_open.stl", "scan.xyz", "scan_normals.xyz", "scan.csv" })
            files[f] = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(Path.Combine(dir, f)))).ToLowerInvariant();
        File.WriteAllText(Path.Combine(dir, "fixtures.json"), JsonSerializer.Serialize(new
        {
            shape = "synthetic rounded slab with bored boss and pin boss; not a vehicle part",
            voxel_mm = voxel, volume_mm3 = volume,
            bbox_min = new[] { box.vecMin.X, box.vecMin.Y, box.vecMin.Z },
            bbox_max = new[] { box.vecMax.X, box.vecMax.Y, box.vecMax.Z },
            scan_points = points, scan_outliers = outliers, scan_noise_sigma_mm = 0.06,
            gap_centres = gaps.Select(g => new[] { g.X, g.Y, g.Z }), gap_radius_mm = gapRadius,
            triangles = n, open_triangles = open.nTriangleCount(), files_sha256 = files,
        }, new JsonSerializerOptions { WriteIndented = true }) + "\n");
        return 0;
    }
}

static class Checks
{
    public static float fSignedVolume(Mesh msh)
    {
        double v = 0;
        for (int i = 0; i < msh.nTriangleCount(); i++)
        {
            msh.GetTriangle(i, out Vector3 a, out Vector3 b, out Vector3 c);
            v += Vector3.Dot(a, Vector3.Cross(b, c)) / 6.0;
        }
        return (float)v;
    }

    public static int Run(string stl, string fixturesJson, float voxel, float minWall, string? dumpPath = null)
    {
        using JsonDocument fx = JsonDocument.Parse(File.ReadAllText(fixturesJson));
        float fixtureVolume = fx.RootElement.GetProperty("volume_mm3").GetSingle();
        using Library lib = new(voxel);
        using Mesh msh = Mesh.mshFromStlFile(stl, Mesh.EStlUnit.MM, libSet: lib);
        int n = msh.nTriangleCount();
        var result = new SortedDictionary<string, object> { ["triangles"] = n };
        if (n == 0) { Emit(result); return 0; }

        // Edge topology on welded vertices: a closed, consistently oriented
        // 2-manifold has every undirected edge used exactly twice.
        var ids = new Dictionary<(long, long, long), int>();
        int Id(Vector3 v)
        {
            var key = ((long)MathF.Round(v.X * 1e4f), (long)MathF.Round(v.Y * 1e4f), (long)MathF.Round(v.Z * 1e4f));
            if (!ids.TryGetValue(key, out int id)) ids[key] = id = ids.Count;
            return id;
        }
        var undirected = new Dictionary<(int, int), int>();
        var directed = new HashSet<(int, int)>();
        int duplicateDirected = 0, degenerate = 0;
        double area = 0, downArea = 0, signedVolume = 0;
        float sign = fSignedVolume(msh) >= 0 ? 1 : -1;
        BBox3 box = msh.oBoundingBox();
        float plateBand = box.vecMin.Z + 1.5f * voxel;
        float cos45 = MathF.Cos(MathF.PI / 4);
        for (int i = 0; i < n; i++)
        {
            msh.GetTriangle(i, out Vector3 a, out Vector3 b, out Vector3 c);
            int[] t = { Id(a), Id(b), Id(c) };
            if (t[0] == t[1] || t[1] == t[2] || t[0] == t[2]) { degenerate++; continue; }
            for (int e = 0; e < 3; e++)
            {
                int u = t[e], v = t[(e + 1) % 3];
                var k = (Math.Min(u, v), Math.Max(u, v));
                undirected[k] = undirected.GetValueOrDefault(k) + 1;
                if (!directed.Add((u, v))) duplicateDirected++;
            }
            Vector3 cr = Vector3.Cross(b - a, c - a) * sign;
            float twice = cr.Length();
            signedVolume += Vector3.Dot(a, Vector3.Cross(b, c)) / 6.0;
            if (twice <= 0) continue;
            area += 0.5 * twice;
            // Downward-facing surface closer than 45 degrees to the build plate,
            // excluding the plate contact band itself.
            if (cr.Z / twice < -cos45 && (a.Z + b.Z + c.Z) / 3 > plateBand) downArea += 0.5 * twice;
        }
        result["boundary_edges"] = undirected.Values.Count(x => x == 1);
        result["nonmanifold_edges"] = undirected.Values.Count(x => x > 2);
        result["inconsistent_orientation_edges"] = duplicateDirected;
        result["degenerate_triangles"] = degenerate;
        result["surface_area_mm2"] = Math.Round(area, 2);
        result["mesh_volume_mm3"] = Math.Round(Math.Abs(signedVolume), 2);
        result["overhang_area_mm2"] = Math.Round(downArea, 2);
        result["overhang_fraction"] = Math.Round(downArea / area, 4);
        result["bbox_min"] = new[] { box.vecMin.X, box.vecMin.Y, box.vecMin.Z };
        result["bbox_max"] = new[] { box.vecMax.X, box.vecMax.Y, box.vecMax.Z };

        using Voxels vox = new(msh);
        vox.CalculateProperties(out float volume, out _);
        result["volume_mm3"] = Math.Round(volume, 2);
        result["volume_ratio_to_fixture"] = Math.Round(volume / fixtureVolume, 4);

        // Occupancy by ray parity, independent of OpenVDB. Mesh-to-level-set
        // conversion fills fully enclosed cavities, which would hide trapped
        // powder; parity along z keeps every cavity bounded by the mesh.
        int X = (int)MathF.Ceiling((box.vecMax.X - box.vecMin.X) / voxel) + 2;
        int Y = (int)MathF.Ceiling((box.vecMax.Y - box.vecMin.Y) / voxel) + 2;
        int Z = (int)MathF.Ceiling((box.vecMax.Z - box.vecMin.Z) / voxel) + 2;
        Vector3 vecOrigin = box.vecMin - new Vector3(voxel);   // centre of cell i is origin + (i + 0.5) voxel
        byte[] g = ParityGrid(msh, vecOrigin, voxel, X, Y, Z);
        long Idx(int x, int y, int z) => x + (long)X * (y + (long)Y * z);
        int[] dx = { 1, -1, 0, 0, 0, 0 }, dy = { 0, 0, 1, -1, 0, 0 }, dz = { 0, 0, 0, 0, 1, -1 };
        // Labels: 0 unvisited, 2 visited. Returns cell count of one 6-connected region.
        long Flood(int sx, int sy, int sz, byte want, byte[] seen)
        {
            var q = new Queue<(int, int, int)>();
            q.Enqueue((sx, sy, sz)); seen[Idx(sx, sy, sz)] = 2;
            long count = 0;
            while (q.Count > 0)
            {
                var (x, y, z) = q.Dequeue(); count++;
                for (int d = 0; d < 6; d++)
                {
                    int ax = x + dx[d], ay = y + dy[d], az = z + dz[d];
                    if (ax < 0 || ay < 0 || az < 0 || ax >= X || ay >= Y || az >= Z) continue;
                    long j = Idx(ax, ay, az);
                    if (g[j] != want || seen[j] != 0) continue;
                    seen[j] = 2; q.Enqueue((ax, ay, az));
                }
            }
            return count;
        }
        byte[] seen = new byte[g.LongLength];
        Flood(0, 0, 0, 0, seen);                               // exterior air
        long enclosedCells = 0, solidCells = 0, largestVoid = 0; int voidRegions = 0, components = 0; long largest = 0;
        for (int z = 0; z < Z; z++)
            for (int y = 0; y < Y; y++)
                for (int x = 0; x < X; x++)
                {
                    long j = Idx(x, y, z);
                    if (seen[j] != 0) continue;
                    if (g[j] == 0) { voidRegions++; long v = Flood(x, y, z, 0, seen); enclosedCells += v; largestVoid = Math.Max(largestVoid, v); }
                    else { components++; long c = Flood(x, y, z, 1, seen); solidCells += c; largest = Math.Max(largest, c); }
                }
        float cell = voxel * voxel * voxel;
        result["enclosed_void_regions"] = voidRegions;
        result["enclosed_void_mm3"] = Math.Round(enclosedCells * cell, 3);
        result["enclosed_void_largest_mm3"] = Math.Round(largestVoid * cell, 3);
        result["solid_components"] = components;
        result["parity_volume_mm3"] = Math.Round(solidCells * cell, 2);
        result["largest_component_fraction"] = solidCells == 0 ? 0 : Math.Round((double)largest / solidCells, 5);

        // Morphological opening with radius minWall/2 removes every feature
        // thinner than minWall; the removed share is the thin-feature fraction.
        using Voxels opened = vox.voxOffset(-0.5f * minWall);
        opened.Offset(0.5f * minWall);
        opened.CalculateProperties(out float openedVolume, out _);
        result["min_wall_mm"] = minWall;
        result["thin_fraction"] = volume <= 0 ? 1 : Math.Round(Math.Max(0, volume - openedVolume) / volume, 4);

        // Wall thickness on the mesh itself, independent of the voxel size:
        // from every triangle's centroid, cast a ray along the inward normal
        // to the first other triangle. Distances are capped, because only
        // walls near the minimum matter.
        var tris = new (Vector3 a, Vector3 b, Vector3 c)[n];
        for (int i = 0; i < n; i++)
        {
            msh.GetTriangle(i, out Vector3 a, out Vector3 b, out Vector3 c);
            tris[i] = (a, b, c);
        }
        float cap = WallThickness.CapMM(minWall);
        float[] thickness = WallThickness.Measure(tris, sign, cap, out double[] areas);
        WallThickness.Summarise(thickness, areas, minWall, cap, result);
        result["needle_triangles"] = WallThickness.Needles(tris);
        if (dumpPath != null) WallThickness.Dump(dumpPath, tris, thickness);
        Emit(result);
        return 0;
    }

    /// <summary>
    /// Solid occupancy of cell centres: a vertical ray through each column
    /// counts mesh crossings below the centre; odd parity means inside. The
    /// ray is jittered by an irrational fraction of a cell to avoid edges.
    /// </summary>
    static byte[] ParityGrid(Mesh msh, Vector3 o, float h, int X, int Y, int Z)
    {
        var bins = new List<int>?[X * Y];
        int n = msh.nTriangleCount();
        var tris = new (Vector3 a, Vector3 b, Vector3 c)[n];
        for (int t = 0; t < n; t++)
        {
            msh.GetTriangle(t, out Vector3 a, out Vector3 b, out Vector3 c);
            tris[t] = (a, b, c);
            int i0 = Math.Max(0, (int)MathF.Floor((MathF.Min(a.X, MathF.Min(b.X, c.X)) - o.X) / h - 0.5f));
            int i1 = Math.Min(X - 1, (int)MathF.Ceiling((MathF.Max(a.X, MathF.Max(b.X, c.X)) - o.X) / h - 0.5f));
            int j0 = Math.Max(0, (int)MathF.Floor((MathF.Min(a.Y, MathF.Min(b.Y, c.Y)) - o.Y) / h - 0.5f));
            int j1 = Math.Min(Y - 1, (int)MathF.Ceiling((MathF.Max(a.Y, MathF.Max(b.Y, c.Y)) - o.Y) / h - 0.5f));
            for (int j = j0; j <= j1; j++)
                for (int i = i0; i <= i1; i++)
                    (bins[i + X * j] ??= new List<int>()).Add(t);
        }
        byte[] g = new byte[(long)X * Y * Z];
        double jx = h * 1.234567e-3 * Math.Sqrt(2), jy = h * 2.345678e-3 * Math.Sqrt(3);
        Parallel.For(0, X * Y, col =>
        {
            List<int>? bin = bins[col];
            if (bin == null) return;
            int i = col % X, j = col / X;
            double px = o.X + (i + 0.5) * h + jx, py = o.Y + (j + 0.5) * h + jy;
            var zs = new List<double>();
            foreach (int t in bin)
            {
                var (a, b, c) = tris[t];
                double d = (b.Y - c.Y) * (a.X - c.X) + (c.X - b.X) * (a.Y - c.Y);
                if (Math.Abs(d) < 1e-18) continue;                    // vertical triangle
                double l1 = ((b.Y - c.Y) * (px - c.X) + (c.X - b.X) * (py - c.Y)) / d;
                double l2 = ((c.Y - a.Y) * (px - c.X) + (a.X - c.X) * (py - c.Y)) / d;
                double l3 = 1 - l1 - l2;
                if (l1 < 0 || l2 < 0 || l3 < 0) continue;
                zs.Add(l1 * a.Z + l2 * b.Z + l3 * c.Z);
            }
            if (zs.Count == 0) return;
            zs.Sort();
            int crossed = 0;
            for (int k = 0; k < Z; k++)
            {
                double zc = o.Z + (k + 0.5) * h;
                while (crossed < zs.Count && zs[crossed] < zc) crossed++;
                if ((crossed & 1) == 1) g[i + (long)X * (j + (long)Y * k)] = 1;
            }
        });
        return g;
    }

    static void Emit(object o) => Console.WriteLine(JsonSerializer.Serialize(o));
}

/// <summary>
/// Wall thickness by inward ray casting on the output mesh. The ray from a
/// triangle's centroid along its inward normal leaves the solid on the other
/// side of the wall, so the first hit distance is the local wall thickness.
/// This needs no voxels: a 1.0 mm wall is not quantised to 0.3 mm cells.
/// Rays that run along a wall overestimate it, so a thin wall is detected
/// from its broad faces, whose normals cross it.
/// </summary>
static class WallThickness
{
    const float CellMM = 0.6f;         // acceleration grid, about two output voxels
    const double HitEpsilonMM = 1e-5;  // ignore hits at the ray origin

    // Walls well above the minimum do not need exact values.
    public static float CapMM(float minWall) => MathF.Max(4f * minWall, 3f);

    public static float[] Measure((Vector3 a, Vector3 b, Vector3 c)[] tris, float sign, float cap, out double[] areas)
    {
        int n = tris.Length;
        double[] area = new double[n];
        Vector3 lo = new(float.MaxValue), hi = new(float.MinValue);
        foreach (var t in tris)
        {
            lo = Vector3.Min(lo, Vector3.Min(t.a, Vector3.Min(t.b, t.c)));
            hi = Vector3.Max(hi, Vector3.Max(t.a, Vector3.Max(t.b, t.c)));
        }
        lo -= new Vector3(CellMM); hi += new Vector3(CellMM);
        int X = (int)MathF.Ceiling((hi.X - lo.X) / CellMM), Y = (int)MathF.Ceiling((hi.Y - lo.Y) / CellMM);
        int Z = (int)MathF.Ceiling((hi.Z - lo.Z) / CellMM);
        int Cell(float v, float o, int count) => Math.Clamp((int)MathF.Floor((v - o) / CellMM), 0, count - 1);

        // Compressed cell -> triangle lists, filled from each triangle's bounding box.
        long cells = (long)X * Y * Z;
        if (cells > int.MaxValue - 1) throw new InvalidOperationException("Mesh too large for the thickness grid");
        int[] start = new int[cells + 1];
        void Boxes(Action<int, int> visit)
        {
            for (int t = 0; t < n; t++)
            {
                var (a, b, c) = tris[t];
                Vector3 mn = Vector3.Min(a, Vector3.Min(b, c)), mx = Vector3.Max(a, Vector3.Max(b, c));
                for (int z = Cell(mn.Z, lo.Z, Z); z <= Cell(mx.Z, lo.Z, Z); z++)
                    for (int y = Cell(mn.Y, lo.Y, Y); y <= Cell(mx.Y, lo.Y, Y); y++)
                        for (int x = Cell(mn.X, lo.X, X); x <= Cell(mx.X, lo.X, X); x++)
                            visit(x + X * (y + Y * z), t);
            }
        }
        Boxes((cell, _) => start[cell + 1]++);
        for (long i = 0; i < cells; i++) start[i + 1] += start[i];
        int[] fill = (int[])start.Clone();
        int[] items = new int[start[cells]];
        Boxes((cell, t) => items[fill[cell]++] = t);

        float[] result = new float[n];
        Parallel.For(0, n, i =>
        {
            var (a, b, c) = tris[i];
            Vector3 cr = Vector3.Cross(b - a, c - a) * sign;
            float len = cr.Length();
            area[i] = 0.5 * len;
            if (!(len > 0)) { result[i] = float.NaN; return; }
            Vector3 dir = -cr / len, o = (a + b + c) / 3f;
            result[i] = Cast(o, dir, i, cap);
        });
        areas = area;
        return result;

        float Cast(Vector3 o, Vector3 d, int self, float limit)
        {
            int ix = Cell(o.X, lo.X, X), iy = Cell(o.Y, lo.Y, Y), iz = Cell(o.Z, lo.Z, Z);
            // Amanatides-Woo traversal: tMax is the ray parameter at the next cell wall per axis.
            (int step, float tMax, float tDelta) Axis(float oc, float dc, float origin, int idx)
            {
                if (dc > 0) return (1, (origin + (idx + 1) * CellMM - oc) / dc, CellMM / dc);
                if (dc < 0) return (-1, (origin + idx * CellMM - oc) / dc, -CellMM / dc);
                return (0, float.PositiveInfinity, float.PositiveInfinity);
            }
            var (sx, tx, dx) = Axis(o.X, d.X, lo.X, ix);
            var (sy, ty, dy) = Axis(o.Y, d.Y, lo.Y, iy);
            var (sz, tz, dz) = Axis(o.Z, d.Z, lo.Z, iz);
            double best = limit;
            while (true)
            {
                int cell = ix + X * (iy + Y * iz);
                for (int k = start[cell]; k < start[cell + 1]; k++)
                {
                    int t = items[k];
                    if (t == self) continue;
                    double hit = Intersect(o, d, tris[t]);
                    if (hit > HitEpsilonMM && hit < best) best = hit;
                }
                float exit = MathF.Min(tx, MathF.Min(ty, tz));
                if (best <= exit || exit > limit) break;
                if (tx <= ty && tx <= tz) { ix += sx; tx += dx; if (ix < 0 || ix >= X) break; }
                else if (ty <= tz) { iy += sy; ty += dy; if (iy < 0 || iy >= Y) break; }
                else { iz += sz; tz += dz; if (iz < 0 || iz >= Z) break; }
            }
            return (float)best;
        }
    }

    /// <summary>Moller-Trumbore in double precision; returns the ray parameter or -1.</summary>
    static double Intersect(Vector3 o, Vector3 d, (Vector3 a, Vector3 b, Vector3 c) t)
    {
        double e1x = t.b.X - t.a.X, e1y = t.b.Y - t.a.Y, e1z = t.b.Z - t.a.Z;
        double e2x = t.c.X - t.a.X, e2y = t.c.Y - t.a.Y, e2z = t.c.Z - t.a.Z;
        double px = d.Y * e2z - d.Z * e2y, py = d.Z * e2x - d.X * e2z, pz = d.X * e2y - d.Y * e2x;
        double det = e1x * px + e1y * py + e1z * pz;
        if (Math.Abs(det) < 1e-18) return -1;
        double inv = 1 / det;
        double sx = o.X - t.a.X, sy = o.Y - t.a.Y, sz = o.Z - t.a.Z;
        double u = (sx * px + sy * py + sz * pz) * inv;
        if (u < 0 || u > 1) return -1;
        double qx = sy * e1z - sz * e1y, qy = sz * e1x - sx * e1z, qz = sx * e1y - sy * e1x;
        double v = (d.X * qx + d.Y * qy + d.Z * qz) * inv;
        if (v < 0 || u + v > 1) return -1;
        return (e2x * qx + e2y * qy + e2z * qz) * inv;
    }

    /// <summary>Area-weighted percentiles and the area share below the minimum wall.</summary>
    public static void Summarise(float[] thickness, double[] areas, float minWall, float cap, IDictionary<string, object> result)
    {
        int[] order = Enumerable.Range(0, thickness.Length).Where(i => !float.IsNaN(thickness[i]) && areas[i] > 0)
                                .OrderBy(i => thickness[i]).ToArray();
        double total = order.Sum(i => areas[i]);
        double Percentile(double q)
        {
            double target = q * total, sum = 0;
            foreach (int i in order) { sum += areas[i]; if (sum >= target) return thickness[i]; }
            return cap;
        }
        double thin = order.Where(i => thickness[i] < minWall).Sum(i => areas[i]);
        result["wall_thickness_cap_mm"] = cap;
        result["wall_thickness_p01_mm"] = total > 0 ? Math.Round(Percentile(0.01), 4) : 0;
        result["wall_thickness_p05_mm"] = total > 0 ? Math.Round(Percentile(0.05), 4) : 0;
        result["thin_wall_area_fraction"] = total > 0 ? Math.Round(thin / total, 5) : 1;
    }

    /// <summary>
    /// Needle or cap triangles: distinct vertices but a height below 1e-3 of
    /// the longest edge. They survive vertex welding and make normals,
    /// overhang and thickness measurements unreliable.
    /// </summary>
    public static int Needles((Vector3 a, Vector3 b, Vector3 c)[] tris)
    {
        int count = 0;
        foreach (var (a, b, c) in tris)
        {
            float l = MathF.Max((b - a).LengthSquared(), MathF.Max((c - b).LengthSquared(), (a - c).LengthSquared()));
            if (l <= 0) continue;
            float twiceArea = Vector3.Cross(b - a, c - a).Length();
            if (twiceArea / l < 1e-3f) count++;
        }
        return count;
    }

    /// <summary>Per-triangle dump for figures: int32 count, then 9 vertex floats and the thickness.</summary>
    public static void Dump(string path, (Vector3 a, Vector3 b, Vector3 c)[] tris, float[] thickness)
    {
        using var w = new BinaryWriter(File.Create(path));
        w.Write(tris.Length);
        for (int i = 0; i < tris.Length; i++)
        {
            foreach (Vector3 v in new[] { tris[i].a, tris[i].b, tris[i].c }) { w.Write(v.X); w.Write(v.Y); w.Write(v.Z); }
            w.Write(thickness[i]);
        }
    }

    // Closed axis-aligned box as 12 outward-wound triangles.
    static (Vector3, Vector3, Vector3)[] Box(Vector3 size)
    {
        Vector3 P(int i) => new((i & 1) * size.X, ((i >> 1) & 1) * size.Y, ((i >> 2) & 1) * size.Z);
        int[][] quads = { new[] { 0, 2, 3, 1 }, new[] { 4, 5, 7, 6 }, new[] { 0, 1, 5, 4 }, new[] { 2, 6, 7, 3 }, new[] { 0, 4, 6, 2 }, new[] { 1, 3, 7, 5 } };
        return quads.SelectMany(q => new[] { (P(q[0]), P(q[1]), P(q[2])), (P(q[0]), P(q[2]), P(q[3])) }).ToArray();
    }

    /// <summary>Known answers without PicoGK: plates of 0.6 and 2.0 mm, and a needle.</summary>
    public static int SelfTest()
    {
        var report = new SortedDictionary<string, object>();
        bool ok = true;
        foreach (var (name, z, expectThin) in new[] { ("plate_0p6", 0.6f, true), ("plate_2p0", 2.0f, false) })
        {
            var tris = Box(new Vector3(10, 10, z)).Select(t => (t.Item1, t.Item2, t.Item3)).ToArray();
            float sign = 1;
            float[] th = Measure(tris, sign, CapMM(1f), out double[] areas);
            var r = new SortedDictionary<string, object>();
            Summarise(th, areas, 1f, CapMM(1f), r);
            float top = th[2];   // a triangle of the 10 x 10 face measures the plate
            r["top_face_thickness_mm"] = top;
            ok &= Math.Abs(top - z) < 1e-4 && ((double)r["thin_wall_area_fraction"] > 0.5) == expectThin;
            report[name] = r;
        }
        var needle = new[] { (new Vector3(0, 0, 0), new Vector3(1, 0, 0), new Vector3(0.5f, 1e-5f, 0)),
                             (new Vector3(0, 0, 0), new Vector3(1, 0, 0), new Vector3(0.5f, 0.5f, 0)) };
        int needles = Needles(needle);
        report["needles_of_two"] = needles;
        ok &= needles == 1;
        report["passed"] = ok;
        Console.WriteLine(JsonSerializer.Serialize(report));
        return ok ? 0 : 1;
    }
}
