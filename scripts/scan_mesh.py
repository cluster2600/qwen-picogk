"""Private scan-demo geometry worker. No raw geometry or derived mesh belongs in Git."""
import argparse
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fresh(path):
    path = Path(path).resolve()
    if path.exists():
        raise ValueError('Use a new private output directory')
    for parent in path.parents:
        if (parent/'.git').exists() and path.relative_to(parent).parts[0] != 'work':
            raise ValueError('Scan derivatives inside Git must stay under ignored work/')
    path.mkdir(parents=True, mode=0o700)
    return path


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def read_obj(path):
    # Reuse the position/triangle intake contract from the private 935 study.
    import numpy as np
    vertices, faces = [], []
    if Path(path).stat().st_size > 256*1024**2:
        raise ValueError('Demo input exceeds 256 MiB')
    with Path(path).open() as stream:
        for line in stream:
            f = line.split()
            if not f or f[0].startswith('#'):
                continue
            if f[0] == 'v':
                if len(f) != 4:
                    raise ValueError('Position-only vertices required')
                vertices.append([float(x) for x in f[1:]])
            elif f[0] == 'f':
                if len(f) != 4:
                    raise ValueError('Triangular OBJ required; no implicit polygon triangulation')
                ids = [int(x.split('/')[0]) for x in f[1:]]
                if 0 in ids:
                    raise ValueError('OBJ indices cannot be zero')
                faces.append([i-1 if i > 0 else len(vertices)+i for i in ids])
            elif f[0] not in {'vn','vt','o','g','s','mtllib','usemtl'}:
                raise ValueError('Unsupported OBJ record')
    v, f = np.asarray(vertices, dtype=float), np.asarray(faces, dtype=int)
    if v.ndim != 2 or v.shape[1] != 3 or not np.isfinite(v).all():
        raise ValueError('Finite vertices required')
    if f.ndim != 2 or f.shape[1] != 3 or f.min() < 0 or f.max() >= len(v):
        raise ValueError('Valid triangular faces required')
    # Material declarations are ignored; no referenced file is opened.
    return v, f


def inspect(source, output):
    import numpy as np
    import trimesh
    sha = digest(source)
    v, f = read_obj(source)
    t = v[f]
    good = np.linalg.norm(np.cross(t[:,1]-t[:,0], t[:,2]-t[:,0]), axis=1) > 0
    centre = v.mean(0)
    _, axes = np.linalg.eigh((v-centre).T@(v-centre)/len(v))
    axes = axes[:, ::-1]
    if np.linalg.det(axes) < 0:
        axes[:,2] *= -1
    pose = (v-centre)@axes
    mesh = trimesh.Trimesh(pose, f[good], process=False)
    _, counts = np.unique(mesh.edges_sorted, axis=0, return_counts=True)
    labels = trimesh.graph.connected_component_labels(mesh.face_adjacency, node_count=len(mesh.faces))
    result = dict(input_sha256=sha, vertices=len(v), triangles=len(f),
                  prepared_triangles=int(good.sum()), zero_area_faces_removed=int((~good).sum()),
                  boundary_edges=int((counts == 1).sum()), nonmanifold_edges=int((counts > 2).sum()),
                  connected_surface_components=len(np.unique(labels)), winding_consistent=bool(mesh.is_winding_consistent),
                  bounds_source_units=mesh.bounds.tolist(), units_confirmed=False,
                  rigid_pose_only=True, source_centre=centre.tolist(), source_to_pose_axes=axes.tolist(),
                  scale_verified=False, back_registration_verified=False)
    output = fresh(output)
    mesh.export(output/'prepared.stl')
    np.savez_compressed(output/'prepared.npz', vertices=pose, faces=f[good])
    result['prepared_sha256'] = digest(output/'prepared.stl')
    result['prepared_npz_sha256'] = digest(output/'prepared.npz')
    if digest(source) != sha:
        raise ValueError('Source changed during intake')
    save(output/'intake.json', result)
    return result


