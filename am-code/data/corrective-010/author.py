"""Author independent faulty-input repair lessons from synthetic native recipes."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    recipe = WORK / 'data/corrective-009/author.py'
    prior = json.loads((recipe.parent / 'cases.json').read_text())
    assert sha(recipe) == prior['author_sha256']
    source = recipe.read_text()
    old = '[[.8,-.4,.6],[-.8,1.,.4],[1.,-.6,-.2],[-.4,-.8,.8]]'
    new = '[[-.2,.8,.4],[.6,-.8,1.],[-.8,.2,-.6],[1.,.4,-.2]]'
    assert source.count(old) == 1
    source = source.replace(old, new).replace("ident=f'api-", "ident=f'repair-")
    namespace = {'__name__': 'repair_recipe', '__file__': str(Path(__file__))}
    exec(compile(source, str(Path(__file__)), 'exec'), namespace)
    namespace['main']()
    manifest = json.loads((ROOT / 'cases.json').read_text())
    rows = [json.loads(line) for line in (ROOT / 'train.jsonl').read_text().splitlines()]
    for number, (row, case) in enumerate(zip(rows, manifest['cases'])):
        path = ROOT / case['source']
        code = path.read_text()
        # Reorder the shared export boundary explicitly; disposal still belongs to Main.
        code = code.replace('Export(part, lib, args[1])', 'WriteFinal(args[1], lib, part)')
        code = code.replace('private static void Export(Voxels part, Library lib, string output)',
                            'private static void WriteFinal(string output, Library lib, Voxels part)')
        path.write_text(code)
        case['source_sha256'] = sha(path)
        faulty = code.replace('using System.Text.Json;\n',
                              'using System.Text.Json;\nusing System.Text.Json.Serialization;\n', 1)
        if 'using Voxels part = new Voxels(' in faulty:
            faulty = faulty.replace('using Voxels part = new Voxels(', 'using Voxels[] part = new Voxels(', 1)
        elif 'float.TryParse' in faulty:
            faulty = faulty.replace('float.TryParse', 'float.ParseUnchecked', 1)
        else:
            faulty = faulty.replace('JsonSerializer.Serialize', 'JsonSerializer.Serialise', 1)
        assert faulty != code and 'System.Text.Json.Serialization' not in code
        row['messages'][0]['content'] += ('\nIndependently authored faulty input follows. Repair every compile/API/schema/input-validation defect, '
            'retain all dimensions and controls stated above, and return one complete C# program. '
            'The extra serialization namespace is outside this exercise allowlist and must be removed. '
            'Never use a using declaration for an array; exact PicoGK receiver and constructor types matter.\n'
            '```csharp\n' + faulty + '```')
        row['messages'][1]['content'] = ('The correction uses only the specified namespaces, typed PicoGK receivers and complete owned helper state. '
            'All requested malformed-input and same-solid export checks remain explicit; these synthetic checks do not authorize manufacture.\n\n'
            '```csharp\n' + code + '```')
        case['synthetic_faulty_input_sha256'] = hashlib.sha256(faulty.encode()).hexdigest()
        case['synthetic_fault_origin'] = 'mechanical mutation of independently authored teacher; never a captured model response'
    assert len(rows) == manifest['count'] == 48
    assert len({row['messages'][0]['content'] for row in rows}) == 48
    (ROOT / 'train.jsonl').write_text(''.join(json.dumps(row, ensure_ascii=False, separators=(',', ':'))+'\n' for row in rows))
    manifest.update(author_sha256=sha(Path(__file__)), train_sha256=sha(ROOT/'train.jsonl'),
        reused_repair_recipe_sha256=sha(recipe),
        implementation_changes='Separate synthetic observations, explicit reordered shared export boundary, independently mutated faulty-input repair prompts; no captured answers or final data.',
        native_validation='pending; no eligibility before native proof', final_contents_read=False)
    (ROOT/'cases.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'cases':48,'train_sha256':manifest['train_sha256']}))


if __name__ == '__main__':
    main()
