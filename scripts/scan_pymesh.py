"""PyMesh worker for the pinned, offline Linux image (Python 3.6 compatible)."""
import argparse
import json
from pathlib import Path
import platform

from scan_mesh import digest, fresh, save


def prepare(intake, output):
    import numpy as np
    import pymesh
    intake = Path(intake)
    metadata = json.loads((intake/'intake.json').read_text())
    path = intake/'prepared.npz'
    if digest(path) != metadata['prepared_npz_sha256']:
        raise ValueError('Prepared coordinates hash mismatch before PyMesh')
    with np.load(str(path), allow_pickle=False) as data:
        vertices, faces = data['vertices'], data['faces']
    if (vertices.ndim != 2 or vertices.shape[1] != 3 or not np.isfinite(vertices).all() or
            faces.ndim != 2 or faces.shape[1] != 3 or not len(faces) or
            faces.dtype.kind not in 'iu' or faces.min() < 0 or faces.max() >= len(vertices)):
        raise ValueError('Finite indexed triangular mesh required')
    mesh = pymesh.form_mesh(vertices, faces)
    mesh, merged = pymesh.remove_duplicated_vertices(mesh, 0.0)
    # Compose provenance through exact welding and subsequent isolated removal.
    index_map = np.asarray(merged['index_map'], dtype=np.int64).reshape(-1)
    origins = np.full(mesh.num_vertices, len(vertices), dtype=np.int64)
    np.minimum.at(origins, index_map, np.arange(len(vertices)))
    mesh, deduplicated = pymesh.remove_duplicated_faces(mesh)
    if not mesh.num_faces:
        raise ValueError('PyMesh cleanup removed the entire acquired surface')
    face_origins = np.asarray(deduplicated['ori_face_index'], dtype=np.int64).reshape(-1)
    mesh, isolated = pymesh.remove_isolated_vertices(mesh)
    origins = origins[np.asarray(isolated['ori_vertex_index'], dtype=np.int64).reshape(-1)]
    output = fresh(output)
    np.savez_compressed(str(output/'cleaned.npz'), vertices=mesh.vertices, faces=mesh.faces,
                        input_vertex_indices=origins, input_face_indices=face_origins)
    result = dict(stage='exact_mesh_cleanup', input_npz_sha256=metadata['prepared_npz_sha256'],
                  output_npz_sha256=digest(output/'cleaned.npz'), pymesh_version=pymesh.__version__,
                  python_version=platform.python_version(), numpy_version=np.__version__,
                  duplicate_vertex_tolerance=0.0, input_vertices=len(vertices), input_faces=len(faces),
                  output_vertices=mesh.num_vertices, output_faces=mesh.num_faces,
                  merged_vertices=int(merged['num_vertex_merged']),
                  removed_isolated_vertices=int(isolated['num_vertex_removed']),
                  manufacturing_qualified=False)
    save(output/'pymesh.json', result)
    return result


def audit(native, output):
    import numpy as np
    import pymesh
    native = Path(native)
    receipt = json.loads((native/'native.json').read_text())
    path = native/'candidate.stl'
    before = digest(path)
    if before != receipt['output_sha256']:
        raise ValueError('Native STL hash mismatch before PyMesh audit')
    mesh = pymesh.load_mesh(str(path))
    if (not mesh.num_faces or not np.isfinite(mesh.vertices).all() or mesh.faces.shape[1] != 3):
        raise ValueError('Finite nonempty triangular native mesh required')
    # STL triangle soup repeats vertex coordinates: weld exactly for adjacency.
    mesh, _ = pymesh.remove_duplicated_vertices(mesh, 0.0)
    pairs = np.asarray(pymesh.detect_self_intersection(mesh))
    if pairs.size and (pairs.ndim != 2 or pairs.shape[1] != 2):
        raise ValueError('Unexpected PyMesh intersection report')
    if digest(path) != before:
        raise ValueError('Native STL changed during PyMesh audit')
    result = dict(stage='native_intersection_audit', input_sha256=before,
                  pymesh_version=pymesh.__version__, python_version=platform.python_version(),
                  self_intersection_pairs=int(len(pairs)), repair_performed=False,
                  manufacturing_qualified=False)
    output = fresh(output)
    save(output/'pymesh.json', result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['prepare', 'audit'])
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    print(json.dumps(globals()[args.stage](args.input, args.output), allow_nan=False))
