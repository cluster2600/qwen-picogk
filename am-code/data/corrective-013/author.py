"""Author separate namespace-explicit teachers from independent compact recipes."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    recipe=WORK/'data/corrective-012/author.py'
    previous=json.loads((recipe.parent/'cases.json').read_text())
    assert sha(recipe)==previous['author_sha256']
    text=recipe.read_text()
    old="[[-.4,.4,.8],[.8,-.6,-.4],[-.6,-.8,.6],[.6,.8,-.2]]"
    assert text.count(old)==1
    text=text.replace(old,"[[.2,-.8,.4],[-.4,.2,-.6],[.6,-.4,1.],[-.8,.6,-.2]]").replace("ident=f'compact-","ident=f'typed-")
    ns={'__name__':'typed_recipe','__file__':str(Path(__file__))}
    exec(compile(text,str(Path(__file__)),'exec'),ns);ns['main']()
    manifest=json.loads((ROOT/'cases.json').read_text())
    rows=[json.loads(x) for x in (ROOT/'train.jsonl').read_text().splitlines()]
    for row,case in zip(rows,manifest['cases']):
        path=ROOT/case['source'];code=path.read_text()
        for typename in ['Library','Lattice','Voxels','Mesh','BBox3','IImplicit']:
            code=re.sub(r'(?<![\w.])'+typename+r'\b','PicoGK.'+typename,code)
        code=re.sub(r'\bsolid\b','body',code).replace('ExportSolid','WriteArtifacts')
        code=re.sub(r'\bargs\b','arguments',code)
        assert not any(bad in code for bad in ['.AddBox(', 'PicoGK.PicoGK', 'VoxelsToMesh', '.OrientedBoundingBox('])
        assert code.count('{')==code.count('}')
        path.write_text(code);case['source_sha256']=sha(path)
        row['messages'][0]['content']+=' Use fully qualified PicoGK type names in constructors and helper signatures. Declare every scalar local individually before use; access Vector3 components explicitly. Construct boxes from a complete IImplicit and BBox3 domain; construct beams through Lattice then Voxels with the same Library. Keep ownership and method receiver types exact. Use the documented oriented-normal voxelization constructor for point clouds. Refusal output must match the requested JSON fields exactly for nominal, empty and sparse inputs.'
        row['messages'][1]['content']='```csharp\n'+code+'```'
    assert len(rows)==manifest['count']==48
    assert len({c['source_sha256'] for c in manifest['cases']} & {c['source_sha256'] for c in previous['cases']})==0
    (ROOT/'train.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n' for x in rows))
    manifest.update(author_sha256=sha(Path(__file__)),train_sha256=sha(ROOT/'train.jsonl'),reused_recipe_sha256=sha(recipe),implementation_changes='New independent synthetic observations; fully qualified public type constructors and helper signatures, explicit body ownership and scalar declaration guidance; exact sparse refusal schema. No captured model answer repaired.',native_validation='pending; no eligibility before unchanged native proof',final_contents_read=False)
    (ROOT/'cases.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'cases':48,'train_sha256':manifest['train_sha256']}))
if __name__=='__main__':main()
