"""Eight independent operation-semantic lessons; no captured answer is reused."""
import ast,hashlib,importlib.util,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    assert not (ROOT/'cases.json').exists()
    recipe=WORK/'data/corrective-007/author.py'
    assert sha(recipe)==json.loads((recipe.parent/'cases.json').read_text())['author_sha256']
    spec=importlib.util.spec_from_file_location('semantic_recipe',recipe)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old);old.ROOT=ROOT;old.__file__=str(Path(__file__))
    text=recipe.read_text();node=next(n for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name=='generate');fn=ast.get_source_segment(text,node)
    begin=fn.index("    families=");end=fn.index('\n    for family',begin)
    fn=fn[:begin]+"    families=['closing','shell']"+fn[end:]
    for before,after in [("ident=f'rehearsal-","ident=f'semantic-"),('[[.4,-.6,1.],[-1.,1.4,.2],[1.4,-.2,-.4],[-.6,-1.,.6]]','[[.3,.9,-.7],[-.9,.3,.5],[.7,-.3,-.9],[-.3,-.7,.9]]'),('[2.78,2.98,3.28,3.58]','[2.86,3.06,3.36,3.66]'),('[1.08,1.18,1.26,1.34]','[1.12,1.22,1.30,1.38]'),('[2.94,3.14,3.46,3.70]','[3.02,3.22,3.54,3.78]'),('[.28,.36,.48,.56]','[.32,.40,.52,.60]'),('[.62,.74,.86,.98]','[.66,.78,.90,1.02]'),('==64','==8'),('>=55','>=8'),("'count':64","'count':8")]:
        assert before in fn,before
        fn=fn.replace(before,after)
    exec(compile(fn,str(Path(__file__)),'exec'),old.__dict__);old.generate()
    m=json.loads((ROOT/'cases.json').read_text());rows=[json.loads(x) for x in (ROOT/'train.jsonl').read_text().splitlines()]
    for row,case in zip(rows,m['cases']):
        f=ROOT/case['source'];code=f.read_text()
        for name in ['Library','Lattice','Voxels','Mesh','BBox3','IImplicit']:code=re.sub(r'(?<![\w.])'+name+r'\b','PicoGK.'+name,code)
        code=re.sub(r'\bpart\b','body',code).replace('body.stl','part.stl').replace('body.vdb','part.vdb')
        code='\n'.join(x.strip() for x in code.splitlines() if x.strip() and not x.lstrip().startswith('//'))+'\n'
        if case['family']=='closing':
            assert code.count('body.Offset(')==2
            guidance=' Closing requires the two operations on the SAME final Voxels: positive Offset by the requested closing radius, then negative Offset by that same radius. Export that modified body. Merely constructing or exporting the cracked field leaves the fissure open.'
        else:
            assert 'body.BoolSubtract(cavity)' in code and 'cavity.Offset(-' in code
            guidance=' Nominal wall is the full radial thickness. Preserve the stated OUTER sphere radius; copy its Voxels, erode the copy by exactly the wall, then BoolSubtract the cavity from the outer body. Export the result, not either operand. Do not use wall as a symmetric half-width.'
        row['messages'][0]['content']+=guidance+' Return one complete C# code block and stop. All helper declarations must be included; this is synthetic geometry evidence only.'
        row['messages'][1]['content']='```csharp\n'+code+'```';f.write_text(code);case['source_sha256']=sha(f)
    prior=json.loads((WORK/'data/corrective-013/cases.json').read_text())
    assert len(rows)==8 and len({x['source_sha256'] for x in m['cases']})==8
    assert not ({x['source_sha256'] for x in m['cases']} & {x['source_sha256'] for x in prior['cases']})
    (ROOT/'train.jsonl').write_text(''.join(json.dumps(x,separators=(',',':'))+'\n' for x in rows))
    m.update(author_sha256=sha(Path(__file__)),train_sha256=sha(ROOT/'train.jsonl'),reused_recipe_sha256=sha(recipe),native_validation='pending; not eligible for training',purpose='Eight new independent closing/shell observations teach operation order, final receiver and full wall semantics; no captured answer repair.',final_contents_read=False)
    (ROOT/'cases.json').write_text(json.dumps(m,indent=2)+'\n')
    print(json.dumps(dict(cases=8,train_sha256=m['train_sha256'])))
if __name__=='__main__':main()
