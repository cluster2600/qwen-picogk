"""Explicit scan-repair and debugging curriculum for PicoGK 2.3.0."""

from textwrap import dedent


SCAN_BASIS = (
    " Curless and Levoy (1996), https://doi.org/10.1145/237170.237269, "
    "supports visibility-aware volumetric range integration, not inferring a solid "
    "from arbitrary unoriented points. Here the selected loader states its input "
    "assumptions, and the repair operates on its resulting voxel field. Positive "
    "Offset dilates; negative Offset erodes. Neither morphology nor voxel-to-mesh "
    "conversion establishes scan accuracy, manifoldness, support freedom, or "
    "manufacturing authorization. The final geometry must pass the reported "
    "wall, overhang, connected-void, and powder-route screens before process review."
)


def examples():
    rows = []

    def add(identifier, title, task, explanation, load_mode, body, *, category="scan", helpers=""):
        rows.append({
            "id": identifier, "category": category, "title": title,
            "task": task, "explanation": explanation + SCAN_BASIS,
            "load_mode": load_mode, "body": dedent(body).strip(),
            "helpers": dedent(helpers).strip(),
        })

    add(1, "Close sub-resolution scan fissures",
        "Read XYZ surface samples in millimetres as a documented union-of-splats envelope. "
        "Close fissures on the 0.4 mm scale without claiming to reconstruct an unseen solid interior. "
        "Show the correct Offset order and measure the actual volume change.",
        "A dilation followed by the same erosion closes nearby concave gaps; it can also bridge "
        "real gaps, so the radius is an explicit measurement assumption. Volume drift is recorded, "
        "and an empty result is rejected rather than exported as a repaired part.", "splats", """
        // Closing expands first, then returns the nominal outer envelope.
        using Voxels part = new(scan);
        part.Offset(2 * h);
        part.Offset(-2 * h);
        scan.CalculateProperties(out float originalVolume, out _);
        part.CalculateProperties(out float repairedVolume, out _);
        if (part.bIsEmpty()) throw new InvalidOperationException("Closing erased the input.");
        Console.WriteLine($"Closing volume change: {repairedVolume - originalVolume:F3} mm3");
        """)

    add(2, "Remove convex splat spikes",
        "Ingest noisy XYZ samples and remove convex spikes approximately one voxel wide using "
        "a morphological opening. Preserve the scan as a separate object and quantify removed material.",
        "Opening erodes before dilating, so it suppresses small convex protrusions rather than "
        "closing cracks. The residual distinguishes material removed by the filter from subsequent "
        "DfAM changes; a filter is not evidence that a protrusion was measurement noise.", "splats", """
        using Voxels part = new(scan);
        // Opening removes convex details below the chosen radius.
        part.Offset(-h);
        part.Offset(h);
        using Voxels removed = new(scan);
        removed.BoolSubtract(part);
        removed.CalculateProperties(out float removedVolume, out _);
        if (part.bIsEmpty()) throw new InvalidOperationException("Opening removed all material.");
        Console.WriteLine($"Material removed by opening: {removedVolume:F3} mm3");
        """)

    add(3, "Balance crack closure and spike removal",
        "Apply a 0.4 mm closing followed by a 0.2 mm opening to an XYZ splat envelope. "
        "Keep the two scales explicit and report total material drift rather than claiming a noiseless reconstruction.",
        "Different closing and opening radii encode two different noise hypotheses. Closing may "
        "join neighbouring splats, while opening may remove thin legitimate features. Running them "
        "in this order is intentionally different from a single net offset.", "splats", """
        using Voxels part = new(scan);
        // Repair concavities at one scale, then suppress finer convex detail.
        part.Offset(2 * h);
        part.Offset(-2 * h);
        part.Offset(-h);
        part.Offset(h);
        scan.CalculateProperties(out float before, out _);
        part.CalculateProperties(out float after, out _);
        if (part.bIsEmpty()) throw new InvalidOperationException("The two-scale filter erased the scan.");
        Console.WriteLine($"Two-scale volume drift: {after - before:F3} mm3");
        """)

    add(4, "Preserve a bottom datum during smoothing",
        "A closed scan STL has an explicitly designated 1 mm bottom datum band. Smooth the rest "
        "with TripleOffset while restoring this original band exactly at voxel resolution.",
        "Protected masks preserve the supplied datum occupancy instead of relying on smoothing "
        "to leave a planar face unchanged. The datum band is a user-supplied assumption, not a "
        "measured mounting interface. Intersections can create a transition seam requiring review.", "mesh", """
        using Voxels part = new(scan);
        Vector3 datumTop = new(hi.X, hi.Y, MathF.Min(hi.Z, lo.Z + minWall));
        using Voxels mask = Render(lib, new Box(lo, datumTop), bounds);
        using Voxels datum = new(scan);
        datum.BoolIntersect(mask);
        // Filter only the unprotected material, then restore the datum.
        part.TripleOffset(h);
        part.BoolSubtract(mask);
        part.BoolAdd(datum);
        Console.WriteLine("Bottom datum occupancy restored from the original scan.");
        """)

    add(5, "Protect two opposed mating faces",
        "The first and last 1 mm bands along X of a closed STL are designated mating faces. "
        "Perform a morphological closing only between them and restore both original bands.",
        "Two protected masks prevent a global repair from moving either nominated interface. "
        "Protecting whole bands also retains their local defects, which must be inspected separately; "
        "the code does not invent plane locations or tolerances.", "mesh", """
        using Voxels part = new(scan);
        using Voxels left = Render(lib, new Box(lo, new Vector3(lo.X + minWall, hi.Y, hi.Z)), bounds);
        using Voxels right = Render(lib, new Box(new Vector3(hi.X - minWall, lo.Y, lo.Z), hi), bounds);
        left.BoolAdd(right);
        using Voxels interfaces = new(scan);
        interfaces.BoolIntersect(left);
        part.Offset(h);
        part.Offset(-h);
        part.BoolSubtract(left);
        part.BoolAdd(interfaces);
        Console.WriteLine("Both nominated X interface bands remain at scan occupancy.");
        """)

    add(6, "Exclude a central attachment zone from opening",
        "A closed STL includes a nominated central attachment zone covering the middle third "
        "of its X and Y extent. Suppress peripheral spikes while retaining that zone's original geometry.",
        "An interior mask separates a protected attachment zone from cosmetic repair. Bounding-box "
        "fractions are explicit synthetic training datums, not reverse-engineered hole patterns. "
        "The transition and attachment load path still need measured-interface validation.", "mesh", """
        using Voxels part = new(scan);
        Vector3 span = hi - lo;
        Vector3 maskLo = new(lo.X + span.X / 3, lo.Y + span.Y / 3, lo.Z);
        Vector3 maskHi = new(hi.X - span.X / 3, hi.Y - span.Y / 3, hi.Z);
        using Voxels mask = Render(lib, new Box(maskLo, maskHi), bounds);
        using Voxels attachment = new(scan);
        attachment.BoolIntersect(mask);
        part.Offset(-h);
        part.Offset(h);
        part.BoolSubtract(mask);
        part.BoolAdd(attachment);
        Console.WriteLine("Central synthetic attachment mask preserved.");
        """)

    add(7, "Repair only a nominated half-space",
        "Repair micro-fissures only in the X-positive half of an oriented scan reconstruction. "
        "Keep the opposite half unchanged and explicitly handle the region boundary.",
        "A region mask restricts repair to the supplied suspect area. Replacing filtered occupancy "
        "inside that mask avoids smoothing the trusted half. The mask boundary is a potential "
        "discontinuity, so the final geometry screen remains essential.", "oriented", """
        using Voxels part = new(scan);
        Vector3 regionLo = new((lo.X + hi.X) / 2, lo.Y, lo.Z);
        using Voxels region = Render(lib, new Box(regionLo, hi), bounds);
        using Voxels repaired = new(scan);
        repaired.Offset(h);
        repaired.Offset(-h);
        repaired.BoolIntersect(region);
        // Replace only the specified repair region.
        part.BoolSubtract(region);
        part.BoolAdd(repaired);
        Console.WriteLine("Closing confined to the nominated X half-space.");
        """)

    add(8, "Spherical region of interest repair",
        "An oriented point scan has a nominated spherical noisy region at the bounding-box centre. "
        "Open only that region using a real PicoGK Lattice sphere as the mask.",
        "AddSphere is a method on Lattice, and new Voxels(lattice) rasterizes the mask. This uses "
        "actual PicoGK types rather than an invented VoxelMatrix. A spherical mask bounds the "
        "repair footprint; it does not prove the selected samples were outliers.", "oriented", """
        using Voxels part = new(scan);
        Vector3 centre = (lo + hi) / 2;
        float radius = MathF.Min(hi.X - lo.X, hi.Y - lo.Y) / 3;
        using Lattice maskLattice = new(lib);
        maskLattice.AddSphere(centre, radius);
        using Voxels mask = new(maskLattice);
        using Voxels local = new(scan);
        local.Offset(-h);
        local.Offset(h);
        local.BoolIntersect(mask);
        part.BoolSubtract(mask);
        part.BoolAdd(local);
        Console.WriteLine($"Spherical repair radius: {radius:F3} mm");
        """)

    add(9, "Cylindrical seam region repair",
        "Repair an explicitly nominated vertical seam region around the scan centreline. "
        "Build its cylindrical mask with AddBeam and perform a local closing without rounded caps.",
        "A constant-radius beam with bRoundCap=false represents a cylindrical mask. Its role here "
        "is local repair, not a powder vent. The seam position is provided by the task, and the "
        "result remains a candidate until the repaired transition is checked.", "oriented", """
        using Voxels part = new(scan);
        Vector3 centre = (lo + hi) / 2;
        float radius = MathF.Min(hi.X - lo.X, hi.Y - lo.Y) / 4;
        using Lattice seam = new(lib);
        seam.AddBeam(new Vector3(centre.X, centre.Y, lo.Z), radius,
                     new Vector3(centre.X, centre.Y, hi.Z), radius, false);
        using Voxels mask = new(seam);
        using Voxels repaired = new(scan);
        repaired.DoubleOffset(h, -h);
        repaired.BoolIntersect(mask);
        part.BoolSubtract(mask);
        part.BoolAdd(repaired);
        Console.WriteLine("Local seam closing uses a flat-capped cylindrical mask.");
        """)

    add(10, "Voxelize and remesh a closed STL",
        "Read a closed, correctly oriented STL explicitly in millimetres, voxelize it, and obtain "
        "a new mesh. Round-trip it back to voxels and report volume drift without calling the mesh manifold.",
        "A mesh-to-voxel-to-mesh round trip resamples the source at the chosen voxel pitch. It "
        "changes resolution and may change tiny features. Counting output triangles checks that "
        "geometry exists; manifoldness requires an independent edge/topology audit.", "mesh", """
        using Mesh remeshed = new(scan);
        if (remeshed.nTriangleCount() == 0) throw new InvalidOperationException("Remeshing produced no triangles.");
        using Voxels part = new(remeshed);
        scan.CalculateProperties(out float sourceVolume, out _);
        part.CalculateProperties(out float resultVolume, out _);
        // Report resampling error separately from any engineering claim.
        Console.WriteLine($"Remeshed triangles: {remeshed.nTriangleCount()}");
        Console.WriteLine($"Round-trip volume drift: {resultVolume - sourceVolume:F3} mm3");
        """)

    add(11, "Smooth before remeshing",
        "A watertight STL contains submillimetre surface chatter. Smooth its voxelization by one "
        "voxel, then remesh and revoxelize once. Record the resolution and resulting triangle count.",
        "TripleOffset applies three explicit morphological stages, then the mesh round trip "
        "resamples the filtered field. This is a controlled geometric filter rather than a "
        "manufacturing or metrology certificate; noise scale must come from scan uncertainty.", "mesh", """
        using Voxels filtered = new(scan);
        filtered.TripleOffset(h);
        using Mesh remeshed = new(filtered);
        using Voxels part = new(remeshed);
        if (part.bIsEmpty()) throw new InvalidOperationException("Filtered round trip is empty.");
        // Surface sampling and output tessellation are both resolution-dependent.
        Console.WriteLine($"Voxel pitch: {h:F3} mm");
        Console.WriteLine($"Filtered mesh triangles: {remeshed.nTriangleCount()}");
        """)

    add(12, "Diagnose degenerate remeshed facets",
        "Remesh a closed STL after a small closing. Traverse every output triangle, count "
        "near-zero-area facets, and refuse to silently claim a clean mesh if they are present.",
        "Degenerate triangles can corrupt normal-based printability screens. A scale-aware "
        "area threshold catches numerically collapsed facets; it does not replace edge incidence "
        "or connected-component tests. The code fails explicitly before a clean-mesh claim.", "mesh", """
        using Voxels part = new(scan);
        part.DoubleOffset(h, -h);
        using Mesh repairedMesh = new(part);
        int degenerate = 0;
        for (int i = 0; i < repairedMesh.nTriangleCount(); i++)
        {
            repairedMesh.GetTriangle(i, out Vector3 a, out Vector3 b, out Vector3 c);
            if (Vector3.Cross(b - a, c - a).Length() < h * h * 0.001f) degenerate++;
        }
        Console.WriteLine($"Degenerate facets: {degenerate}");
        if (degenerate != 0) throw new InvalidOperationException("Degenerate facets require mesh review.");
        """)

    add(13, "Set a volume-drift repair budget",
        "Close an oriented scan by one voxel but accept the automatic edit only when volume drift "
        "is at most 5 percent. Restore the original when the proposed edit exceeds that explicit budget.",
        "A volume budget is a coarse guard against large edits, not proof of local dimensional "
        "accuracy. This example rolls back a failed proposal rather than exporting it as repaired. "
        "Zero source volume is invalid and is rejected before computing a ratio.", "oriented", """
        using Voxels part = new(scan);
        scan.CalculateProperties(out float before, out _);
        if (before <= 0) throw new InvalidOperationException("Source volume must be positive.");
        part.DoubleOffset(h, -h);
        part.CalculateProperties(out float after, out _);
        float drift = MathF.Abs(after - before) / before;
        if (drift > 0.05f)
        {
            // Roll back the candidate without changing the source field.
            using Voxels rejected = new(part);
            part.BoolSubtract(rejected);
            part.BoolAdd(scan);
        }
        Console.WriteLine($"Proposed closing relative volume drift: {drift:F5}");
        """)

    add(14, "Compare closing and opening volume costs",
        "For an oriented scan, compare one-voxel closing and opening by their absolute volume "
        "change. Choose the lower-drift candidate and explain why this is only a geometric heuristic.",
        "Opening and closing have different semantic effects, so minimum volume change is "
        "useful only when both operations are permitted by the scan-repair brief. The code reports "
        "both costs; it does not infer which surface detail is physically correct.", "oriented", """
        using Voxels closed = new(scan);
        using Voxels opened = new(scan);
        closed.DoubleOffset(h, -h);
        opened.DoubleOffset(-h, h);
        scan.CalculateProperties(out float referenceVolume, out _);
        closed.CalculateProperties(out float closedVolume, out _);
        opened.CalculateProperties(out float openedVolume, out _);
        bool chooseClosed = MathF.Abs(closedVolume - referenceVolume) <= MathF.Abs(openedVolume - referenceVolume);
        using Voxels part = new(chooseClosed ? closed : opened);
        Console.WriteLine($"Closing drift: {closedVolume - referenceVolume:F3} mm3");
        Console.WriteLine($"Opening drift: {openedVolume - referenceVolume:F3} mm3; selected closing={chooseClosed}");
        """)

    add(15, "Bound repair by original spatial extent",
        "Close a reconstructed scan by two voxels and clip the result to the source bounding box. "
        "Report clipping volume and explain why preserving extents does not preserve all dimensions.",
        "A source-envelope constraint prevents unbounded outward edits, while still allowing "
        "changes within the envelope. This is appropriate only when the supplied bounds are "
        "trusted and no intended geometry lies beyond them.", "oriented", """
        using Voxels part = new(scan);
        part.DoubleOffset(2 * h, -2 * h);
        using Voxels beforeTrim = new(part);
        part.Trim(bounds);
        beforeTrim.BoolSubtract(part);
        beforeTrim.CalculateProperties(out float clippedVolume, out _);
        BBox3 repairedBounds = part.oCalculateBoundingBox();
        Console.WriteLine($"Clipped outside original bounds: {clippedVolume:F3} mm3");
        Console.WriteLine($"Remaining extent: {repairedBounds.vecMax - repairedBounds.vecMin}");
        """)

    add(16, "Measure additive repair residual",
        "Close a splat envelope and isolate only material introduced by repair. Report added "
        "material volume so that unintended bridges can be reviewed independently.",
        "The difference repaired minus original isolates additive repair. A small total volume "
        "can still bridge a functional gap, so this diagnostic is not an acceptance proof. "
        "Boolean differences use BoolSubtract, the actual PicoGK method.", "splats", """
        using Voxels part = new(scan);
        part.DoubleOffset(h, -h);
        using Voxels added = new(part);
        added.BoolSubtract(scan);
        added.CalculateProperties(out float addedVolume, out _);
        using Voxels removed = new(scan);
        removed.BoolSubtract(part);
        removed.CalculateProperties(out float removedVolume, out _);
        Console.WriteLine($"Closing added {addedVolume:F3} mm3 and removed {removedVolume:F3} mm3");
        """)

    add(17, "Measure symmetric morphological disagreement",
        "Smooth an XYZ envelope and measure the symmetric difference between original and "
        "candidate. Do not hide cancellation between added and removed volume.",
        "Net volume change can cancel equal additions and removals. The union of both directed "
        "differences measures occupancy disagreement without that cancellation. It is still "
        "resolution-dependent and does not measure maximum surface displacement.", "splats", """
        using Voxels part = new(scan);
        part.TripleOffset(h);
        using Voxels difference = new(part);
        difference.BoolSubtract(scan);
        using Voxels removed = new(scan);
        removed.BoolSubtract(part);
        difference.BoolAdd(removed);
        difference.CalculateProperties(out float disagreement, out _);
        scan.CalculateProperties(out float referenceVolume, out _);
        Console.WriteLine($"Symmetric disagreement: {disagreement:F3} mm3 / {referenceVolume:F3} mm3");
        """)

    add(18, "Reject repairs that move too much occupancy",
        "Propose a one-voxel closing to an oriented scan, then reject it if symmetric occupancy "
        "disagreement exceeds 10 percent of source volume. Count additions and removals separately.",
        "A symmetric-difference budget is stricter than a net volume budget, although it can "
        "still miss a local high-consequence change. The explicit exception prevents a failed "
        "candidate from being represented as an accepted repair.", "oriented", """
        using Voxels part = new(scan);
        part.DoubleOffset(h, -h);
        using Voxels addition = new(part);
        addition.BoolSubtract(scan);
        using Voxels removal = new(scan);
        removal.BoolSubtract(part);
        addition.CalculateProperties(out float addedVolume, out _);
        removal.CalculateProperties(out float removedVolume, out _);
        scan.CalculateProperties(out float sourceVolume, out _);
        Console.WriteLine($"Source volume={sourceVolume:F6} mm3; added={addedVolume:F6} mm3; removed={removedVolume:F6} mm3");
        if (sourceVolume <= 0 || addedVolume + removedVolume > 0.1f * sourceVolume)
            throw new InvalidOperationException("Safety rejection: repair exceeds its explicit occupancy-change budget.");
        Console.WriteLine($"Repair budget used: {addedVolume + removedVolume:F3} mm3");
        """)

    add(19, "Create a conservative inward-offset skin",
        "Use a closed STL boundary to construct an inward 1 mm skin after scan repair. "
        "Reject an empty interior and show why erosion distance is a design parameter rather than a measured minimum wall.",
        "Subtracting an eroded copy gives an inward skin while retaining the outer envelope. "
        "Voxel discretization and local curvature can affect thickness, so minWall is a target "
        "that still requires the final thickness screen. Mercelis and Kruth (2006), "
        "https://doi.org/10.1108/13552540610707013, explains residual stress, which this geometry does not solve.", "mesh", """
        using Voxels repaired = new(scan);
        repaired.DoubleOffset(h, -h);
        using Voxels interior = new(repaired);
        interior.Offset(-minWall);
        if (interior.bIsEmpty()) throw new InvalidOperationException("The scan is too small for the requested hollow skin.");
        using Voxels part = new(repaired);
        part.BoolSubtract(interior);
        // The shared final screen checks the resulting wall and closed voids.
        Console.WriteLine($"Requested inward skin thickness: {minWall:F3} mm");
        """)

    add(20, "Protect thin geometry from global erosion",
        "For an oriented reconstruction, open only the material that survives a 1 mm erosion. "
        "Preserve all original occupancy outside that thick-core mask.",
        "The eroded core is an explicit region selector, not a local-thickness oracle. Keeping "
        "the complementary region prevents this filter from deleting thin peripheral geometry, "
        "but also keeps its scan defects and possible unprintable walls.", "oriented", """
        using Voxels part = new(scan);
        using Voxels thickCore = new(scan);
        thickCore.Offset(-minWall);
        using Voxels filteredCore = new(scan);
        filteredCore.DoubleOffset(-h, h);
        filteredCore.BoolIntersect(thickCore);
        part.BoolSubtract(thickCore);
        part.BoolAdd(filteredCore);
        Console.WriteLine("Original occupancy outside the eroded core was preserved.");
        """)

    add(21, "Audit a candidate exterior skin before hollowing",
        "A repaired STL will later be hollowed. Generate the inward-offset boundary band, measure "
        "its volume, but leave the candidate solid until a powder-access design is supplied.",
        "Separating skin diagnosis from hollowing avoids silently introducing a trapped internal "
        "chamber. A core erosion can identify the intended skin volume, but it does not qualify "
        "the wall for stress, fatigue, machining, or a particular LPBF alloy.", "mesh", """
        using Voxels part = new(scan);
        part.DoubleOffset(h, -h);
        using Voxels core = new(part);
        core.Offset(-minWall);
        using Voxels diagnosticSkin = new(part);
        diagnosticSkin.BoolSubtract(core);
        diagnosticSkin.CalculateProperties(out float skinVolume, out _);
        core.CalculateProperties(out float coreVolume, out _);
        Console.WriteLine($"Diagnostic skin={skinVolume:F3} mm3, core={coreVolume:F3} mm3");
        Console.WriteLine("Candidate remains solid; hollowing requires its own powder-route design.");
        """)

    add(22, "Detect sparse splat reconstruction",
        "Read XYZ points as splats and determine how much occupancy remains after eroding by "
        "two voxels. Use the ratio as a sparse-envelope diagnostic, not as evidence of a filled object.",
        "An unoriented point set cannot establish inside/outside. The loader therefore makes "
        "a splat envelope, and erosion survival diagnoses how much of that envelope has "
        "geometric depth. The ratio has no universal metrology or printability threshold.", "splats", """
        using Voxels part = new(scan);
        using Voxels eroded = new(scan);
        eroded.Offset(-2 * h);
        part.CalculateProperties(out float envelopeVolume, out _);
        eroded.CalculateProperties(out float coreVolume, out _);
        if (envelopeVolume <= 0) throw new InvalidOperationException("The splat envelope has no volume.");
        float survival = coreVolume / envelopeVolume;
        Console.WriteLine($"Two-voxel erosion survival: {survival:F5}");
        Console.WriteLine("This diagnostic does not establish a closed solid interior.");
        """)

    add(23, "Keep additions within a sampling envelope",
        "A noisy XYZ splat envelope may be closed, but new material must remain within one "
        "voxel of the original occupancy. Intersect the candidate with that dilated source envelope.",
        "A dilation of the original field bounds permitted repair additions. Intersecting with "
        "that field limits the spatial reach of the repair, although the bound does not guarantee "
        "the inserted material represents an actual surface.", "splats", """
        using Voxels permitted = new(scan);
        permitted.Offset(h);
        using Voxels part = new(scan);
        part.DoubleOffset(2 * h, -2 * h);
        // Constrain any inserted bridge to the documented sampling envelope.
        part.BoolIntersect(permitted);
        using Voxels addition = new(part);
        addition.BoolSubtract(scan);
        addition.CalculateProperties(out float additionVolume, out _);
        Console.WriteLine($"Constrained repair additions: {additionVolume:F3} mm3");
        """)

    add(24, "Attach a nominated calibration witness",
        "Read an XYZ scan and add a 1 mm diameter spherical witness centred one radius above "
        "the lowest source point in Z. Explain why this labelled witness is auxiliary geometry.",
        "This example teaches real AddSphere usage and distinguishes an auxiliary calibration "
        "witness from recovered geometry. The witness position is a deliberate synthetic choice; "
        "it may need supports and must not be mistaken for a physical feature of the scanned part.", "splats", """
        using Voxels part = new(scan);
        float radius = minWall / 2;
        Vector3 witnessCentre = new((lo.X + hi.X) / 2, (lo.Y + hi.Y) / 2, lo.Z + radius);
        using Lattice witness = new(lib);
        witness.AddSphere(witnessCentre, radius);
        using Voxels witnessVoxels = new(witness);
        part.BoolAdd(witnessVoxels);
        Console.WriteLine($"Auxiliary witness diameter: {2 * radius:F3} mm");
        Console.WriteLine("Witness is labelled auxiliary geometry, not reconstructed scan evidence.");
        """)

    add(25, "Retain the oriented SDF sign convention",
        "Read oriented CSV samples, perform a mild closing, then query a ScalarField converted "
        "from the result. Demonstrate raw voxel-unit values and conversion to millimetres only where active.",
        "PicoGK ScalarField values obtained from Voxels are in voxel units, while fSignedDistance "
        "returns millimetres. A failed bGetValue means inactive data; treating it as a zero distance "
        "would invent a surface. The query here reports availability without asserting interior sign.", "oriented", """
        using Voxels part = new(scan);
        part.DoubleOffset(h, -h);
        using ScalarField distances = new(part);
        Vector3 query = (lo + hi) / 2;
        if (distances.bGetValue(query, out float voxelDistance))
            Console.WriteLine($"Active signed distance at centre: {voxelDistance * h:F3} mm");
        else
            Console.WriteLine("Centre is outside the stored active SDF band; distance is unavailable.");
        Console.WriteLine("Negative active distances indicate material; absent values are not surface samples.");
        """)

    add(26, "Report oriented-scan bounding drift",
        "Close an oriented scan by one voxel and compare all six bounding planes with the "
        "original. Keep local accuracy claims separate from these coarse extent diagnostics.",
        "Bounding planes are inexpensive diagnostics for gross scale or repair drift. They "
        "cannot verify local dimensions or a mounting face. The accurate bounds helper meshes "
        "the field, avoiding spurious zero-distance voxels left by boolean operations.", "oriented", """
        using Voxels part = new(scan);
        part.DoubleOffset(h, -h);
        BBox3 finalBounds = part.oCalculateBoundingBox();
        Vector3 lowerDrift = finalBounds.vecMin - lo;
        Vector3 upperDrift = finalBounds.vecMax - hi;
        Console.WriteLine($"Lower bounding-plane drift: {lowerDrift} mm");
        Console.WriteLine($"Upper bounding-plane drift: {upperDrift} mm");
        if (!float.IsFinite(lowerDrift.Length()) || !float.IsFinite(upperDrift.Length()))
            throw new InvalidOperationException("Bounding-plane diagnostics are non-finite.");
        """)

    add(27, "Limit oriented repair to an uncertainty band",
        "An oriented scan has an explicitly assumed ±0.4 mm geometric uncertainty band. "
        "Clip a smoothed proposal between erosion and dilation constraints and report added material. "
        "If smoothing erases all measurable material, reject that filter and retain the original for the final geometry screen.",
        "The inner erosion supplies material that cannot be removed by this edit, and the outer "
        "dilation limits additions. This constructs a geometric uncertainty envelope, not a "
        "statistical confidence interval; its width must come from measured scanner uncertainty. "
        "An empty proposal is rejected and rolled back; keeping the original is not approval of its geometry.", "oriented", """
        using Voxels lowerEnvelope = new(scan);
        using Voxels upperEnvelope = new(scan);
        lowerEnvelope.Offset(-2 * h);
        upperEnvelope.Offset(2 * h);
        using Voxels proposal = new(scan);
        proposal.TripleOffset(h);
        proposal.BoolIntersect(upperEnvelope);
        proposal.BoolAdd(lowerEnvelope);
        proposal.CalculateProperties(out float proposalVolume, out _);
        bool filterRejected = proposalVolume <= 0;
        using Voxels part = new(filterRejected ? scan : proposal);
        if (filterRejected) Console.WriteLine("Safety rejection: smoothing erased the measured reconstruction; original retained for screening.");
        using Voxels addition = new(part);
        addition.BoolSubtract(scan);
        addition.CalculateProperties(out float addedVolume, out _);
        Console.WriteLine($"Uncertainty-band repair additions: {addedVolume:F3} mm3");
        """)

    add(28, "Repair fused range data conservatively",
        "Ingest CSV range samples with per-ray origins and normals using the visibility-aware "
        "range loader. Apply one-voxel closing only, then report morphology separately from range fusion.",
        "Range origins provide visibility information required by Curless–Levoy-style fusion. "
        "The morphology stage follows reconstruction and must not be presented as the range "
        "integration algorithm itself. Its radius is a documented postprocessing choice.", "range", """
        using Voxels part = new(scan);
        // Postprocess the fused volume; this is separate from visibility-aware fusion.
        part.Offset(h);
        part.Offset(-h);
        scan.CalculateProperties(out float fusedVolume, out _);
        part.CalculateProperties(out float repairedVolume, out _);
        Console.WriteLine($"Fused volume: {fusedVolume:F3} mm3");
        Console.WriteLine($"Post-fusion closing change: {repairedVolume - fusedVolume:F3} mm3");
        """)

    add(29, "Protect range-fused surface occupancy",
        "Read visibility-aware range CSV data and smooth the reconstruction, but preserve the "
        "original one-voxel exterior band. Explain the difference between trusted occupancy and measured surfaces.",
        "A one-voxel band is preserved as a supplied geometric constraint. It is only as trustworthy "
        "as the range-fusion inputs and voxelization; preservation does not turn it into a metrology "
        "certificate. This filter can alter internal artefacts while retaining the source exterior band.", "range", """
        using Voxels eroded = new(scan);
        eroded.Offset(-h);
        using Voxels exteriorBand = new(scan);
        exteriorBand.BoolSubtract(eroded);
        using Voxels part = new(scan);
        part.TripleOffset(h);
        part.BoolIntersect(eroded);
        part.BoolAdd(exteriorBand);
        Console.WriteLine("Original one-voxel exterior occupancy band restored after filtering.");
        """)

    add(30, "Expose morphology removal after range fusion",
        "Propose a one-voxel opening of a range-fused reconstruction and measure only the removed "
        "component volume. Reject an empty filtered proposal and keep the original fused input for final screening.",
        "Range fusion and morphological filtering have different evidence roles. The removal "
        "residual makes postprocessing destructive edits visible. A sparse TSDF may only observe "
        "thin bands, so an opening that erases the reconstruction is rejected and rolled back. "
        "Retaining the original does not approve its thin walls, support conditions, or completeness.", "range", """
        using Voxels proposal = new(scan);
        proposal.DoubleOffset(-h, h);
        proposal.CalculateProperties(out float proposalVolume, out _);
        bool filterRejected = proposalVolume <= 0;
        using Voxels part = new(filterRejected ? scan : proposal);
        if (filterRejected) Console.WriteLine("Safety rejection: opening erased the fused reconstruction; original retained for screening.");
        using Voxels removed = new(scan);
        removed.BoolSubtract(part);
        removed.CalculateProperties(out float removedVolume, out _);
        scan.CalculateProperties(out float referenceVolume, out _);
        Console.WriteLine($"Post-fusion removed volume: {removedVolume:F3} of {referenceVolume:F3} mm3");
        """)

    add(31, "Anisotropic closing for directional cracks",
        "A closed STL has a documented directional noise hypothesis: allow more crack bridging "
        "along X than Y or Z. Implement anisotropic closing by scaling, voxel filtering, and inverse scaling.",
        "Compressing X before isotropic closing increases the corresponding world-space "
        "morphological radius. The inverse transform restores the coordinate system, but two "
        "resamplings introduce error. This is a directional geometric filter, not a scan-physics model.", "mesh", """
        using Mesh sourceMesh = new(scan);
        using Mesh compressed = sourceMesh.mshCreateTransformed(Matrix4x4.CreateScale(0.5f, 1, 1));
        using Voxels filtered = new(compressed);
        filtered.DoubleOffset(h, -h);
        using Mesh filteredMesh = new(filtered);
        using Mesh restored = filteredMesh.mshCreateTransformed(Matrix4x4.CreateScale(2, 1, 1));
        using Voxels part = new(restored);
        // Scale-and-resample implements an ellipsoidal, not isotropic, world-space filter.
        Console.WriteLine("Closing radii are approximately 2h in X and h in Y/Z; inspect resampling drift.");
        """)

    add(32, "Suppress Z-direction scan chatter",
        "A closed scan STL exhibits finer acceptable filtering in Z than in-plane. Stretch Z "
        "before a morphological opening, undo the transform, and report the resulting extent drift.",
        "Stretching Z reduces the world-space Z radius of an isotropic opening while leaving "
        "the in-plane radius unchanged. The filter is appropriate only for the stated directional "
        "noise model. Extent drift reveals gross effects of the additional resampling.", "mesh", """
        using Mesh sourceMesh = new(scan);
        using Mesh stretched = sourceMesh.mshCreateTransformed(Matrix4x4.CreateScale(1, 1, 2));
        using Voxels filtered = new(stretched);
        filtered.DoubleOffset(-h, h);
        using Mesh filteredMesh = new(filtered);
        using Mesh restored = filteredMesh.mshCreateTransformed(Matrix4x4.CreateScale(1, 1, 0.5f));
        using Voxels part = new(restored);
        BBox3 resultBounds = part.oCalculateBoundingBox();
        Console.WriteLine($"Directional-opening extent drift: {resultBounds.vecSize() - bounds.vecSize()} mm");
        """)

    add(33, "Directional smoothing with explicit resampling audit",
        "An STL has unequal X/Y scan sampling. Apply a smoothing filter after stretching X and "
        "compressing Y, undo both scales, and report symmetric voxel disagreement.",
        "The scale transform changes the physical radii of the three morphological stages. "
        "The symmetric difference includes both deliberate filtering and resampling effects; "
        "it is therefore reported as total geometric disagreement, not scanner error alone.", "mesh", """
        using Mesh sourceMesh = new(scan);
        using Mesh transformed = sourceMesh.mshCreateTransformed(Matrix4x4.CreateScale(2, 0.5f, 1));
        using Voxels filtered = new(transformed);
        filtered.TripleOffset(h);
        using Mesh filteredMesh = new(filtered);
        using Mesh restored = filteredMesh.mshCreateTransformed(Matrix4x4.CreateScale(0.5f, 2, 1));
        using Voxels part = new(restored);
        using Voxels addition = new(part);
        addition.BoolSubtract(scan);
        using Voxels removal = new(scan);
        removal.BoolSubtract(part);
        addition.BoolAdd(removal);
        addition.CalculateProperties(out float disagreement, out _);
        Console.WriteLine($"Directional smoothing plus resampling disagreement: {disagreement:F3} mm3");
        """)

    add(34, "Round concave scan notches explicitly",
        "Use PicoGK Fillet on a closed STL to round small concave notches with a 0.4 mm radius. "
        "Identify all added material and avoid treating the result as measured original geometry.",
        "Fillet modifies the supplied shape intentionally, so its added material is a design "
        "change rather than recovered scan evidence. The API performs morphology and does not "
        "guarantee an analytic circular fillet radius at every voxelized corner.", "mesh", """
        using Voxels part = new(scan);
        part.Fillet(2 * h);
        using Voxels addition = new(part);
        addition.BoolSubtract(scan);
        addition.CalculateProperties(out float addedVolume, out _);
        // Added matter is an intentional geometric edit, not scan evidence.
        Console.WriteLine($"Fillet request: {2 * h:F3} mm; added material: {addedVolume:F3} mm3");
        if (part.bIsEmpty()) throw new InvalidOperationException("Fillet result is empty.");
        """)

    add(35, "Limit closing to concave changes",
        "Close a mesh scan by one voxel, but prohibit any removal of original material. "
        "Union the repaired candidate with the original and quantify only the retained additions.",
        "Restoring original occupancy enforces an additive-only repair policy despite voxel "
        "resampling effects. This policy can retain unprintable protrusions and may insert unwanted "
        "bridges, so it must match the explicit repair brief.", "mesh", """
        using Voxels part = new(scan);
        part.DoubleOffset(h, -h);
        part.BoolAdd(scan);
        using Voxels added = new(part);
        added.BoolSubtract(scan);
        added.CalculateProperties(out float addedVolume, out _);
        using Voxels lost = new(scan);
        lost.BoolSubtract(part);
        Console.WriteLine($"Additive-only closing inserted {addedVolume:F3} mm3; lost field empty={lost.bIsEmpty()}");
        """)

    add(36, "Limit opening to removal changes",
        "Open a closed STL by one voxel, but prohibit additions outside the original material. "
        "Intersect the candidate with the source and report the amount removed.",
        "An explicit intersection enforces a subtractive-only policy at voxel occupancy level. "
        "This is useful when added material is forbidden, but it can reduce functional wall "
        "thickness and must be followed by the minimum-wall screen.", "mesh", """
        using Voxels part = new(scan);
        part.DoubleOffset(-h, h);
        part.BoolIntersect(scan);
        using Voxels removed = new(scan);
        removed.BoolSubtract(part);
        removed.CalculateProperties(out float removedVolume, out _);
        if (part.bIsEmpty()) throw new InvalidOperationException("Subtractive-only opening removed everything.");
        Console.WriteLine($"Subtractive-only opening removed {removedVolume:F3} mm3");
        """)

    add(37, "Audit forward surface displacement",
        "Smooth an oriented reconstruction and sample every eighth vertex of its mesh. Query "
        "the closest original surface point and record a directed maximum displacement diagnostic.",
        "A directed vertex-to-surface distance is a useful repair audit but is not the exact "
        "Hausdorff distance because sampling is incomplete and only one direction is measured. "
        "A failed nearest-surface query is a real error rather than a zero residual.", "oriented", """
        using Voxels part = new(scan);
        part.TripleOffset(h);
        using Mesh resultMesh = new(part);
        if (resultMesh.nTriangleCount() == 0)
            throw new InvalidOperationException("Safety rejection: smoothing erased the reconstruction; surface deviation is unavailable.");
        float maximum = 0;
        for (int i = 0; i < resultMesh.nVertexCount(); i += 8)
        {
            Vector3 sample = resultMesh.vecVertexAt(i);
            if (!scan.bClosestPointOnSurface(sample, out Vector3 closest))
                throw new InvalidOperationException("Original surface query failed.");
            maximum = MathF.Max(maximum, Vector3.Distance(sample, closest));
        }
        Console.WriteLine($"Sampled candidate-to-source maximum: {maximum:F3} mm; not an exact Hausdorff distance");
        """)

    add(38, "Audit reverse surface displacement",
        "Open an oriented reconstruction and sample the original mesh toward the new surface. "
        "Report the reverse directed residual so removed protrusions are not hidden by forward-only sampling.",
        "Original-to-candidate sampling can reveal removed features that candidate-to-original "
        "sampling misses. The stride keeps this tutorial bounded, and the result is explicitly "
        "a sampled diagnostic rather than a guaranteed maximum deviation.", "oriented", """
        using Voxels part = new(scan);
        part.DoubleOffset(-h, h);
        using Mesh candidateMesh = new(part);
        if (candidateMesh.nTriangleCount() == 0)
            throw new InvalidOperationException("Safety rejection: opening erased the reconstruction; reverse surface deviation is unavailable.");
        using Mesh originalMesh = new(scan);
        float maximum = 0;
        int count = 0;
        for (int i = 0; i < originalMesh.nVertexCount(); i += 8)
        {
            Vector3 sample = originalMesh.vecVertexAt(i);
            if (!part.bClosestPointOnSurface(sample, out Vector3 closest))
                throw new InvalidOperationException("Repaired surface query failed.");
            maximum = MathF.Max(maximum, Vector3.Distance(sample, closest));
            count++;
        }
        Console.WriteLine($"Source-to-candidate sampled maximum: {maximum:F3} mm over {count} vertices");
        """)

    add(39, "Gate repair on sampled bidirectional deviation",
        "Close an oriented scan by one voxel and reject the candidate if sampled bidirectional "
        "surface deviation exceeds 0.6 mm. Explain why this sampled gate cannot certify all dimensions.",
        "Sampling both directions reduces a common blind spot in surface audits. The tolerance "
        "is a task-specific training assumption, and unsampled regions remain unverified. "
        "Actual release needs metrology against measured interfaces and a complete surface audit.", "oriented", """
        using Voxels part = new(scan);
        part.DoubleOffset(h, -h);
        using Mesh sourceMesh = new(scan);
        using Mesh candidateMesh = new(part);
        float maximum = 0;
        foreach (var pair in new[] { (sourceMesh, part), (candidateMesh, scan) })
        {
            for (int i = 0; i < pair.Item1.nVertexCount(); i += 8)
            {
                Vector3 sample = pair.Item1.vecVertexAt(i);
                if (!pair.Item2.bClosestPointOnSurface(sample, out Vector3 closest))
                    throw new InvalidOperationException("Bidirectional surface query failed.");
                maximum = MathF.Max(maximum, Vector3.Distance(sample, closest));
            }
        }
        Console.WriteLine($"Sampled bidirectional deviation: {maximum:F3} mm");
        if (maximum > 3 * h) throw new InvalidOperationException("Safety rejection: sampled repair deviation exceeds 0.6 mm.");
        """)

    add(40, "Choose among documented repair scales",
        "For a closed STL, compare 0.2 and 0.4 mm closings by symmetric occupancy disagreement. "
        "Choose the smaller edit when the repair brief permits either scale; report both costs.",
        "Candidate comparison makes the tradeoff explicit instead of claiming that a larger "
        "filter is better. Symmetric disagreement quantifies edit extent, not repair success. "
        "A candidate that fails the final geometry screens remains rejected even if its cost is lower.", "mesh", """
        using Voxels small = new(scan);
        using Voxels large = new(scan);
        small.DoubleOffset(h, -h);
        large.DoubleOffset(2 * h, -2 * h);
        float[] costs = new float[2];
        Voxels[] candidates = { small, large };
        for (int i = 0; i < candidates.Length; i++)
        {
            using Voxels added = new(candidates[i]);
            added.BoolSubtract(scan);
            using Voxels removed = new(scan);
            removed.BoolSubtract(candidates[i]);
            added.BoolAdd(removed);
            added.CalculateProperties(out costs[i], out _);
        }
        using Voxels part = new(costs[0] <= costs[1] ? small : large);
        Console.WriteLine($"Closing disagreement at h={costs[0]:F3}, at 2h={costs[1]:F3} mm3");
        """)

    add(41, "Choose opening only when it preserves a thick core",
        "Compare an oriented scan's original 1 mm eroded core with a one-voxel opening. "
        "Restore the source candidate if the proposed opening removes any of that nominated core.",
        "The nominated core is an explicit occupancy-preservation constraint. Any core loss "
        "causes rollback, even when total volume change is small. This does not establish "
        "local thickness; it only guarantees the chosen core occupancy is retained by the edit.", "oriented", """
        using Voxels protectedCore = new(scan);
        protectedCore.Offset(-minWall);
        protectedCore.CalculateProperties(out float coreVolume, out _);
        if (coreVolume <= 0)
            throw new InvalidOperationException("Safety rejection: reconstruction has no measurable protected core; preservation would be vacuous.");
        using Voxels proposal = new(scan);
        proposal.DoubleOffset(-h, h);
        using Voxels lostCore = new(protectedCore);
        lostCore.BoolSubtract(proposal);
        lostCore.CalculateProperties(out float lostVolume, out _);
        bool preserveProposal = lostVolume == 0;
        using Voxels part = new(preserveProposal ? proposal : scan);
        Console.WriteLine($"Lost protected core: {lostVolume:F6} mm3; proposal selected={preserveProposal}");
        """)

    add(42, "Compare operation ordering explicitly",
        "Create close-then-open and open-then-close candidates from an XYZ envelope. "
        "Report the disagreement between the two outcomes and choose the ordering specified in the repair brief.",
        "Morphological operations do not generally commute. Computing both sequences teaches "
        "that equal net offsets are not interchangeable algorithms. This task explicitly selects "
        "close-then-open; the alternative is a diagnostic, not an automatically superior result.", "splats", """
        using Voxels part = new(scan);
        part.DoubleOffset(2 * h, -2 * h);
        part.DoubleOffset(-h, h);
        using Voxels alternative = new(scan);
        alternative.DoubleOffset(-h, h);
        alternative.DoubleOffset(2 * h, -2 * h);
        using Voxels disagreement = new(part);
        disagreement.BoolSubtract(alternative);
        using Voxels inverse = new(alternative);
        inverse.BoolSubtract(part);
        disagreement.BoolAdd(inverse);
        disagreement.CalculateProperties(out float disagreementVolume, out _);
        Console.WriteLine($"Ordering disagreement: {disagreementVolume:F3} mm3; close-then-open selected by brief");
        """)

    add(43, "Preserve a nominated small feature mask",
        "An oriented scan has a small designated feature in its lower-left X/Y quarter. "
        "Smooth the field while restoring that original region, and quantify the feature-mask volume.",
        "A feature mask prevents a general smoother from deleting a known region of interest. "
        "The quarter-space coordinates are supplied synthetic training assumptions. A real "
        "part needs an exact measured feature mask and its own fitment and strength evidence.", "oriented", """
        using Voxels part = new(scan);
        Vector3 span = hi - lo;
        Vector3 featureHi = new(lo.X + span.X / 4, lo.Y + span.Y / 4, hi.Z);
        using Voxels featureMask = Render(lib, new Box(lo, featureHi), bounds);
        using Voxels feature = new(scan);
        feature.BoolIntersect(featureMask);
        feature.CalculateProperties(out float featureVolume, out _);
        part.TripleOffset(h);
        part.BoolSubtract(featureMask);
        part.BoolAdd(feature);
        Console.WriteLine($"Protected synthetic feature-mask volume: {featureVolume:F3} mm3");
        """)

    add(44, "Separate solidification proposal from scan evidence",
        "A splat reconstruction may have an unobserved interior. Create an inset box proposal "
        "only as auxiliary geometry, compare its overlap with the scan, and keep the scan candidate unchanged.",
        "Filling a bounding box would fabricate unseen material. The auxiliary box is therefore "
        "a labelled hypothesis used for an overlap diagnostic, while the candidate remains the "
        "original splat reconstruction. Real solidification requires oriented or range evidence.", "splats", """
        using Voxels part = new(scan);
        Vector3 insetLo = lo + new Vector3(minWall);
        Vector3 insetHi = hi - new Vector3(minWall);
        if (insetLo.X >= insetHi.X || insetLo.Y >= insetHi.Y || insetLo.Z >= insetHi.Z)
            throw new InvalidOperationException("Input is too small for the auxiliary inset-box diagnostic.");
        using Voxels hypothesis = Render(lib, new Box(insetLo, insetHi), bounds);
        hypothesis.BoolIntersect(scan);
        hypothesis.CalculateProperties(out float overlapVolume, out _);
        Console.WriteLine($"Auxiliary box/scan overlap: {overlapVolume:F3} mm3; no unseen material inserted");
        """)

    add(45, "Diagnose residual islands without deleting them",
        "Close an XYZ envelope and isolate occupancy removed by an additional one-voxel opening. "
        "Report the residual as potential thin features or islands, preserving the closed candidate for review.",
        "Morphological residues can flag geometry worth examining, but do not identify connected "
        "components or distinguish noise from functional thin features. Deleting such residues "
        "without semantic evidence could destroy a legitimate part feature.", "splats", """
        using Voxels part = new(scan);
        part.DoubleOffset(h, -h);
        using Voxels openedDiagnostic = new(part);
        openedDiagnostic.DoubleOffset(-h, h);
        using Voxels residue = new(part);
        residue.BoolSubtract(openedDiagnostic);
        residue.CalculateProperties(out float residueVolume, out _);
        Console.WriteLine($"Potential thin-feature/island residue: {residueVolume:F3} mm3");
        Console.WriteLine("Residue was diagnosed, not deleted or labelled measurement noise.");
        """)

    add(136, "Fix uninitialized PicoGK objects",
        "Debug this PicoGK 2.3.0 code: `Voxels scan = new(); Lattice points = new(); "
        "points.AddSphere(Vector3.Zero, 1); scan.RenderLattice(points);`. It fails to compile. "
        "Use an explicit initialized headless Library, retain the imported scan, and add a labelled witness sphere.",
        "PicoGK 2.3.0 requires a Library for empty Voxels and Lattice construction. The complete "
        "program initializes one Library and supplies it to every native object, avoiding hidden "
        "viewer/global state. Radius is in millimetres, and the witness is intentional auxiliary geometry.", "mesh", """
        using Voxels part = new(scan);
        using Lattice witness = new(lib);
        Vector3 centre = (lo + hi) / 2;
        witness.AddSphere(centre, minWall / 2);
        using Voxels witnessVoxels = new(witness);
        part.BoolAdd(witnessVoxels);
        // All objects share the already initialized headless Library.
        Console.WriteLine("Explicit Library ownership fixes the missing-constructor error.");
        """, category="debug")

    add(137, "Fix the invented subtraction method",
        "Debug `voxels.Sub(vent);` in a PicoGK 2.3.0 powder-drain script. There is no Sub method. "
        "Use the real boolean API to subtract a vertical centreline cylinder that crosses both outer faces; "
        "do not claim it drains every possible disconnected chamber.",
        "BoolSubtract is the actual mutating difference API. A constant-radius, flat-capped "
        "Lattice beam supplies the cutter. Extending it beyond both faces avoids a blind cut; "
        "whether it touches every connected chamber is a separate powder-route test.", "mesh", """
        using Voxels part = new(scan);
        Vector3 centre = (lo + hi) / 2;
        float radius = minWall;
        using Lattice cutter = new(lib);
        cutter.AddBeam(new Vector3(centre.X, centre.Y, lo.Z - 2 * h), radius,
                       new Vector3(centre.X, centre.Y, hi.Z + 2 * h), radius, false);
        using Voxels vent = new(cutter);
        part.BoolSubtract(vent);
        Console.WriteLine("BoolSubtract cuts the cylinder; connected powder routes still require screening.");
        """, category="debug")

    add(138, "Fix inverted shell offsets",
        "Debug this shell attempt: `var inside = new Voxels(scan); inside.Offset(+1.0f); "
        "scan.BoolSubtract(inside);`. It erases the part. Construct a target 1 mm inward skin "
        "using an independent candidate and reject an empty interior.",
        "Positive Offset expands, so the proposed cutter contains the original part and subtracts "
        "it entirely. The interior cutter must be eroded by a negative distance. A shell "
        "intentionally creates a chamber; its drain and wall screens remain mandatory.", "mesh", """
        using Voxels interior = new(scan);
        interior.Offset(-minWall);
        if (interior.bIsEmpty()) throw new InvalidOperationException("No interior remains at the target wall distance.");
        using Voxels part = new(scan);
        part.BoolSubtract(interior);
        part.CalculateProperties(out float skinVolume, out _);
        // Negative offset builds the interior cutter instead of an exterior superset.
        Console.WriteLine($"Corrected inward skin volume: {skinVolume:F3} mm3");
        """, category="debug")

    add(139, "Fix SDF voxel-unit confusion",
        "Debug `ScalarField sdf = new(scan); sdf.bGetValue(p, out float d); "
        "Console.WriteLine($\"{d} mm\");`. The reported distance changes when voxel pitch changes. "
        "Correct the raw-value conversion and explicitly report inactive samples.",
        "ScalarField extracted from Voxels stores raw distance in voxel units. Multiplying an "
        "active raw value by lib.fVoxelSize gives millimetres. Ignoring the bGetValue result "
        "would turn missing narrow-band data into a fictitious zero-distance surface.", "oriented", """
        using Voxels part = new(scan);
        using ScalarField sdf = new(part);
        Vector3 query = (lo + hi) / 2;
        if (sdf.bGetValue(query, out float rawDistance))
        {
            float distanceMm = rawDistance * lib.fVoxelSize;
            Console.WriteLine($"Active SDF distance: {distanceMm:F3} mm");
        }
        else Console.WriteLine("No active SDF sample at the query point; distance unavailable.");
        """, category="debug")

    add(140, "Fix invented mesh and matrix types",
        "Debug `PolyMesh mesh = PolyMesh.LoadStl(input); VoxelMatrix grid = new(mesh); "
        "grid.SaveStl(output);` for PicoGK 2.3.0. Replace invented types with Mesh and Voxels, "
        "remesh the loaded scan, and report its triangle count.",
        "PicoGK 2.3.0 exposes Mesh, Voxels, ScalarField, Lattice and IImplicit. It does not "
        "expose those proposed PolyMesh/VoxelMatrix APIs. The complete loader reads STL with "
        "explicit units and library ownership; remeshing remains a resolution-dependent operation.", "mesh", """
        using Mesh sourceMesh = new(scan);
        if (sourceMesh.nTriangleCount() == 0) throw new InvalidOperationException("The loaded scan mesh is empty.");
        using Voxels part = new(sourceMesh);
        using Mesh candidateMesh = new(part);
        Console.WriteLine($"Source triangles: {sourceMesh.nTriangleCount()}");
        Console.WriteLine($"Voxel-round-trip triangles: {candidateMesh.nTriangleCount()}");
        // The common output stage saves a real Mesh and retains its review status.
        """, category="debug")

    add(141, "Fix implicit rendering that overwrites the scan",
        "Debug `vox.RenderImplicit(tpms, bounds);` called on an imported scan. It replaces the "
        "scan boundary with a whole implicit field. Demonstrate preserving the scan by rendering "
        "a separate analytic box mask and intersecting it with the candidate.",
        "RenderImplicit overwrites its target field. To retain imported boundaries, render "
        "the implicit into a separate Voxels object, then BoolIntersect, or use IntersectImplicit. "
        "A box mask makes the corrected object ownership and boolean semantics easy to verify.", "mesh", """
        using Voxels part = new(scan);
        Vector3 inset = new(h);
        using Voxels independentMask = Render(lib, new Box(lo + inset, hi - inset), bounds);
        part.BoolIntersect(independentMask);
        using Voxels outsideSource = new(part);
        outsideSource.BoolSubtract(scan);
        outsideSource.CalculateProperties(out float leakedVolume, out _);
        Console.WriteLine($"Material outside original scan after clipping: {leakedVolume:F6} mm3");
        """, category="debug")

    add(142, "Fix mismatched native libraries",
        "Debug `using var a = new Library(0.2f); using var b = new Library(0.2f); "
        "var part = new Voxels(a); var vent = new Voxels(b); part.BoolSubtract(vent);`. "
        "It throws despite equal voxel pitches. Show the single-library correction.",
        "Equal voxel size does not mean identical native library ownership. PicoGK boolean "
        "operations enforce Library identity. Construct the scan, cutter and result under "
        "the same explicit lib, and dispose child objects before disposing that Library.", "mesh", """
        using Voxels part = new(scan);
        Vector3 centre = (lo + hi) / 2;
        using Lattice cutter = new(lib);
        cutter.AddBeam(new Vector3(centre.X, centre.Y, lo.Z - h), minWall,
                       new Vector3(centre.X, centre.Y, hi.Z + h), minWall, false);
        using Voxels sameLibraryCutter = new(cutter);
        part.BoolSubtract(sameLibraryCutter);
        Console.WriteLine("Matching Library identity fixes the boolean-library mismatch.");
        """, category="debug")

    add(143, "Fix inconsistent physical units",
        "Debug STL ingestion that assumes metres and later uses millimetre wall targets: "
        "`Mesh.mshFromStlFile(input, Mesh.EStlUnit.M); interior.Offset(-1);`. "
        "The source contract specifies millimetres. Correct the import and report extents before any shelling.",
        "STL usually carries no authoritative unit metadata, so units must come from the "
        "input contract. Loading millimetre coordinates as metres introduces a factor of 1000. "
        "The complete mesh loader explicitly uses MM; extent reporting is a sanity check, not proof of units.", "mesh", """
        using Voxels part = new(scan);
        Vector3 extentMm = hi - lo;
        if (extentMm.X <= 0 || extentMm.Y <= 0 || extentMm.Z <= 0)
            throw new InvalidOperationException("Input has a non-positive physical extent.");
        Console.WriteLine($"Contract units: mm; extents: {extentMm}");
        using Voxels diagnosticCore = new(part);
        diagnosticCore.Offset(-minWall);
        Console.WriteLine($"One-millimetre erosion leaves material={!diagnosticCore.bIsEmpty()}");
        """, category="debug")

    add(144, "Fix beam radius versus diameter",
        "Debug `lattice.AddBeam(a, 1.0f, b, 1.0f, false);` intended to create a 1 mm "
        "diameter strut: it makes a 2 mm diameter strut. Add an explicitly labelled central vertical "
        "witness strut with correct radii and keep its process review status.",
        "AddBeam parameters are radii, not diameters. Half the requested diameter supplies "
        "the correct nominal beam size. The witness is vertical, but its junctions and final "
        "voxel geometry still require wall and overhang screening.", "mesh", """
        using Voxels part = new(scan);
        float diameter = minWall;
        float radius = diameter / 2;
        Vector3 centre = (lo + hi) / 2;
        using Lattice witness = new(lib);
        witness.AddBeam(new Vector3(centre.X, centre.Y, lo.Z), radius,
                        new Vector3(centre.X, centre.Y, hi.Z), radius, false);
        using Voxels witnessVoxels = new(witness);
        part.BoolAdd(witnessVoxels);
        Console.WriteLine($"Witness diameter={diameter:F3} mm; AddBeam radius={radius:F3} mm");
        """, category="debug")

    add(145, "Fix an opening described as crack closure",
        "Debug `vox.Offset(-r); vox.Offset(+r);` labelled close scan cracks. Explain why that "
        "is an opening and correct it to closing. Quantify introduced material for bridge review.",
        "Erosion followed by dilation is opening. Closing uses dilation followed by erosion; "
        "the sign order cannot be swapped because morphology does not commute. Added matter "
        "is measured explicitly so an unintended bridge is visible to the reviewer.", "splats", """
        using Voxels part = new(scan);
        float radius = h;
        part.Offset(radius);
        part.Offset(-radius);
        using Voxels addition = new(part);
        addition.BoolSubtract(scan);
        addition.CalculateProperties(out float addedVolume, out _);
        Console.WriteLine($"Correct closing inserted {addedVolume:F3} mm3; review bridges at radius {radius:F3} mm");
        """, category="debug")

    add(146, "Fix arbitrary detail removal near attachments",
        "Debug a global `scan.TripleOffset(2.0f);` that destroys a nominated 1 mm bottom "
        "attachment band. Use one-voxel smoothing away from a protected mask, restoring original interface occupancy.",
        "A large global morphology radius removes legitimate geometry along with noise. "
        "The correction ties the filter scale to voxel pitch and restores the explicitly "
        "nominated band. This protects source occupancy, not an unmeasured fitment tolerance.", "mesh", """
        using Voxels part = new(scan);
        using Voxels attachmentMask = Render(lib, new Box(lo, new Vector3(hi.X, hi.Y, lo.Z + minWall)), bounds);
        using Voxels attachment = new(scan);
        attachment.BoolIntersect(attachmentMask);
        part.TripleOffset(h);
        part.BoolSubtract(attachmentMask);
        part.BoolAdd(attachment);
        Console.WriteLine("Original attachment band restored; smoothing radius is one voxel.");
        """, category="debug")

    add(147, "Fix absent SDF samples interpreted as material",
        "Debug `if (field.fSignedDistance(p) <= 0) inside = true;` used on a sparse ScalarField "
        "converted from the scan. Unstored points return zero in this wrapper. Use bIsInside for occupancy "
        "and treat bGetValue failure as unavailable distance.",
        "ScalarField.fSignedDistance ignores bGetValue failure and therefore maps absent data "
        "to zero. The occupancy query belongs to Voxels.bIsInside; raw field sampling must "
        "retain an availability flag. This separates missing data from actual zero-level samples.", "oriented", """
        using Voxels part = new(scan);
        using ScalarField sparse = new(part);
        Vector3 query = hi + new Vector3(10 * h);
        bool occupancy = part.bIsInside(query);
        bool active = sparse.bGetValue(query, out float raw);
        Console.WriteLine($"Voxel occupancy at query={occupancy}; active SDF sample={active}");
        if (active) Console.WriteLine($"Available signed distance: {raw * h:F3} mm");
        else Console.WriteLine("Do not classify an unavailable SDF value as surface or material.");
        """, category="debug")

    add(148, "Fix degenerate-triangle normal evaluation",
        "Debug `Vector3 n = Vector3.Normalize(Vector3.Cross(b-a,c-a));` before an overhang "
        "screen. Degenerate triangles can produce NaNs. Add a scale-aware area check and count "
        "invalid triangles instead of treating them as passing.",
        "Normalizing a zero or near-zero cross product is invalid. Count degenerate facets "
        "before normalizing and reject any such mesh for review. The threshold is relative "
        "to voxel pitch, and absence of degeneracy alone does not establish a manifold mesh.", "mesh", """
        using Voxels part = new(scan);
        using Mesh mesh = new(part);
        int degenerate = 0;
        float minimumAreaTwice = h * h * 0.001f;
        for (int i = 0; i < mesh.nTriangleCount(); i++)
        {
            mesh.GetTriangle(i, out Vector3 a, out Vector3 b, out Vector3 c);
            Vector3 cross = Vector3.Cross(b - a, c - a);
            if (cross.Length() < minimumAreaTwice) { degenerate++; continue; }
            Vector3 normal = Vector3.Normalize(cross);
            if (!float.IsFinite(normal.Z)) throw new InvalidOperationException("Non-finite triangle normal.");
        }
        Console.WriteLine($"Degenerate triangle count: {degenerate}");
        if (degenerate != 0) throw new InvalidOperationException("Mesh contains invalid triangles.");
        """, category="debug")

    add(149, "Fix an incorrect overhang normal threshold",
        "Debug `if (normal.Z > 0.707f) unsupported++;` for a +Z build. It incorrectly flags "
        "upward faces. Count downward facets at or below 45 degrees to the platform above "
        "a two-voxel plate band; do not claim a facet-only screen proves support freedom.",
        "For an outward downward normal n, the facet angle to the platform is acos(-n.Z). "
        "At or below 45 degrees corresponds to n.Z <= -cos(45 degrees), while positive n.Z "
        "faces upward. Plate contact and disconnected build islands are separate considerations.", "mesh", """
        using Voxels part = new(scan);
        using Mesh mesh = new(part);
        int shallowDownward = 0;
        float limit = -MathF.Cos(MathF.PI / 4);
        for (int i = 0; i < mesh.nTriangleCount(); i++)
        {
            mesh.GetTriangle(i, out Vector3 a, out Vector3 b, out Vector3 c);
            Vector3 cross = Vector3.Cross(b - a, c - a);
            if (cross.LengthSquared() <= 1e-12f) throw new InvalidOperationException("Degenerate triangle in angle screen.");
            Vector3 normal = Vector3.Normalize(cross);
            float centroidZ = (a.Z + b.Z + c.Z) / 3;
            if (centroidZ > lo.Z + 2 * h && normal.Z <= limit) shallowDownward++;
        }
        Console.WriteLine($"Shallow downward facets above plate band: {shallowDownward}");
        """, category="debug")

    add(150, "Fix incorrect scalar-field distance scaling",
        "Debug custom reconstruction code that executes `field.SetValue(p, distanceMm);` and "
        "then reads `field.fSignedDistance(p)`. The retrieved distance is multiplied by voxel pitch. "
        "Demonstrate SetValue with voxel-unit storage in a separate diagnostic field, never reusing "
        "one sample as a global scan SDF.",
        "ScalarField's signed-distance wrapper multiplies stored raw values by voxel pitch. "
        "The correction divides millimetre distance by h before storage and checks the active "
        "sample's round trip. One diagnostic sample cannot define a valid global signed field.", "oriented", """
        using Voxels part = new(scan);
        using ScalarField diagnostic = new(lib);
        Vector3 sample = lib.vecVoxelsToMm(0, 0, 0);
        float distanceMm = 0.6f;
        diagnostic.SetValue(sample, distanceMm / h);
        if (!diagnostic.bGetValue(sample, out float raw))
            throw new InvalidOperationException("Diagnostic scalar sample was not stored.");
        float recoveredMm = raw * h;
        if (MathF.Abs(recoveredMm - distanceMm) > 1e-5f)
            throw new InvalidOperationException("Scalar distance unit round trip failed.");
        Console.WriteLine($"Diagnostic distance round trip: {recoveredMm:F3} mm");
        """, category="debug")

    assert len(rows) == 60
    assert [row["id"] for row in rows] == list(range(1, 46)) + list(range(136, 151))
    assert len({row["body"] for row in rows}) == 60
    assert sum(row["category"] == "scan" for row in rows) == 45
    assert sum(row["category"] == "debug" for row in rows) == 15
    return rows
