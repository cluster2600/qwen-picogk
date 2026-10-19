"""Generate separate synthetic API-discipline teachers from the validated recipe."""
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    recipe = WORK / 'data/corrective-008/author.py'
    prior = json.loads((recipe.parent / 'cases.json').read_text())
    assert sha(recipe) == prior['author_sha256']
    source = recipe.read_text()
    anchor = "    exec(compile(function,str(Path(__file__)),'exec'),old.__dict__)"
    assert source.count(anchor) == 1
    # Separate synthetic observations, while retaining the established geometric oracles.
    injection = "    function=function.replace('[[.4,-.6,1.],[-1.,1.4,.2],[1.4,-.2,-.4],[-.6,-1.,.6]]','[[.8,-.4,.6],[-.8,1.,.4],[1.,-.6,-.2],[-.4,-.8,.8]]').replace(\"ident=f'state-\",\"ident=f'api-\")\n"
    source = source.replace(anchor, injection + anchor)
    namespace = {'__name__': 'api_recipe', '__file__': str(Path(__file__))}
    exec(compile(source, str(Path(__file__)), 'exec'), namespace)
    namespace['main']()
    manifest = json.loads((ROOT / 'cases.json').read_text())
    rows = [json.loads(line) for line in (ROOT / 'train.jsonl').read_text().splitlines()]
    for row, case in zip(rows, manifest['cases']):
        path = ROOT / case['source']
        code = path.read_text()
        # Train exact constructor types and one reusable same-solid export routine.
        code = re.sub(r'using (Library|Lattice|Voxels|Mesh) (\w+)\s*=\s*new\(',
                      lambda m: f'using {m[1]} {m[2]} = new {m[1]}(', code)
        if '        part.CalculateProperties' in code:
            start = code.index('        part.CalculateProperties')
            end = code.index('\n    }\n', start)
            body = code[start:end].replace('args[1]', 'output')
            code = code[:start] + '        Export(part, lib, args[1]);' + code[end:]
            boundary = code.index('\n}\n')
            code = code[:boundary] + '\n    private static void Export(Voxels part, Library lib, string output)\n    {\n' + body + '\n    }\n' + code[boundary:]
        # Every implicit helper is nested in the same complete Program declaration.
        if '\npublic sealed class ' in code:
            boundary = code.index('\npublic sealed class ')
            program, helpers = code[:boundary], code[boundary:]
            assert program.rstrip().endswith('}')
            code = program.rstrip()[:-1] + '\n' + helpers + '\n}\n'
        assert 'System.Text.Json.Serialization' not in code
        assert '.Xyz' not in code and 'using Voxels[]' not in code
        path.write_text(code)
        case['source_sha256'] = sha(path)
        row['messages'][0]['content'] += (' Use only the listed namespaces and exact public APIs. '
            'Use explicit constructor types, include all helpers in Program, never assign a using variable, '
            'and export through one static routine taking the actual final Voxels. '
            'Malformed/nonfinite/zero-normal observations must fail before writing geometry. '
            'Report fields must match the requested schema exactly.')
        row['messages'][1]['content'] = ('All helper state is declared and every API receiver and argument type is explicit. '
            'The shared export routine preserves the actual solid; synthetic software/geometry evidence does not authorize manufacture.\n\n'
            '```csharp\n' + code + '```')
    assert len(rows) == manifest['count'] == 48
    assert len({case['source_sha256'] for case in manifest['cases']}) >= 40
    assert len({case['source_sha256'] for case in manifest['cases']} &
               {case['source_sha256'] for case in prior['cases']}) <= 4
    (ROOT / 'train.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False, separators=(',', ':')) + '\n' for row in rows))
    manifest.update(author_sha256=sha(Path(__file__)), train_sha256=sha(ROOT / 'train.jsonl'),
        reused_implementation_recipe_sha256=sha(recipe),
        implementation_changes='Explicit constructor types, nested complete helpers, shared static same-solid export, strict namespace/schema/parser teaching; separate synthetic observations.',
        native_validation='pending; no training eligibility until independent native proof', final_contents_read=False)
    (ROOT / 'cases.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'cases': len(rows), 'train_sha256': manifest['train_sha256']}))


if __name__ == '__main__':
    main()
