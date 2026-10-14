"""Admit only the literal six-beam C# subset and independently required geometry."""
import math
import re

NUMBER = r'(-?\d+(?:\.\d+)?)f'
VECTOR = r'new\s+Vector3\(\s*'+NUMBER+r'\s*,\s*'+NUMBER+r'\s*,\s*'+NUMBER+r'\s*\)'
BEAM = re.compile(r'lattice\.AddBeam\(\s*'+VECTOR+r'\s*,\s*'+NUMBER+r'\s*,\s*'+VECTOR+r'\s*,\s*'+NUMBER+r'\s*,\s*(true|false)\s*\);')


def admitted(text, finish, request):
    if finish != 'stop':
        raise ValueError('Model code did not reach EOS')
    beams, position = [], 0
    for match in BEAM.finditer(text):
        if text[position:match.start()].strip():
            raise ValueError('Code outside the literal AddBeam subset')
        values = [float(v) for v in match.groups()[:8]]
        if not all(math.isfinite(v) and abs(v) <= 32 for v in values) or not all(0.25 <= values[i] <= 5 for i in (3, 7)):
            raise ValueError('Beam coordinates or radii outside witness bounds')
        beams.append(values+[match[9] == 'true']); position = match.end()
    if text[position:].strip() or not 1 <= len(beams) <= 6:
        raise ValueError('Invalid or empty beam program')
    expected = [request['vertices_mm'][a]+[request['start_diameter_mm']/2]+
                request['vertices_mm'][b]+[request['end_diameter_mm']/2]+[True] for a,b in request['edges']]
    signature = lambda items: sorted((min(tuple(b[:4]),tuple(b[4:8])),max(tuple(b[:4]),tuple(b[4:8])),b[8]) for b in items)
    if signature(beams) != signature(expected):
        raise ValueError('Missing, duplicated or dimensionally different beam')
    return beams
