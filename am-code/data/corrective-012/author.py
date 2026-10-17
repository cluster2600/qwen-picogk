"""Create compact direct teaching programs from independent synthetic field recipes."""
import hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    recipe=WORK/'data/corrective-011/author.py'
    prior=json.loads((recipe.parent/'cases.json').read_text());assert sha(recipe)==prior['author_sha256']
    source=recipe.read_text()
    old='[[.4,.6,-.8],[-.6,-.4,.8],[.8,-1.,.2],[-1.,.8,-.4]]'
    assert source.count(old)==1
    source=source.replace(old,'[[-.4,.4,.8],[.8,-.6,-.4],[-.6,-.8,.6],[.6,.8,-.2]]').replace("ident=f'field-","ident=f'compact-")
    ns={'__name__':'compact_recipe','__file__':str(Path(__file__))}
    exec(compile(source,str(Path(__file__)),'exec'),ns);ns['main']()
    manifest=json.loads((ROOT/'cases.json').read_text());rows=[json.loads(x) for x in (ROOT/'train.jsonl').read_text().splitlines()]
    for row,case in zip(rows,manifest['cases']):
        path=ROOT/case['source'];code=path.read_text()
        code=re.sub(r'\bpart\b','solid',code).replace('solid.stl','part.stl').replace('solid.vdb','part.vdb')
        code=code.replace('SaveSolid','ExportSolid')
        code='\n'.join(line.strip() for line in code.splitlines() if line.strip() and not line.lstrip().startswith('//'))+'\n'
        assert 'MathF.Clamp' not in code and 'MathF.TwoPi' not in code
        path.write_text(code);case['source_sha256']=sha(path)
        row['messages'][0]['content']+='\nReturn exactly one finite, complete C# code block, ending after its closing brace and closing fence; no repeated program or prose after it. Use only documented .NET/PicoGK members. MathF.PI is supported; construct 2*MathF.PI explicitly when needed. Geometry Boolean/offset/property/VDB methods belong to Voxels, never Mesh; primitive AddSphere/AddBeam belong to Lattice. Preserve every input, size and void specification. A refusal must also reject an empty/sparse observation. No viewer and no manufacture claim.'
        row['messages'][1]['content']='```csharp\n'+code+'```'
    assert len(rows)==manifest['count']==48
    (ROOT/'train.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n' for x in rows))
    manifest.update(author_sha256=sha(Path(__file__)),train_sha256=sha(ROOT/'train.jsonl'),reused_recipe_sha256=sha(recipe),implementation_changes='New independent synthetic observations, explicit solid receiver naming, compact complete scoped programs and single-codeblock termination teaching; no captured model answers.',native_validation='pending; no eligibility before native proof',final_contents_read=False)
    (ROOT/'cases.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'cases':48,'train_sha256':manifest['train_sha256']}))
if __name__=='__main__':main()
