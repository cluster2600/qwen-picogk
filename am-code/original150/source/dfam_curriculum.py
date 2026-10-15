"""Thirty bounded DfAM tutorials using verified PicoGK Boolean operations."""

from textwrap import dedent


CONE = dedent(r"""
// Cone sides exceed the chosen angle only when rise/radius exceeds tan(angle).
// This is a sign-correct distance-like cone field, approximate near its floor rim.
// Cloots et al. 2013: https://utw10945.utweb.utexas.edu/Manuscripts/2013/2013-50-Cloots.pdf
sealed class RisingConeVoid : IImplicit
{
    private readonly Vector3 origin;
    private readonly float radius, slope, normalization;
    public RisingConeVoid(Vector3 floorCenter, float baseRadius, float rise)
    {
        if (!float.IsFinite(baseRadius) || !float.IsFinite(rise) || baseRadius <= 0 || rise <= 0)
            throw new ArgumentOutOfRangeException(nameof(rise));
        origin = floorCenter; radius = baseRadius; slope = baseRadius / rise;
        normalization = MathF.Sqrt(1 + slope * slope);
    }
    public float fSignedDistance(in Vector3 point)
    {
        Vector3 p = point - origin;
        float radial = MathF.Sqrt(p.X * p.X + p.Y * p.Y);
        float side = (radial - radius + slope * p.Z) / normalization;
        return MathF.Max(side, -p.Z); // No horizontal cap at the apex.
    }
}
""").strip()


VENT = dedent(r"""
// Materialise C465 powder guidance: https://www.materialise.com/en/academy/industrial/design-am/stainless-steel-c465
// shortcut: grid connectivity resolves only features sampled at h, refine and physically validate removal.
static int VentPockets(Library lib, Voxels part, BBox3 bounds, float h)
{
    if (!float.IsFinite(h) || h <= 0) throw new ArgumentOutOfRangeException(nameof(h));
    Vector3 low = bounds.vecMin, high = bounds.vecMax;
    Vector3 origin = new(MathF.Floor(low.X / h) * h - 2 * h,
        MathF.Floor(low.Y / h) * h - 2 * h, MathF.Floor(low.Z / h) * h - 2 * h);
    int nx = checked((int)MathF.Ceiling((high.X - origin.X) / h) + 3);
    int ny = checked((int)MathF.Ceiling((high.Y - origin.Y) / h) + 3);
    int nz = checked((int)MathF.Ceiling((high.Z - origin.Z) / h) + 3);
    long count = checked((long)nx * ny * nz);
    if (nx < 3 || ny < 3 || nz < 3 || count > 1_000_000)
        throw new InvalidDataException("Void grid is invalid or exceeds one million samples.");
    int total = checked((int)count), plane = checked(nx * ny);
    byte[] state = new byte[total]; // 0 unknown void, 1 solid, 2 exterior, 3 enclosed visited.
    Queue<int> queue = new();
    Vector3 Point(int id)
    {
        int z = id / plane, y = id / nx % ny, x = id % nx;
        return origin + h * new Vector3(x, y, z);
    }
    void Push(int id, byte marker)
    {
        if (state[id] != 0) return;
        state[id] = marker; queue.Enqueue(id);
    }
    void Expand(int id, byte marker)
    {
        int z = id / plane, y = id / nx % ny, x = id % nx;
        if (x > 0) Push(id - 1, marker);
        if (x + 1 < nx) Push(id + 1, marker);
        if (y > 0) Push(id - nx, marker);
        if (y + 1 < ny) Push(id + nx, marker);
        if (z > 0) Push(id - plane, marker);
        if (z + 1 < nz) Push(id + plane, marker);
    }
    for (int id = 0; id < total; id++)
        state[id] = part.bIsInside(Point(id)) ? (byte)1 : (byte)0;
    // Flood all box faces so exterior air is never mistaken for a powder chamber.
    for (int id = 0; id < total; id++)
    {
        int z = id / plane, y = id / nx % ny, x = id % nx;
        if (x == 0 || x == nx - 1 || y == 0 || y == ny - 1 || z == 0 || z == nz - 1)
            Push(id, 2);
    }
    while (queue.TryDequeue(out int exterior)) Expand(exterior, 2);
    List<Vector3> sampledLowPoints = new();
    for (int seed = 0; seed < total; seed++)
    {
        if (state[seed] != 0) continue;
        Vector3 lowest = Point(seed);
        Push(seed, 3);
        while (queue.TryDequeue(out int id))
        {
            Vector3 p = Point(id);
            if (p.Z < lowest.Z) lowest = p; // Gravity in the declared removal pose is -Z.
            Expand(id, 3);
        }
        sampledLowPoints.Add(lowest);
    }
    if (sampledLowPoints.Count == 0) return 0;
    using Lattice drains = new(lib);
    foreach (Vector3 p in sampledLowPoints)
        drains.AddBeam(new Vector3(p.X, p.Y, origin.Z - h), 1.5f,
            p + Vector3.UnitZ * h, 1.5f, false);
    using Voxels cutters = new(drains);
    part.BoolSubtract(cutters);
    // Check grid samples through the actual chamber point, not the cutter's end-cap plane.
    foreach (Vector3 p in sampledLowPoints)
    {
        int endLayer = checked((int)MathF.Round((p.Z - origin.Z) / h));
        for (int layer = 0; layer <= endLayer; layer++)
        {
            Vector3 q = new(p.X, p.Y, origin.Z + layer * h);
            if (part.bIsInside(q))
                throw new InvalidOperationException($"Powder drain blocked at {q}; chamber sample {p}.");
        }
    }
    Console.WriteLine($"Cut {sampledLowPoints.Count} sampled component drains; gravity -Z, sample pitch {h} mm.");
    return sampledLowPoints.Count;
}
""").strip()


