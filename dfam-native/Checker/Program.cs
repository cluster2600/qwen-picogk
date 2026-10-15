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
//   check    OUTPUT.stl FIXTURES.json VOXEL_MM MIN_WALL_MM
CultureInfo.DefaultThreadCurrentCulture = CultureInfo.InvariantCulture;
CultureInfo.CurrentCulture = CultureInfo.InvariantCulture;
if (args.Length == 3 && args[0] == "fixtures")
    return Fixtures.Write(Path.GetFullPath(args[1]), float.Parse(args[2]));
if (args.Length == 5 && args[0] == "check")
    return Checks.Run(args[1], args[2], float.Parse(args[3]), float.Parse(args[4]));
Console.Error.WriteLine("Usage: fixtures NEW_DIR VOXEL_MM | check OUTPUT.stl FIXTURES.json VOXEL_MM MIN_WALL_MM");
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

    public static int Run(string stl, string fixturesJson, float voxel, float minWall)
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
