"""Independent admission of a Qwen proposal; it cannot certify its own output."""
import json
import math
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from contracts import unique


def expected(request):
    if request.get('user_allows_demo_assumptions') is not True:
        raise ValueError('This course supports explicitly authorised demos only')
    for name in ['triangles','boundary_edges','connected_surface_components']:
        if type(request.get(name)) is not int or request[name] < 0:
            raise ValueError('Integer independently audited mesh counts required')
    if 'surface_topology' in request and request['surface_topology'] != ('open' if request['boundary_edges'] else 'closed'):
        raise ValueError('Topology feature disagrees with audited boundary count')
    for name in ['mm_per_source_unit_assumed','voxel_mm_assumed']:
        v = request.get(name)
        if type(v) not in (int,float) or not math.isfinite(v) or v <= 0:
            raise ValueError('Explicit positive demo assumptions required')
    if not .1 <= request['mm_per_source_unit_assumed'] <= 2 or not .3 <= request['voxel_mm_assumed'] <= 1.2:
        raise ValueError('Outside the demo course')
    return dict(method='screened_poisson' if request['boundary_edges'] else 'direct_voxelization',
                target_faces=180000 if request['triangles']>1000000 else 300000, poisson_depth=9,
                mm_per_source_unit=request['mm_per_source_unit_assumed'], voxel_mm=request['voxel_mm_assumed'],
                manufacturing_qualified=False)


def admit(text, finish, request):
    if finish != 'stop':
        raise ValueError('Truncated scan proposal')
    plan = json.loads(text, object_pairs_hook=unique)
    target = expected(request)
    if not isinstance(plan,dict) or set(plan)!=set(target) or plan!=target:
        raise ValueError('Proposal disagrees with independently registered scan policy/assumptions')
    if type(plan['manufacturing_qualified']) is not bool:
        raise ValueError('Proposal cannot qualify manufacture')
    if type(plan['target_faces']) is not int or type(plan['poisson_depth']) is not int:
        raise ValueError('Integer reconstruction settings required')
    if any(type(plan[key]) not in (int,float) or not math.isfinite(plan[key]) for key in ['mm_per_source_unit','voxel_mm']):
        raise ValueError('Finite numeric scale and voxel step required')
    return plan


def execution_plan(text, finish, request):
    """Bound resource choices separately from the historical exact-preset score."""
    if finish != 'stop':
        raise ValueError('Truncated scan proposal')
    plan = json.loads(text, object_pairs_hook=unique)
    target = expected(request)
    if not isinstance(plan,dict) or set(plan)!=set(target):
        raise ValueError('Scan proposal schema')
    if type(plan['target_faces']) is not int or plan['target_faces'] not in (180000,300000):
        raise ValueError('Outside the two bounded reconstruction budgets')
    target['target_faces'] = plan['target_faces']
    if target != plan or type(plan['manufacturing_qualified']) is not bool or type(plan['poisson_depth']) is not int:
        raise ValueError('Wrong method, units, voxel step or qualification')
    if any(type(plan[key]) not in (int,float) or not math.isfinite(plan[key]) for key in ['mm_per_source_unit','voxel_mm']):
        raise ValueError('Finite numeric scale and voxel step required')
    return plan