def examples():
    rows = []

    def add(title, task, explanation, body, helpers="", load_mode="mesh"):
        rows.append({
            "id": 106 + len(rows), "category": "dfam", "title": title,
            "task": task, "explanation": explanation,
            "load_mode": load_mode, "body": dedent(body).strip(), "helpers": helpers,
        })

    add(
        "Pointed conical chamber with one build-down drain",
        "Hollow an 8 mm or larger scan coupon with one pointed conical void whose roof is at least 55 degrees to the build platform. Keep 1 mm nominal walls, cut a 3 mm vertical low-point powder port and preserve the scan exterior. Use +Z for building and -Z for the specified evacuation pose.",
        "The cone uses a pointed apex rather than a flat internal roof. Its height/radius ratio controls the analytical roof angle, and the cutter is clipped to an eroded scan so the nominal wall allowance stays explicit. The drain deliberately breaches that allowance. Cloots, Spierings and Wegener (2013, https://utw10945.utweb.utexas.edu/Manuscripts/2013/2013-50-Cloots.pdf) motivate process-dependent support minimization; a final mesh screen remains necessary. The 3 mm opening is a tutorial choice informed by Materialise C465 guidance (https://www.materialise.com/en/academy/industrial/design-am/stainless-steel-c465), not a universal depowdering proof.",
        r"""
        using Voxels part = new(scan);
        Vector3 size = hi - lo, c = (lo + hi) * 0.5f;
        float radius = 1.6f, rise = 3.5f;
        if (size.X < 6f || size.Y < 6f || size.Z < rise + 2 * minWall)
            throw new InvalidDataException("Scan is too small for the cone and wall allowance.");
        if (MathF.Atan(rise / radius) * 180 / MathF.PI <= 55f)
            throw new InvalidOperationException("Cone roof angle failed.");
        Vector3 floor = new(c.X, c.Y, lo.Z + minWall);
        using Voxels allowed = new(scan);
        allowed.Offset(-minWall); // Nominal shell allowance in millimetres.
        using Voxels cavity = Render(lib, new RisingConeVoid(floor, radius, rise), bounds);
        cavity.BoolIntersect(allowed);
        part.BoolSubtract(cavity);
        using Lattice drain = new(lib);
        drain.AddBeam(new Vector3(c.X, c.Y, lo.Z - 2 * h), 1.5f,
            floor + Vector3.UnitZ * h, 1.5f, false);
        using Voxels drainVoxels = new(drain);
        part.BoolSubtract(drainVoxels); // Materialise C465: a 3 mm opening is service-specific.
        """, CONE,
    )
    add(
        "Conical chamber preserves a measured central attachment axis",
        "Create an off-axis pointed conical cavity and a 3 mm low-point drain in a scan coupon. Reserve the centerline for a solid attachment land. Place the cavity using a declared coupon datum, require a 55 degree roof, and distinguish this coupon datum from a measured vehicle interface.",
        "An off-axis cone leaves the center of the scan solid for later interface work. The centerline is a coupon design datum, not a recovered mating measurement. The normalized cone-side field has the correct sign; its floor-rim distance remains approximate before voxelization. Cloots et al. (2013, https://utw10945.utweb.utexas.edu/Manuscripts/2013/2013-50-Cloots.pdf) support considering heat paths as well as angles. The final wall and void screens must include the offset cavity and drain.",
        r"""
        using Voxels part = new(scan);
        Vector3 size = hi - lo, c = (lo + hi) * 0.5f;
        float radius = 1.5f, rise = 3.4f;
        if (size.X < 7f || size.Y < 6f || size.Z < 6f)
            throw new InvalidDataException("Off-axis cone does not fit this scan envelope.");
        Vector3 floor = new(c.X - 2.4f, c.Y, lo.Z + minWall);
        float roofAngle = MathF.Atan(rise / radius) * 180 / MathF.PI;
        if (roofAngle <= 55f) throw new InvalidOperationException("Roof angle is too low.");
        using Voxels allowed = new(scan);
        allowed.Offset(-minWall);
        using Voxels cavity = Render(lib, new RisingConeVoid(floor, radius, rise), bounds);
        cavity.BoolIntersect(allowed);
        // A protected cylinder keeps the nominal center attachment axis fully solid.
        using Lattice reserved = new(lib);
        reserved.AddBeam(new Vector3(c.X, c.Y, lo.Z - h), 0.6f,
            new Vector3(c.X, c.Y, hi.Z + h), 0.6f, false);
        using Voxels reserveVoxels = new(reserved);
        cavity.BoolSubtract(reserveVoxels);
        part.BoolSubtract(cavity);
        using Lattice port = new(lib);
        port.AddBeam(floor - Vector3.UnitZ * (minWall + 2 * h), 1.5f,
            floor + Vector3.UnitZ * h, 1.5f, false);
        using Voxels portVoxels = new(port);
        part.BoolSubtract(portVoxels);
        """, CONE,
    )
    add(
        "Two pointed chambers receive independent powder ports",
        "Generate two small pointed conical chambers in a scan at least 8 mm wide. Give each its own 3 mm bottom port and leave a solid central web. Avoid assuming that one vent reaches two disconnected chambers.",
        "Each independently created chamber gets an independently cut exterior port. A minimum-height check keeps the analytic cone roof above 55 degrees; the final Boolean shape still requires screening because clipping against the scan can introduce new roofs. Materialise C465 powder-removal guidance (https://www.materialise.com/en/academy/industrial/design-am/stainless-steel-c465) motivates multiple openings for complex cavities, and Cloots et al. (2013, https://utw10945.utweb.utexas.edu/Manuscripts/2013/2013-50-Cloots.pdf) show that support decisions remain process-dependent.",
        r"""
        using Voxels part = new(scan);
        Vector3 size = hi - lo, c = (lo + hi) * 0.5f;
        if (size.X < 7.8f || size.Y < 6f || size.Z < 6f)
            throw new InvalidDataException("Two chambers require a wider coupon.");
        using Voxels allowed = new(scan);
        allowed.Offset(-minWall);
        float radius = 1.5f, rise = 3.2f;
        if (MathF.Atan(rise / radius) * 180 / MathF.PI <= 55f)
            throw new InvalidOperationException("Roof angle failed.");
        foreach (float x in new[] { lo.X + 2.1f, hi.X - 2.1f })
        {
            Vector3 floor = new(x, c.Y, lo.Z + minWall);
            using Voxels cavity = Render(lib, new RisingConeVoid(floor, radius, rise), bounds);
            cavity.BoolIntersect(allowed);
            part.BoolSubtract(cavity);
            using Lattice drain = new(lib);
            drain.AddBeam(new Vector3(x, c.Y, lo.Z - 2 * h), 1.5f,
                floor + Vector3.UnitZ * h, 1.5f, false);
            using Voxels drainVoxels = new(drain);
            part.BoolSubtract(drainVoxels);
        }
        """, CONE,
    )

    add(
        "A 55 degree roof channel replaces a circular horizontal bore",
        "Create an open-through channel along Y in a scanned coupon using a vertical-walled cross section with a pointed 55 degree roof. Make its clear width 3 mm, extend the cutter through both faces, preserve the external scan, and screen the voxelized roof.",
        "A horizontal circular bore has a shallow down-facing ceiling near its crown. A pointed roof provides two declared 55 degree roof planes before voxelization. The cutter extends outside both Y faces, so its end caps cannot close the channel. Cloots et al. (2013, https://utw10945.utweb.utexas.edu/Manuscripts/2013/2013-50-Cloots.pdf) motivate support minimization, but the angle is a configured screen rather than a transferable process qualification.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        if (hi.X - lo.X < 6f || hi.Z - lo.Z < 6f)
            throw new InvalidDataException("Roof channel and wall allowance do not fit.");
        float halfWidth = 1.5f;
        Vector3 a = new(c.X - halfWidth, lo.Y - 2 * h, lo.Z + minWall);
        Vector3 b = new(c.X + halfWidth, hi.Y + 2 * h, lo.Z + 4.8f);
        // RoofVoid has two roof planes at 55 degrees and vertical side walls.
        using Voxels channel = Render(lib, new RoofVoid(a, b),
            new BBox3(a - Vector3.One * h, b + Vector3.One * h));
        part.BoolSubtract(channel);
        """,
    )
    add(
        "A low roof channel slopes its floor toward an evacuation face",
        "Add a through-Y 55 degree roof channel and a second lower roof channel near the -Y face to expose the lowest chamber floor. Keep 3 mm clear widths. Explain why connecting cutters geometrically does not prove powder flow.",
        "The second channel lowers the accessible floor near the chosen evacuation face while retaining a pointed roof. The overlapping cutters establish a designed geometric route, subject to the final void-connectivity screen. Materialise powder-removal guidance (https://www.materialise.com/en/academy/industrial/design-am/stainless-steel-c465) warns about powder traps and long complex channels. No numerical void test establishes complete physical evacuation.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        if (hi.Z - lo.Z < 6f || hi.X - lo.X < 6f)
            throw new InvalidDataException("Insufficient room for the two-level channel.");
        Vector3 a = new(c.X - 1.5f, lo.Y - 2 * h, lo.Z + 1.4f);
        Vector3 b = new(c.X + 1.5f, hi.Y + 2 * h, lo.Z + 5f);
        using Voxels channel = Render(lib, new RoofVoid(a, b), new BBox3(a - Vector3.One, b + Vector3.One));
        Vector3 drainLo = new(a.X, lo.Y - 2 * h, lo.Z + minWall);
        Vector3 drainHi = new(b.X, lo.Y + 2.4f, lo.Z + 4.6f);
        using Voxels floorOutlet = Render(lib, new RoofVoid(drainLo, drainHi),
            new BBox3(drainLo - Vector3.One, drainHi + Vector3.One));
        channel.BoolAdd(floorOutlet); // Union the routes before cutting the scan.
        part.BoolSubtract(channel);
        """,
    )
    add(
        "Independent parallel roof channels avoid a shared sealed plenum",
        "Create two parallel Y-directed powder channels with 55 degree roofs, each exposed at both Y ends. Preserve a central solid web of at least 1 mm. Use 2 mm channel widths for this small coupon and explicitly reject treating that tutorial width as qualified powder clearance.",
        "Independent through channels avoid adding a horizontal shared-plenum roof. Their centers and widths preserve a nominal 1 mm web. The 2 mm width is an intentionally constrained tutorial: Materialise C465 powder-removal guidance (https://www.materialise.com/en/academy/industrial/design-am/stainless-steel-c465) recommends larger removal openings, so this candidate needs service review or enlargement before manufacture. The final clear-throat check must report that distinction.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        if (hi.X - lo.X < 7f || hi.Z - lo.Z < 5.5f)
            throw new InvalidDataException("Parallel channels require a wider coupon.");
        float halfWidth = 1f, centerSeparation = 3.2f;
        if (centerSeparation - 2 * halfWidth < minWall)
            throw new InvalidOperationException("Central web would be too thin.");
        foreach (float x in new[] { c.X - centerSeparation / 2, c.X + centerSeparation / 2 })
        {
            Vector3 a = new(x - halfWidth, lo.Y - 2 * h, lo.Z + minWall);
            Vector3 b = new(x + halfWidth, hi.Y + 2 * h, lo.Z + 4.2f);
            using Voxels route = Render(lib, new RoofVoid(a, b), new BBox3(a - Vector3.One, b + Vector3.One));
            part.BoolSubtract(route);
        }
        Console.WriteLine("Designed channels are 2 mm wide; powder-service clearance remains unqualified.");
        """,
    )

    add(
        "One bottom drain opens a scan-following hollow",
        "Hollow a scanned coupon using a 1 mm inward offset, then cut a 3 mm cylindrical powder outlet through the lowest -Z wall. Explain that the inherited cavity roof may still need support and must be retained as rejected when the screen fails.",
        "An inward offset gives a scan-following cavity without claiming that its inherited roof is self-supporting. The low-point port crosses the bottom skin and enters the eroded cavity. Materialise C465 guidance (https://www.materialise.com/en/academy/industrial/design-am/stainless-steel-c465) motivates accessible powder removal; Cloots et al. (2013, https://utw10945.utweb.utexas.edu/Manuscripts/2013/2013-50-Cloots.pdf) require process-aware support decisions. An inherited horizontal ceiling must fail the final overhang screen rather than acquire a false support-free label.",
        r"""
        using Voxels part = new(scan);
        using Voxels cavity = new(scan);
        cavity.Offset(-minWall);
        part.BoolSubtract(cavity);
        Vector3 c = (lo + hi) * 0.5f;
        if (hi.Z - lo.Z <= 2 * minWall + 1f)
            throw new InvalidDataException("No room for a drained hollow.");
        using Lattice drain = new(lib);
        drain.AddBeam(new Vector3(c.X, c.Y, lo.Z - 2 * h), 1.5f,
            new Vector3(c.X, c.Y, lo.Z + minWall + 2 * h), 1.5f, false);
        using Voxels cutter = new(drain);
        part.BoolSubtract(cutter);
        // The downstream angle screen must reject any inherited down-facing roof.
        """,
    )
    add(
        "A rotated evacuation pose uses the X-lowest outlet",
        "Design a scan-following hollow for evacuation after the part is rotated so gravity points along -X. Use a pointed 55 degree roof port extended along Y at the X-low edge; state the evacuation pose separately from the +Z build direction.",
        "Build direction and handling gravity are separate vectors. This example places an open roof outlet near the low-X cavity edge so the coupon can be tipped toward it. It does not call the build-lowest coordinate a universal drainage datum. Materialise powder-removal guidance (https://www.materialise.com/en/academy/industrial/design-am/stainless-steel-c465) motivates avoiding traps; a pose-aware removal trial is still required.",
        r"""
        using Voxels part = new(scan);
        using Voxels cavity = new(scan);
        cavity.Offset(-minWall);
        part.BoolSubtract(cavity);
        if (hi.X - lo.X < 6f || hi.Z - lo.Z < 6f)
            throw new InvalidDataException("Outlet cannot fit the declared evacuation pose.");
        Vector3 gravityDuringRemoval = -Vector3.UnitX;
        Vector3 a = new(lo.X + 0.8f, lo.Y - 2 * h, lo.Z + minWall);
        Vector3 b = new(lo.X + 3.8f, hi.Y + 2 * h, lo.Z + 4.8f);
        using Voxels outlet = Render(lib, new RoofVoid(a, b), new BBox3(a - Vector3.One, b + Vector3.One));
        part.BoolSubtract(outlet);
        Console.WriteLine($"Evacuation gravity: {gravityDuringRemoval}; build remains +Z.");
        """,
    )
    add(
        "Bottom drain and upper purge port provide two accessible routes",
        "Hollow a scan with 1 mm nominal skin and add a bottom 3 mm drain plus a top 3 mm purge opening. Connect both into the same cavity, keep the scan exterior elsewhere, and distinguish purge access from evidence of powder removal.",
        "The bottom opening gives gravity access and the top opening allows a second accessible path for the specified purge or handling procedure. Cutter endpoints overlap the eroded cavity and extend outside the exterior. Multiple openings follow the concern expressed in Materialise C465 guidance (https://www.materialise.com/en/academy/industrial/design-am/stainless-steel-c465); physical evacuation remains unproven and inherited roofs remain subject to rejection.",
        r"""
        using Voxels part = new(scan);
        using Voxels cavity = new(scan);
        cavity.Offset(-minWall);
        part.BoolSubtract(cavity);
        Vector3 c = (lo + hi) * 0.5f;
        if (hi.Z - lo.Z < 5f) throw new InvalidDataException("Two ports cannot reach a useful cavity.");
        using Lattice openings = new(lib);
        openings.AddBeam(new Vector3(c.X, c.Y, lo.Z - 2 * h), 1.5f,
            new Vector3(c.X, c.Y, lo.Z + minWall + 2 * h), 1.5f, false);
        openings.AddBeam(new Vector3(c.X, c.Y, hi.Z - minWall - 2 * h), 1.5f,
            new Vector3(c.X, c.Y, hi.Z + 2 * h), 1.5f, false);
        using Voxels openingVoxels = new(openings);
        part.BoolSubtract(openingVoxels);
        """,
    )

    add(
        "Separated roof chambers each expose a drain",
        "Cut two separated chambers with pointed 55 degree roofs into a scan coupon and drill an independent 3 mm bottom port for each. Preserve a central web and avoid connecting the two roofs with an unsupported horizontal plenum.",
        "A separate port for each chamber prevents relying on nonexistent communication through the central web. Chamber clipping preserves the nominal external skin, while ports intentionally breach it. Materialise guidance (https://www.materialise.com/en/academy/industrial/design-am/stainless-steel-c465) supports multiple accessible powder openings for complex cavities; the final flood screen must inspect the actual Boolean result.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        if (hi.X - lo.X < 7.8f || hi.Z - lo.Z < 6f)
            throw new InvalidDataException("Separated chambers do not fit.");
        using Voxels allowed = new(scan);
        allowed.Offset(-minWall);
        foreach (float x in new[] { lo.X + 2.1f, hi.X - 2.1f })
        {
            Vector3 a = new(x - 1.5f, lo.Y + minWall, lo.Z + minWall);
            Vector3 b = new(x + 1.5f, hi.Y - minWall, lo.Z + 4.8f);
            using Voxels chamber = Render(lib, new RoofVoid(a, b), bounds);
            chamber.BoolIntersect(allowed);
            part.BoolSubtract(chamber);
            using Lattice drain = new(lib);
            drain.AddBeam(new Vector3(x, c.Y, lo.Z - 2 * h), 1.5f,
                new Vector3(x, c.Y, lo.Z + minWall + h), 1.5f, false);
            using Voxels port = new(drain);
            part.BoolSubtract(port);
        }
        """,
    )
    add(
        "Fore and aft sealed chambers receive their own low-point ports",
        "Partition the scan cavity into fore and aft chambers separated by a 1.2 mm Y web. Use pointed roofs and independent bottom vents. Verify that port count is associated with chamber locations rather than guessed from one global bounding box.",
        "The fore/aft construction makes the protected Y web explicit and maps one drain center to each chamber. This teaches location-aware venting without pretending that two exterior holes prove every void is connected. Materialise powder-removal guidance (https://www.materialise.com/en/academy/industrial/design-am/stainless-steel-c465) motivates access and avoids powder traps; final topology may still differ after intersection with a real scan.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        if (hi.Y - lo.Y < 7.8f || hi.X - lo.X < 6f || hi.Z - lo.Z < 6f)
            throw new InvalidDataException("Fore/aft chambers require an 8 mm coupon.");
        using Voxels allowed = new(scan);
        allowed.Offset(-minWall);
        foreach ((float y0, float y1) in new[] { (lo.Y + minWall, c.Y - 0.6f), (c.Y + 0.6f, hi.Y - minWall) })
        {
            Vector3 a = new(c.X - 1.5f, y0, lo.Z + minWall);
            Vector3 b = new(c.X + 1.5f, y1, lo.Z + 4.8f);
            using Voxels chamber = Render(lib, new RoofVoid(a, b), bounds);
            chamber.BoolIntersect(allowed);
            part.BoolSubtract(chamber);
            using Lattice drain = new(lib);
            float y = (y0 + y1) * 0.5f;
            drain.AddBeam(new Vector3(c.X, y, lo.Z - 2 * h), 1.5f,
                new Vector3(c.X, y, lo.Z + minWall + h), 1.5f, false);
            using Voxels port = new(drain);
            part.BoolSubtract(port);
        }
        """,
    )
    add(
        "Long chamber gets accessible ports at both gravitational ends",
        "Create one elongated pointed-roof chamber inside a scan coupon and two bottom vents near its Y ends. Keep the chamber itself connected and leave the central section free of unnecessary perforations.",
        "End ports provide two accessible locations for an elongated connected chamber. The code maintains a single cavity field and adds two cutters, preserving the middle skin. Materialise C465 guidance (https://www.materialise.com/en/academy/industrial/design-am/stainless-steel-c465) advises larger or multiple access points for complex spaces; no assumed port diameter establishes reliable removal from long channels.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        if (hi.Y - lo.Y < 7.8f || hi.Z - lo.Z < 6f || hi.X - lo.X < 6f)
            throw new InvalidDataException("The elongated vented chamber does not fit.");
        using Voxels allowed = new(scan);
        allowed.Offset(-minWall);
        Vector3 a = new(c.X - 1.5f, lo.Y + minWall, lo.Z + minWall);
        Vector3 b = new(c.X + 1.5f, hi.Y - minWall, lo.Z + 4.8f);
        using Voxels chamber = Render(lib, new RoofVoid(a, b), bounds);
        chamber.BoolIntersect(allowed);
        part.BoolSubtract(chamber);
        using Lattice vents = new(lib);
        foreach (float y in new[] { lo.Y + 2.1f, hi.Y - 2.1f })
            vents.AddBeam(new Vector3(c.X, y, lo.Z - 2 * h), 1.5f,
                new Vector3(c.X, y, lo.Z + minWall + h), 1.5f, false);
        using Voxels ports = new(vents);
        part.BoolSubtract(ports);
        """,
    )

    add(
        "A protected build-down attachment foot stays solid",
        "Add a solid 2 mm thick attachment foot at the build-lowest face of a scan coupon, then hollow the scan while protecting the entire foot. Treat its size as a tutorial datum rather than an inferred vehicle attachment interface.",
        "The union creates an anchored attachment foot, then subtracting that same foot from the cavity cutter prevents accidental hollowing of the load-entry region. Dimensions are declared coupon dimensions rather than recovered scan-interface evidence. Sigmund (1994, https://doi.org/10.1016/0020-7683(94)90154-6) motivates preserving stiffness/load paths, but this Boolean operation does not optimize or validate strength. Mercelis and Kruth (2006, https://doi.org/10.1108/13552540610707013) explain why attachment and heat paths matter to residual stress without establishing this foot as sufficient.",
        r"""
        using Voxels part = new(scan);
        Vector3 a = new(lo.X - 1f, lo.Y - 1f, lo.Z);
        Vector3 b = new(hi.X + 1f, hi.Y + 1f, lo.Z + 2f);
        using Voxels foot = Render(lib, new Box(a, b), new BBox3(a - Vector3.One, b + Vector3.One));
        part.BoolAdd(foot);
        using Voxels cavity = new(scan);
        cavity.Offset(-minWall);
        cavity.BoolSubtract(foot); // Keep the complete declared attachment region solid.
        part.BoolSubtract(cavity);
        """,
    )
    add(
        "Opposed full-height attachment lands survive hollowing",
        "Add two full-height solid attachment lands on opposed X sides of a scan coupon. Hollow the scan with a 1 mm shell while reserving the lands. Require future loads and mating datums before calling the lands functional.",
        "Opposed lands extend to the build-lowest face and are protected from the cavity subtraction. Full-height columns avoid introducing a floating horizontal flange in this coupon. They establish geometry for later measured interfaces, not strength or fitment. Sigmund's inverse-homogenization work (1994, https://doi.org/10.1016/0020-7683(94)90154-6) supports considering mechanical objectives; no such objective is solved here.",
        r"""
        using Voxels part = new(scan);
        using Voxels protectedLands = new(lib);
        foreach (bool right in new[] { false, true })
        {
            Vector3 a = new(right ? hi.X - 0.8f : lo.X - 1f, lo.Y + 1f, lo.Z);
            Vector3 b = new(right ? hi.X + 1f : lo.X + 0.8f, hi.Y - 1f, hi.Z);
            using Voxels land = Render(lib, new Box(a, b), new BBox3(a - Vector3.One, b + Vector3.One));
            protectedLands.BoolAdd(land);
        }
        part.BoolAdd(protectedLands);
        using Voxels cavity = new(scan);
        cavity.Offset(-minWall);
        cavity.BoolSubtract(protectedLands);
        part.BoolSubtract(cavity);
        """,
    )
    add(
        "Vertical cylindrical attachment collar remains solid",
        "Create a solid cylindrical attachment collar on a scan centerline and hollow the surrounding scan while preserving the collar. Use a flat-ended, vertical Lattice beam and keep the collar diameter distinct from a hole diameter.",
        "A vertical flat-ended beam defines a solid collar, and excluding it from the cavity cutter preserves its cross section. PicoGK Lattice radii are half the declared diameter. The datum is the coupon center rather than a scanned vehicle interface. Sigmund (1994, https://doi.org/10.1016/0020-7683(94)90154-6) is a conceptual mechanical-design reference; this reserved region is not an FE-optimized load path.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        float collarDiameter = 3f;
        using Lattice collarLattice = new(lib);
        collarLattice.AddBeam(new Vector3(c.X, c.Y, lo.Z), collarDiameter / 2,
            new Vector3(c.X, c.Y, hi.Z + 1f), collarDiameter / 2, false);
        using Voxels collar = new(collarLattice);
        part.BoolAdd(collar);
        using Voxels cavity = new(scan);
        cavity.Offset(-minWall);
        cavity.BoolSubtract(collar);
        part.BoolSubtract(cavity);
        """,
    )

    add(
        "Attachment union precedes the through-hole subtraction",
        "Add a solid build-down foot and a vertical 3 mm through hole to a scanned coupon. Ensure the foot union cannot refill the hole. Use explicit Boolean order and flat-ended Lattice cutters extended beyond all material.",
        "The foot is united first and the through cutter is subtracted last, so the later union cannot heal the hole. Cutter endpoints exceed both final material faces. These coupon dimensions are declared, not scan-derived fitment evidence. Mercelis and Kruth (2006, https://doi.org/10.1108/13552540610707013) motivate maintaining build attachment and heat paths, but this foot is not a validated stress-control solution.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        Vector3 a = new(lo.X - 1f, lo.Y - 1f, lo.Z);
        Vector3 b = new(hi.X + 1f, hi.Y + 1f, lo.Z + 2f);
        using Voxels foot = Render(lib, new Box(a, b), new BBox3(a - Vector3.One, b + Vector3.One));
        part.BoolAdd(foot);
        using Lattice bore = new(lib);
        bore.AddBeam(new Vector3(c.X, c.Y, lo.Z - 2 * h), 1.5f,
            new Vector3(c.X, c.Y, hi.Z + 2 * h), 1.5f, false);
        using Voxels hole = new(bore);
        part.BoolSubtract(hole); // Last subtraction preserves the aperture through the union.
        """,
    )
    add(
        "Protected boss is hollowed before the finish hole is drilled",
        "Create a vertical cylindrical solid boss in an oriented-point reconstructed coupon. Hollow the scan while protecting the boss, then drill a 3 mm vertical hole through both the boss and scan. Leave at least 1 mm radial boss stock.",
        "The boss diameter is hole diameter plus twice the nominal wall allowance. It is excluded from the hollowing cutter, and drilling occurs after all unions. This preserves the reserved load-entry region geometrically while leaving strength and mating tolerances unknown. Sigmund (1994, https://doi.org/10.1016/0020-7683(94)90154-6) supplies a structural-optimization foundation, not a claim that this simple boss is optimized.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        float holeRadius = 1.5f, bossRadius = holeRadius + minWall + h;
        if (2 * bossRadius > MathF.Min(hi.X - lo.X, hi.Y - lo.Y))
            throw new InvalidDataException("Boss radial allowance does not fit the coupon.");
        using Lattice bossLattice = new(lib);
        bossLattice.AddBeam(new Vector3(c.X, c.Y, lo.Z), bossRadius,
            new Vector3(c.X, c.Y, hi.Z + 1f), bossRadius, false);
        using Voxels boss = new(bossLattice);
        part.BoolAdd(boss);
        using Voxels cavity = new(scan);
        cavity.Offset(-minWall);
        cavity.BoolSubtract(boss);
        part.BoolSubtract(cavity);
        using Lattice drilling = new(lib);
        drilling.AddBeam(new Vector3(c.X, c.Y, lo.Z - 2 * h), holeRadius,
            new Vector3(c.X, c.Y, hi.Z + 1f + 2 * h), holeRadius, false);
        using Voxels throughHole = new(drilling);
        part.BoolSubtract(throughHole);
        """, load_mode="oriented",
    )
    add(
        "Two flange apertures stay open after adding machining stock",
        "Add a build-down flange with 0.4 mm local machining stock, then drill two 3 mm vertical holes. Extend both cutters through the added stock and check nominal edge distances and the web between holes before constructing them.",
        "Holes are drilled after stock is added, and their endpoints include that stock. Edge distances and inter-hole web are checked using the declared flange dimensions. This prevents a concrete Boolean-order error without pretending those checks provide fatigue or bolt-load validation. Mercelis and Kruth (2006, https://doi.org/10.1108/13552540610707013) remain a residual-stress reference; stock and edge-distance rules do not solve their physics.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        float radius = 1.5f, separation = 4.2f, stock = 0.4f;
        Vector3 a = new(lo.X - 1f, lo.Y - 1f, lo.Z);
        Vector3 b = new(hi.X + 1f, hi.Y + 1f, lo.Z + 2f + stock);
        if (separation - 2 * radius < minWall ||
            (b.X - a.X - separation) / 2 - radius < minWall)
            throw new InvalidDataException("Declared flange has insufficient nominal ligaments.");
        using Voxels flange = Render(lib, new Box(a, b), new BBox3(a - Vector3.One, b + Vector3.One));
        part.BoolAdd(flange);
        using Lattice bores = new(lib);
        foreach (float x in new[] { c.X - separation / 2, c.X + separation / 2 })
            bores.AddBeam(new Vector3(x, c.Y, lo.Z - 2 * h), radius,
                new Vector3(x, c.Y, hi.Z + stock + 2 * h), radius, false);
        using Voxels holes = new(bores);
        part.BoolSubtract(holes);
        """,
    )

    add(
        "Uniform machining allowance remains separate from final skin",
        "Produce an as-built shell candidate with 0.4 mm exterior machining stock and a 1 mm nominal finished skin. Keep the interior cutter referenced to the original scan, not the stock-expanded exterior. State that stock is not process compensation.",
        "Expanding the exterior by stock while eroding the original scan by the finished wall allowance makes the bookkeeping explicit. Eroding the expanded exterior by only the finished wall would misplace the inner surface. Neither allowance certifies dimensions after printing or machining. Mercelis and Kruth (2006, https://doi.org/10.1108/13552540610707013) explain why a geometric allowance cannot replace a calibrated distortion prediction.",
        r"""
        float machiningStock = 0.4f;
        if (minWall / h < 5f || machiningStock / h < 2f)
            throw new InvalidOperationException("Allowances are inadequately sampled.");
        using Voxels part = new(scan);
        part.Offset(machiningStock); // As-built exterior stock, not thermal compensation.
        using Voxels interior = new(scan);
        interior.Offset(-minWall); // Keep the inner surface tied to the original datum.
        part.BoolSubtract(interior);
        using Lattice port = new(lib);
        Vector3 c = (lo + hi) * 0.5f;
        port.AddBeam(new Vector3(c.X, c.Y, lo.Z - machiningStock - 2 * h), 1.5f,
            new Vector3(c.X, c.Y, lo.Z + minWall + 2 * h), 1.5f, false);
        using Voxels portVoxels = new(port);
        part.BoolSubtract(portVoxels);
        """,
    )
    add(
        "Local upper-face stock protects the scan datum elsewhere",
        "Add only a 0.4 mm upper-face machining pad to an oriented-point reconstructed scan coupon. Hollow the scan while preserving a 1.4 mm nominal upper skin below the pad. Keep all other exterior faces tied to the reconstruction.",
        "A local pad avoids expanding every measured exterior surface. The protected upper band records a larger nominal allowance beneath the intended finishing face. Scan reconstruction remains uncertain, and a nominal face at the bounding-box maximum is a coupon datum, not a measured mating plane. Curless and Levoy (1996, https://lightfield.stanford.edu/papers/volrange/) provide reconstruction foundations; Mercelis and Kruth (2006, https://doi.org/10.1108/13552540610707013) do not make this pad a distortion model.",
        r"""
        using Voxels part = new(scan);
        float stock = 0.4f, topSkin = minWall + stock;
        Vector3 a = new(lo.X, lo.Y, hi.Z - h);
        Vector3 b = new(hi.X, hi.Y, hi.Z + stock);
        using Voxels pad = Render(lib, new Box(a, b), new BBox3(a - Vector3.One, b + Vector3.One));
        part.BoolAdd(pad);
        Vector3 guardLo = new(lo.X - h, lo.Y - h, hi.Z - topSkin);
        Vector3 guardHi = new(hi.X + h, hi.Y + h, hi.Z + stock + h);
        using Voxels protectedTop = Render(lib, new Box(guardLo, guardHi),
            new BBox3(guardLo - Vector3.One, guardHi + Vector3.One));
        using Voxels cavity = new(scan);
        cavity.Offset(-minWall);
        cavity.BoolSubtract(protectedTop);
        part.BoolSubtract(cavity);
        """, load_mode="oriented",
    )
    add(
        "A pilot bore leaves radial finishing allowance",
        "Create a vertical solid boss and a 3 mm as-built pilot bore for a declared 3.4 mm finished bore. Compute radial machining allowance correctly and preserve at least 1 mm nominal finished ligament around the future final bore.",
        "Diameter stock must be halved to obtain radial stock. The boss radius is based on the future finished radius plus wall allowance, while the as-built cutter uses the pilot radius. This prevents radius/diameter mistakes and retains finishing material. Final machining, process capability and fitment remain unverified; Materialise C465 holes guidance (https://www.materialise.com/en/academy/industrial/design-am/stainless-steel-c465) recommends post-machining where bore tolerances matter.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        float pilotDiameter = 3f, finishedDiameter = 3.4f;
        float radialStock = (finishedDiameter - pilotDiameter) / 2;
        float bossRadius = finishedDiameter / 2 + minWall + h;
        if (radialStock < h || 2 * bossRadius > MathF.Min(hi.X - lo.X, hi.Y - lo.Y))
            throw new InvalidDataException("Pilot stock or boss envelope is inadequate.");
        using Lattice bossLattice = new(lib);
        bossLattice.AddBeam(new Vector3(c.X, c.Y, lo.Z), bossRadius,
            new Vector3(c.X, c.Y, hi.Z + 1f), bossRadius, false);
        using Voxels boss = new(bossLattice);
        part.BoolAdd(boss);
        using Lattice pilot = new(lib);
        pilot.AddBeam(new Vector3(c.X, c.Y, lo.Z - 2 * h), pilotDiameter / 2,
            new Vector3(c.X, c.Y, hi.Z + 1f + 2 * h), pilotDiameter / 2, false);
        using Voxels pilotVoxels = new(pilot);
        part.BoolSubtract(pilotVoxels);
        Console.WriteLine($"Radial finishing stock: {radialStock:F3} mm.");
        """,
    )

    add(
        "A roof opening communicates through a protected structural web",
        "Hollow the scan, preserve a 1.2 mm central Y web, and cut a 3 mm wide pointed-roof communication channel through that web. Expose the route on both Y faces so the web does not create inaccessible chambers.",
        "A protected web preserves nominal material for a future load path, and a late roof cutter gives both sides a designed access route. Boolean order keeps the communication aperture open. Sigmund (1994, https://doi.org/10.1016/0020-7683(94)90154-6) motivates mechanical objectives but does not certify this web; Materialise C465 guidance (https://www.materialise.com/en/academy/industrial/design-am/stainless-steel-c465) motivates connected accessible voids.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        if (hi.X - lo.X < 6f || hi.Z - lo.Z < 6f)
            throw new InvalidDataException("Web opening cannot fit with nominal walls.");
        Vector3 webLo = new(lo.X, c.Y - 0.6f, lo.Z);
        Vector3 webHi = new(hi.X, c.Y + 0.6f, hi.Z);
        using Voxels web = Render(lib, new Box(webLo, webHi), bounds);
        using Voxels cavity = new(scan);
        cavity.Offset(-minWall);
        cavity.BoolSubtract(web);
        part.BoolSubtract(cavity);
        Vector3 a = new(c.X - 1.5f, lo.Y - 2 * h, lo.Z + minWall);
        Vector3 b = new(c.X + 1.5f, hi.Y + 2 * h, lo.Z + 4.8f);
        using Voxels route = Render(lib, new RoofVoid(a, b), new BBox3(a - Vector3.One, b + Vector3.One));
        part.BoolSubtract(route); // Cut communication after preserving the web.
        """,
    )
    add(
        "Offset twin web openings preserve a central ligament",
        "Keep a central Y web inside a hollow scan but provide two 2 mm wide Y-directed roof openings on either side of a 1.2 mm ligament. Expose both routes at the exterior and record that their clearance is below the selected 3 mm powder criterion.",
        "Two channels preserve a central ligament while permitting separate access through the web. The geometry deliberately records its 2 mm aperture as a constrained example, so a service requiring 3 mm clearance must reject or enlarge it. Materialise C465 guidance (https://www.materialise.com/en/academy/industrial/design-am/stainless-steel-c465) is service-specific and does not turn small geometric connectivity into depowdering qualification.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        if (hi.X - lo.X < 7f || hi.Z - lo.Z < 6f)
            throw new InvalidDataException("Twin web openings do not fit.");
        Vector3 webLo = new(lo.X, c.Y - 0.6f, lo.Z);
        Vector3 webHi = new(hi.X, c.Y + 0.6f, hi.Z);
        using Voxels web = Render(lib, new Box(webLo, webHi), bounds);
        using Voxels cavity = new(scan);
        cavity.Offset(-minWall);
        cavity.BoolSubtract(web);
        part.BoolSubtract(cavity);
        foreach (float x in new[] { c.X - 1.6f, c.X + 1.6f })
        {
            Vector3 a = new(x - 1f, lo.Y - 2 * h, lo.Z + minWall);
            Vector3 b = new(x + 1f, hi.Y + 2 * h, lo.Z + 4.2f);
            using Voxels route = Render(lib, new RoofVoid(a, b), new BBox3(a - Vector3.One, b + Vector3.One));
            part.BoolSubtract(route);
        }
        Console.WriteLine("2 mm routes require enlargement for the selected 3 mm powder-clearance criterion.");
        """,
    )
    add(
        "A low roof aperture keeps an upper web strap",
        "Hollow a scan while retaining a central Y web, then cut only a low pointed-roof 3 mm opening through it. Preserve at least 1 mm of web above the channel apex and expose the channel at both Y ends.",
        "An explicit apex-height check reserves the upper web strap. The opening is cut after the protected web is excluded from the hollowing operation, which keeps the nominal strap while enabling an accessible low route. Sigmund (1994, https://doi.org/10.1016/0020-7683(94)90154-6) is a conceptual structural reference; the strap needs actual loads and analysis before functional claims.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        float apexZ = lo.Z + 4.8f;
        if (hi.Z - apexZ < minWall || hi.X - lo.X < 6f)
            throw new InvalidDataException("An upper web strap cannot be retained.");
        Vector3 webLo = new(lo.X, c.Y - 0.6f, lo.Z);
        Vector3 webHi = new(hi.X, c.Y + 0.6f, hi.Z);
        using Voxels web = Render(lib, new Box(webLo, webHi), bounds);
        using Voxels cavity = new(scan);
        cavity.Offset(-minWall);
        cavity.BoolSubtract(web);
        part.BoolSubtract(cavity);
        Vector3 a = new(c.X - 1.5f, lo.Y - 2 * h, lo.Z + minWall);
        Vector3 b = new(c.X + 1.5f, hi.Y + 2 * h, apexZ);
        using Voxels opening = Render(lib, new RoofVoid(a, b), new BBox3(a - Vector3.One, b + Vector3.One));
        part.BoolSubtract(opening);
        """,
    )

    add(
        "A rising tapered buttress avoids a floating attachment tab",
        "Add a tapered vertical buttress to one side of a scan coupon. Start it at the build-lowest face, narrow its radius as Z rises, and intersect it substantially with the scan. Check that side slope exceeds 55 degrees while preserving final-screen rejection at junctions.",
        "A buttress rising from the build-lowest face provides a continuous geometric base. Its decreasing radius makes the declared side slope steep, but Boolean junctions and finite caps remain subject to the final mesh screen. Cloots et al. (2013, https://utw10945.utweb.utexas.edu/Manuscripts/2013/2013-50-Cloots.pdf) emphasize heat dissipation and support strategy; an analytic beam angle does not prove the full union is support-free.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        float baseRadius = 1.6f, topRadius = 0.7f;
        float rise = (hi.Z - lo.Z) * 0.75f;
        if (rise <= 0 || MathF.Atan(rise / (baseRadius - topRadius)) * 180 / MathF.PI <= 55f)
            throw new InvalidDataException("Buttress side angle is too shallow.");
        using Lattice buttress = new(lib);
        buttress.AddBeam(new Vector3(hi.X - 0.5f, c.Y, lo.Z), baseRadius,
            new Vector3(hi.X - 0.5f, c.Y, lo.Z + rise), topRadius, false);
        using Voxels gusset = new(buttress);
        part.BoolAdd(gusset);
        """,
    )
    add(
        "Opposed tapered buttresses distribute attachment geometry",
        "Add matching tapered buttresses to opposed X sides of a scanned coupon. Both start at the build-lowest face and narrow upward. Do not call matching geometry a balanced thermal or mechanical design without analysis.",
        "Two mirrored buttresses provide a declared symmetric geometry and steep sides, while avoiding an unsupported floating tab. Symmetry alone does not establish stiffness, residual stress or recoater stability. Cloots et al. (2013, https://utw10945.utweb.utexas.edu/Manuscripts/2013/2013-50-Cloots.pdf) and Mercelis/Kruth (2006, https://doi.org/10.1108/13552540610707013) motivate process-aware support and stress evaluation; those evaluations remain outside this geometric construction.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        float baseRadius = 1.4f, topRadius = 0.6f;
        float rise = (hi.Z - lo.Z) * 0.8f;
        if (rise <= 0 || MathF.Atan(rise / (baseRadius - topRadius)) * 180 / MathF.PI <= 55f)
            throw new InvalidDataException("Opposed buttress slopes are too shallow.");
        using Lattice buttresses = new(lib);
        foreach (float x in new[] { lo.X + 0.5f, hi.X - 0.5f })
            buttresses.AddBeam(new Vector3(x, c.Y, lo.Z), baseRadius,
                new Vector3(x, c.Y, lo.Z + rise), topRadius, false);
        using Voxels reinforcement = new(buttresses);
        part.BoolAdd(reinforcement);
        """,
    )
    add(
        "Four corner pillars use a bounded reinforcement pitch",
        "Add four vertical tapered reinforcement pillars near a scan coupon's corners, using at least 1.2 mm diameter at their narrow ends. Validate the declared pitch against the scan envelope and keep them anchored at the build-lowest face.",
        "The pillar pitch comes from the bounded coupon envelope, and the narrow-end diameter exceeds the chosen 1 mm wall scale. This is a reinforcement candidate rather than a optimized topology. Cloots et al. (2013, https://utw10945.utweb.utexas.edu/Manuscripts/2013/2013-50-Cloots.pdf) motivate attention to support and heat paths. The final union can still fail the overhang, wall or topology screens and must retain that outcome.",
        r"""
        using Voxels part = new(scan);
        Vector3 size = hi - lo;
        float inset = 1.2f, baseRadius = 1f, tipRadius = 0.6f;
        if (size.X - 2 * inset < 2 * baseRadius + minWall ||
            size.Y - 2 * inset < 2 * baseRadius + minWall || size.Z < 4f)
            throw new InvalidDataException("Corner pitch cannot preserve nominal ligaments.");
        using Voxels cavity = new(scan);
        cavity.Offset(-minWall);
        part.BoolSubtract(cavity); // Interior pillars reinforce a hollow, not an already solid scan.
        using Lattice pillars = new(lib);
        foreach (float x in new[] { lo.X + inset, hi.X - inset })
            foreach (float y in new[] { lo.Y + inset, hi.Y - inset })
                pillars.AddBeam(new Vector3(x, y, lo.Z), baseRadius,
                    new Vector3(x, y, hi.Z - minWall), tipRadius, false);
        using Voxels reinforcement = new(pillars);
        part.BoolAdd(reinforcement);
        """,
    )

    add(
        "Actual enclosed-void components get sampled low-point drains",
        "Hollow a scan with a 1 mm nominal skin, automatically discover every enclosed void component on a 0.2 mm grid, exclude exterior air by a box-face flood, and cut a 3 mm drain from each component's sampled minimum Z. Limit the grid to one million samples and use -Z only for the declared evacuation pose.",
        "The helper samples the final solid rather than nominating one global bounding-box vent. Exterior air is marked first; remaining six-connected void components yield their own lowest sampled point. A vertical flat-ended cutter reaches from below the part into each component. Materialise C465 guidance (https://www.materialise.com/en/academy/industrial/design-am/stainless-steel-c465) motivates powder access; finite grid connectivity and the 3 mm tutorial port do not prove complete removal. Automatic cuts may remove load-path material, so final walls, connections and measured attachment regions need review. An inherited flat cavity roof still fails the overhang screen.",
        r"""
        if (minWall / h < 5f) throw new InvalidOperationException("Nominal wall needs five samples.");
        using Voxels part = new(scan);
        using Voxels cavity = new(scan);
        cavity.Offset(-minWall);
        part.BoolSubtract(cavity);
        part.CalculateProperties(out _, out BBox3 actualBounds);
        int portCount = VentPockets(lib, part, actualBounds, h);
        Console.WriteLine($"Enclosed components found and vented: {portCount}.");
        // The shared final screens inspect the post-drilling candidate, including new thin walls.
        """, VENT,
    )
    add(
        "Clipped pointed cavities are vented by detected topology",
        "Create two pointed conical cavities clipped inside a 1 mm eroded scan. Detect enclosed voids after clipping instead of assuming exactly two chambers, then cut low-point 3 mm drains for every detected component with a bounded six-neighbor flood.",
        "Intersections with a real scan can split an intended cone into additional pockets, so vent count must follow the final voxel topology. A box-face flood excludes exterior air before each enclosed component is searched for its sampled minimum Z. The cone roof has a declared steep analytical slope, while clipping may introduce failing down-facing surfaces. Cloots et al. (2013, https://utw10945.utweb.utexas.edu/Manuscripts/2013/2013-50-Cloots.pdf) motivate process-aware support minimization; Materialise guidance (https://www.materialise.com/en/academy/industrial/design-am/stainless-steel-c465) motivates access. The post-cut geometry remains unqualified.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        if (hi.X - lo.X < 7.8f || hi.Y - lo.Y < 6f || hi.Z - lo.Z < 6f)
            throw new InvalidDataException("Detected-vent cone coupon is too small.");
        using Voxels allowed = new(scan);
        allowed.Offset(-minWall);
        foreach (float x in new[] { lo.X + 2.1f, hi.X - 2.1f })
        {
            Vector3 floor = new(x, c.Y, lo.Z + minWall);
            using Voxels cone = Render(lib, new RisingConeVoid(floor, 1.5f, 3.2f), bounds);
            cone.BoolIntersect(allowed);
            part.BoolSubtract(cone);
        }
        part.CalculateProperties(out _, out BBox3 actualBounds);
        int portCount = VentPockets(lib, part, actualBounds, h);
        Console.WriteLine($"Detected topology required {portCount} drainage cuts.");
        """, CONE + "\n\n" + VENT,
    )
    add(
        "Reserved central collar does not imply one connected labyrinth",
        "Hollow an oriented-point reconstructed scan around a protected solid central collar. Discover all enclosed void components, identify each lowest sampled Z and cut 3 mm build-down drainage shafts. Explicitly review whether those shafts have damaged the collar or other load-entry material.",
        "A reserved collar can divide or redirect the surrounding cavity, and noisy reconstructed geometry can introduce extra pockets. Component-based venting therefore follows the actual Boolean solid, using bounded grid sampling with exterior exclusion. The automatic straight routes intentionally do not implement load-path-aware routing: review the final collar and ligaments after drilling. Materialise C465 guidance (https://www.materialise.com/en/academy/industrial/design-am/stainless-steel-c465) motivates access, while Sigmund (1994, https://doi.org/10.1016/0020-7683(94)90154-6) motivates preserving structural objectives. Neither foundation certifies this simple routing algorithm.",
        r"""
        using Voxels part = new(scan);
        Vector3 c = (lo + hi) * 0.5f;
        using Lattice collarLattice = new(lib);
        collarLattice.AddBeam(new Vector3(c.X, c.Y, lo.Z), 0.8f,
            new Vector3(c.X, c.Y, hi.Z), 0.8f, false);
        using Voxels collar = new(collarLattice);
        using Voxels cavity = new(scan);
        cavity.Offset(-minWall);
        cavity.BoolSubtract(collar);
        part.BoolSubtract(cavity);
        part.CalculateProperties(out _, out BBox3 actualBounds);
        int portCount = VentPockets(lib, part, actualBounds, h);
        Console.WriteLine($"Automatic drains: {portCount}; review collar ligaments after cutting.");
        """, VENT, load_mode="oriented",
    )

    assert len(rows) == 30 and [row["id"] for row in rows] == list(range(106, 136))
    assert len({row["title"] for row in rows}) == 30
    assert all("using Voxels part = new(scan);" in row["body"] for row in rows)
    return rows
