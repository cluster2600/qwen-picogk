"""Author independent direct tasks with explicit field/domain/receiver construction."""
import hashlib
import json
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    recipe=WORK/'data/corrective-009/author.py'
    prior=json.loads((recipe.parent/'cases.json').read_text())
    assert sha(recipe)==prior['author_sha256']
    source=recipe.read_text()
    old='[[.8,-.4,.6],[-.8,1.,.4],[1.,-.6,-.2],[-.4,-.8,.8]]'
    assert source.count(old)==1
    source=source.replace(old,'[[.4,.6,-.8],[-.6,-.4,.8],[.8,-1.,.2],[-1.,.8,-.4]]').replace("ident=f'api-","ident=f'field-")
    ns={'__name__':'field_recipe','__file__':str(Path(__file__))}
    exec(compile(source,str(Path(__file__)),'exec'),ns);ns['main']()
    manifest=json.loads((ROOT/'cases.json').read_text())
    rows=[json.loads(x) for x in (ROOT/'train.jsonl').read_text().splitlines()]
    changed=0
    for row,case in zip(rows,manifest['cases']):
        path=ROOT/case['source'];code=path.read_text()
        pattern=r'using Voxels part = new Voxels\(lib,(.+),new BBox3\((.+)\)\);'
        code,n=re.subn(pattern,lambda m:'IImplicit field = '+m[1]+';\n        BBox3 domain = new BBox3('+m[2]+');\n        using Voxels part = new Voxels(lib,field,domain);',code)
        changed+=n
        code=code.replace('Export(part, lib, args[1])','SaveSolid(part, args[1], lib)').replace('private static void Export(Voxels part, Library lib, string output)','private static void SaveSolid(Voxels part, string output, Library lib)')
        path.write_text(code);case['source_sha256']=sha(path)
        row['messages'][0]['content']+='\nConstruct only the stated solid and preserve every size, location, void and input control. Use the precise supported receivers: CalculateProperties and SaveToVdbFile on Voxels; SaveToStlFile on Mesh. For an implicit shape, instantiate the complete IImplicit implementation and BBox3 domain separately before new Voxels(lib, field, domain). Keep scoped native objects alive through export and never reassign a using variable. Return the whole program, including every helper. Do not substitute a sphere or a lattice primitive for a different requested solid.'
        row['messages'][1]['content']='The construction preserves the requested geometry and input controls with explicit native ownership and receiver types.\n\n```csharp\n'+code+'```'
    assert len(rows)==manifest['count']==48 and changed>=20,(len(rows),changed)
    (ROOT/'train.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n' for x in rows))
    manifest.update(author_sha256=sha(Path(__file__)),train_sha256=sha(ROOT/'train.jsonl'),reused_recipe_sha256=sha(recipe),implementation_changes='Distinct synthetic observations; explicit field/domain construction and reordered same-solid export receivers. Direct task conditioning; no faulty input or captured model answers.',native_validation='pending; no eligibility before native proof',final_contents_read=False)
    (ROOT/'cases.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'cases':48,'explicit_field_domain_constructions':changed,'train_sha256':manifest['train_sha256']}))
if __name__=='__main__':main()