def pymesh_intake(intake, cleaned, output):
    """Independently prove that PyMesh retained the exact acquired surface."""
    import numpy as np
    import trimesh
    intake, cleaned = Path(intake), Path(cleaned)
    metadata = json.loads((intake/'intake.json').read_text())
    receipt = json.loads((cleaned/'pymesh.json').read_text())
    if (digest(intake/'prepared.npz') != metadata['prepared_npz_sha256'] or
            receipt['input_npz_sha256'] != metadata['prepared_npz_sha256'] or
            digest(cleaned/'cleaned.npz') != receipt['output_npz_sha256'] or
            receipt['duplicate_vertex_tolerance'] != 0):
        raise ValueError('PyMesh cleanup binding or exact-weld policy mismatch')
    with np.load(intake/'prepared.npz', allow_pickle=False) as src:
        vertices, faces = src['vertices'], src['faces']
    with np.load(cleaned/'cleaned.npz', allow_pickle=False) as data:
        v, f = data['vertices'], data['faces']
        vi, fi = data['input_vertex_indices'], data['input_face_indices']
    if (v.ndim != 2 or v.shape[1] != 3 or not np.isfinite(v).all() or
            f.ndim != 2 or f.shape[1] != 3 or not len(f) or f.dtype.kind not in 'iu' or
            f.min() < 0 or f.max() >= len(v) or vi.dtype.kind not in 'iu' or fi.dtype.kind not in 'iu' or
            vi.shape != (len(v),) or fi.shape != (len(f),) or
            vi.min() < 0 or vi.max() >= len(vertices) or fi.min() < 0 or fi.max() >= len(faces)):
        raise ValueError('Invalid PyMesh coordinates, faces or source maps')
    if not np.array_equal(v, vertices[vi]) or not np.array_equal(v[f], vertices[faces[fi]]):
        raise ValueError('PyMesh moved vertices or changed retained oriented triangles')
    # Verify complete surface coverage, allowing only exact duplicate faces.
    _, canonical = np.unique(vertices, axis=0, return_inverse=True)
    corners = canonical[faces]
    before, groups = np.unique(np.sort(corners, axis=1), axis=0, return_inverse=True)
    parity = ((corners[:,0] > corners[:,1]).astype(np.uint8) +
              (corners[:,0] > corners[:,2]).astype(np.uint8) +
              (corners[:,1] > corners[:,2]).astype(np.uint8)) % 2
    low, high = np.ones(len(before), dtype=np.uint8), np.zeros(len(before), dtype=np.uint8)
    np.minimum.at(low, groups, parity)
    np.maximum.at(high, groups, parity)
    if np.any(low != high):
        raise ValueError('Opposing acquired duplicate orientations need explicit review')
    after = np.unique(np.sort(canonical[vi][f], axis=1), axis=0)
    if not np.array_equal(before, after) or len(after) != len(f):
        raise ValueError('PyMesh removed acquired surface or left duplicate faces')
    mesh = trimesh.Trimesh(v, f, process=False)
    if not np.all(mesh.area_faces > 0):
        raise ValueError('PyMesh left zero-area faces')
    _, counts = np.unique(mesh.edges_sorted, axis=0, return_counts=True)
    labels = trimesh.graph.connected_component_labels(mesh.face_adjacency, node_count=len(f))
    if np.any(counts > 2) or not mesh.is_winding_consistent:
        raise ValueError('Cleaned scan is nonmanifold or inconsistently oriented')
    output = fresh(output)
    mesh.export(output/'prepared.stl')
    np.savez_compressed(output/'prepared.npz', vertices=v, faces=f)
    metadata.update(vertices=len(v), triangles=len(f), prepared_triangles=len(f),
                    boundary_edges=int((counts == 1).sum()), nonmanifold_edges=int((counts > 2).sum()),
                    connected_surface_components=len(np.unique(labels)), winding_consistent=True,
                    prepared_sha256=digest(output/'prepared.stl'), prepared_npz_sha256=digest(output/'prepared.npz'),
                    pymesh_cleanup=receipt, cleanup_preserves_acquired_surface=True,
                    cleanup_vertices_moved=False, cleanup_holes_filled=False)
    save(output/'intake.json', metadata)
    return metadata


def reconstruct(intake, plan, output):
    import numpy as np
    import pymeshlab
    import trimesh
    from scan_policy import execution_plan
    metadata = json.loads((Path(intake)/'intake.json').read_text())
    binding = json.loads(Path(plan).read_text())
    if any(binding['request'][key] != metadata[key] for key in ['triangles','boundary_edges','connected_surface_components']):
        raise ValueError('Model request differs from independently audited scan')
    plan = execution_plan(binding['raw_response'], binding['finish_reason'], binding['request'])
    if digest(Path(intake)/'prepared.stl') != metadata['prepared_sha256']:
        raise ValueError('Prepared mesh hash mismatch')
    if digest(Path(intake)/'prepared.npz') != metadata['prepared_npz_sha256']:
        raise ValueError('Prepared coordinates hash mismatch')
    output = fresh(output)
    src = np.load(Path(intake)/'prepared.npz')
    vertices, faces = src['vertices']*plan['mm_per_source_unit'], src['faces']
    if plan['method'] == 'screened_poisson':
        ms = pymeshlab.MeshSet()
        ms.add_mesh(pymeshlab.Mesh(vertices, faces))
        ms.apply_filter('meshing_decimation_quadric_edge_collapse', targetfacenum=plan['target_faces'],
                        preserveboundary=True, preservenormal=True, preservetopology=False, autoclean=True)
        ms.apply_filter('compute_normal_per_face')
        ms.apply_filter('compute_normal_per_vertex')
        ms.apply_filter('generate_surface_reconstruction_screened_poisson', depth=plan['poisson_depth'],
                        fulldepth=5, cgdepth=0, scale=1.1, samplespernode=1.5, pointweight=4.,
                        iters=8, confidence=False, preclean=True, threads=8)
        m = ms.current_mesh()
        mesh = trimesh.Trimesh(m.vertex_matrix(), m.face_matrix(), process=False)
    else:
        mesh = trimesh.Trimesh(vertices, faces, process=False)
    components = mesh.split(only_watertight=False)
    # Only generated Poisson fragments are dust candidates; acquired closed meshes stay intact.
    threshold = max(100, len(mesh.faces)//1000) if plan['method']=='screened_poisson' else 0
    kept = [m for m in components if len(m.faces) >= threshold]
    if not kept:
        raise ValueError('Reconstruction contains no retained surface')
    mesh = trimesh.util.concatenate(kept)
    mesh.export(output/'reconstructed.stl')
    save(output/'reconstruction.json', dict(method=plan['method'], plan=plan,
         input_sha256=metadata['input_sha256'], prepared_sha256=metadata['prepared_sha256'],
         output_sha256=digest(output/'reconstructed.stl'), triangles=len(mesh.faces),
         dust_faces_removed=sum(len(m.faces) for m in components if len(m.faces) < threshold),
         watertight=bool(mesh.is_watertight), winding_consistent=bool(mesh.is_winding_consistent),
         hole_closures_are_hypotheses=plan['method']=='screened_poisson', manufacturing_qualified=False))
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume <= 0:
        raise ValueError('Reconstructed input is not a closed positive oriented surface')


def surface_distance(source, target, seed):
    import numpy as np
    import trimesh
    rng = np.random.default_rng(seed)
    ids = rng.choice(len(source.faces), 2000, p=source.area_faces/source.area)
    uv = rng.random((2000,2))
    uv[uv.sum(1)>1] = 1-uv[uv.sum(1)>1]
    t = source.triangles[ids]
    points = t[:,0]+uv[:,:1]*(t[:,1]-t[:,0])+uv[:,1:]*(t[:,2]-t[:,0])
    _, d, _ = trimesh.proximity.closest_point(target, points)
    return dict(samples=2000, seed=seed, rms_mm=float(np.sqrt(np.mean(d*d))),
                p95_mm=float(np.quantile(d,.95)), sampled_max_mm=float(d.max()),
                method='area_uniform_points_to_triangles; sampled extrema, not exact Hausdorff')


def inspect_closed(source, output):
    import numpy as np
    import struct
    import trimesh
    with Path(source).open('rb') as stream:
        header=stream.read(84)
    if len(header)!=84 or Path(source).stat().st_size!=84+50*struct.unpack('<I',header[80:84])[0]:
        raise ValueError('Exact binary STL required')
    mesh=trimesh.load(source,force='mesh',process=True)
    _,counts=np.unique(mesh.edges_sorted,axis=0,return_counts=True)
    labels=trimesh.graph.connected_component_labels(mesh.face_adjacency,node_count=len(mesh.faces))
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume<=0:
        raise ValueError('Closed positive oriented envelope required')
    result=dict(input_sha256=digest(source),triangles=len(mesh.faces),boundary_edges=int((counts==1).sum()),
                connected_surface_components=len(np.unique(labels)),nonmanifold_edges=int((counts>2).sum()))
    if result['nonmanifold_edges']:
        raise ValueError('Nonmanifold envelope')
    output=fresh(output);save(output/'closed-intake.json',result)
    return result


def dominant_demo(intake, output):
    """Isolate the dominant acquired surface for a demo; retain unregistered fragments."""
    import numpy as np
    import trimesh
    intake=Path(intake)
    metadata=json.loads((intake/'intake.json').read_text())
    if digest(intake/'prepared.npz')!=metadata['prepared_npz_sha256']:
        raise ValueError('Prepared coordinates hash mismatch')
    data=np.load(intake/'prepared.npz')
    mesh=trimesh.Trimesh(data['vertices'],data['faces'],process=False)
    labels=trimesh.graph.connected_component_labels(mesh.face_adjacency,node_count=len(mesh.faces))
    areas=np.bincount(labels,weights=mesh.area_faces)
    selected=labels==int(areas.argmax())
    fraction=float(areas.max()/areas.sum())
    if fraction<.95:
        raise ValueError('No 95-percent dominant surface; unregistered assembly cannot be simplified automatically')
    output=fresh(output)
    kept=trimesh.Trimesh(mesh.vertices,mesh.faces[selected],process=False)
    kept.export(output/'prepared.stl')
    np.savez_compressed(output/'prepared.npz',vertices=mesh.vertices,faces=mesh.faces[selected])
    if np.any(~selected):
        trimesh.Trimesh(mesh.vertices,mesh.faces[~selected],process=False).export(output/'unregistered-fragments.stl')
    np.save(output/'retained_prepared_face_indices.npy',np.flatnonzero(selected))
    _,counts=np.unique(kept.edges_sorted,axis=0,return_counts=True)
    metadata.update(triangles=int(selected.sum()),prepared_triangles=int(selected.sum()),
                    vertices=len(np.unique(kept.faces)),boundary_edges=int((counts==1).sum()),
                    connected_surface_components=1,prepared_sha256=digest(output/'prepared.stl'),
                    prepared_npz_sha256=digest(output/'prepared.npz'),
                    reference_scope='dominant acquired surface; not the complete original OBJ',
                    retained_surface_area_fraction=fraction,omitted_triangles=int((~selected).sum()),
                    omitted_fragments_are_not_classified_as_dust=True,back_registration_verified=False)
    save(output/'intake.json',metadata)
    return metadata


def assess(intake, native, output):
    import numpy as np
    import pymeshlab
    import trimesh
    metadata = json.loads((Path(intake)/'intake.json').read_text())
    receipt = json.loads((Path(native)/'native.json').read_text())
    if digest(Path(intake)/'prepared.npz') != metadata['prepared_npz_sha256']:
        raise ValueError('Prepared coordinates hash mismatch')
    path = Path(native)/'candidate.stl'
    if digest(path) != receipt['output_sha256']:
        raise ValueError('Native mesh hash mismatch')
    src = np.load(Path(intake)/'prepared.npz')
    scan = trimesh.Trimesh(src['vertices']*receipt['mm_per_source_unit_assumed'], src['faces'], process=False)
    mesh = trimesh.load(path, force='mesh', process=True)
    topology = {}
    for filter_name, key in [('compute_selection_by_self_intersections_per_face','self_intersection_faces'),
                             ('compute_selection_by_non_manifold_edges_per_face','nonmanifold_edge_faces'),
                             ('compute_selection_by_non_manifold_per_vertex','nonmanifold_vertices')]:
        ms = pymeshlab.MeshSet(); ms.load_new_mesh(str(path)); ms.apply_filter(filter_name)
        topology[key] = int(ms.current_mesh().selected_vertex_number() if key.endswith('vertices') else ms.current_mesh().selected_face_number())
    a, b = surface_distance(scan,mesh,9931414), surface_distance(mesh,scan,9931415)
    components = len(mesh.split(only_watertight=False))
    checks = dict(watertight=bool(mesh.is_watertight), winding_consistent=bool(mesh.is_winding_consistent),
                  one_component=components==1, positive_volume=bool(mesh.volume>0),
                  no_zero_area_faces=bool(np.all(mesh.area_faces>0)), topology_clean=not any(topology.values()),
                  scan_coverage=a['p95_mm']<=1.5 and a['sampled_max_mm']<=10,
                  reconstructed_surface=b['p95_mm']<=3 and b['sampled_max_mm']<=15)
    output = fresh(output)
    result = dict(status='demo_geometry_passed' if all(checks.values()) else 'demo_geometry_rejected',
                  checks=checks, topology=topology, components=components, triangles=len(mesh.faces),
                  volume_mm3_assumed=float(mesh.volume), bounds_mm_assumed=mesh.bounds.tolist(),
                  scan_to_native=a, native_to_open_scan=b, native_sha256=digest(path),
                  source_sha256=metadata['input_sha256'], manufacturing_qualified=False,
                  supports_prepared=False, scale_verified=False, rotation_authorized=False)
    save(output/'quality.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['inspect','inspect_closed','dominant_demo','pymesh_intake','reconstruct','assess'])
    parser.add_argument('paths', nargs='+', type=Path)
    args = parser.parse_args()
    if len(args.paths) != (2 if args.stage in ('inspect','inspect_closed','dominant_demo') else 3):
        parser.error('inspect OBJ NEW_DIR | reconstruct INTAKE PLAN NEW_DIR | assess INTAKE NATIVE NEW_DIR')
    result = globals()[args.stage](*args.paths)
    print(json.dumps(result, allow_nan=False))
