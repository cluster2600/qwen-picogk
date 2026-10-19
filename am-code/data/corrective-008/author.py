"""Author alternative state/Boolean/parser implementations from synthetic recipes."""
import ast, hashlib, importlib.util, json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
WORK=ROOT.parents[1]

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    if (ROOT/'cases.json').exists():raise FileExistsError('Preserve prior authored cases.')
    recipe=WORK/'data/corrective-007/author.py'
    assert sha(recipe)==json.loads((recipe.parent/'cases.json').read_text())['author_sha256']
    spec=importlib.util.spec_from_file_location('synthetic_recipe',recipe)
    old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
    old.ROOT=ROOT;old.__file__=str(Path(__file__))
    # Replace primary-constructor captures by explicit, named state before generating answers.
    definitions={
      'BOX':('Box','Vector3 centre, Vector3 half',[('Vector3','centre'),('Vector3','half')]),
      'CRACK':('Crack','Vector3 centre, float half, float gap',[('Vector3','centre'),('float','half'),('float','gap')]),
      'TPMS':('Phase','Vector3 origin, float cell, int kind',[('Vector3','origin'),('float','cell'),('int','kind')]),
      'CONE':('Roof','Vector3 origin, float radius, float floor, float shoulder, float rise',[('Vector3','origin'),('float','radius'),('float','floor'),('float','shoulder'),('float','rise')]),
      'HULL':('Hull','List<(Vector3 point,Vector3 normal)> planes',[('List<(Vector3 point,Vector3 normal)>','planes')])}
    for name,(cls,args,fields) in definitions.items():
        text=getattr(old,name);first,body=text.split('\n{\n',1)
        assert first==f'public sealed class {cls}({args}) : IImplicit'
        declarations=''.join(f'    private readonly {typ} {field};\n' for typ,field in fields)
        assignments=' '.join(f'this.{field}={field};' for _,field in fields)
        setattr(old,name,f'public sealed class {cls} : IImplicit\n{{\n'+declarations+f'    public {cls}({args}) {{ {assignments} }}\n'+body)
    old.NORMALS='''    static List<(Vector3 point,Vector3 normal)> ReadPlanes(string path)
    {
        var lines=new List<string>();
        foreach(string raw in File.ReadLines(path))
        {
            string line=raw.Trim();
            if(line.Length>0 && !line.StartsWith("#")) lines.Add(line);
        }
        if(lines.Count!=7) throw new InvalidDataException("Header and six planes required.");
        string[] header=lines[0].Split(';'), names={"x","y","z","nx","ny","nz"};
        if(header.Length!=6) throw new InvalidDataException("Six named columns required.");
        int[] columns=new int[6]; var seen=new HashSet<string>();
        foreach(string name in header) if(!seen.Add(name)) throw new InvalidDataException("Duplicate column.");
        for(int j=0;j<6;j++)
        {
            columns[j]=Array.IndexOf(header,names[j]);
            if(columns[j]<0) throw new InvalidDataException("Missing named column.");
        }
        var result=new List<(Vector3 point,Vector3 normal)>(); var directions=new HashSet<Vector3>();
        for(int i=1;i<lines.Count;i++)
        {
            string[] cells=lines[i].Split(';');
            if(cells.Length!=6) throw new InvalidDataException("Six values required.");
            float[] values=new float[6];
            for(int j=0;j<6;j++)
                if(!float.TryParse(cells[columns[j]],NumberStyles.Float,CultureInfo.InvariantCulture,out values[j]) || !float.IsFinite(values[j]))
                    throw new InvalidDataException("Finite numeric observations required.");
            Vector3 point=new(values[0],values[1],values[2]),normal=new(values[3],values[4],values[5]);
            if(Vector3.Abs(point).X>8 || Vector3.Abs(point).Y>8 || Vector3.Abs(point).Z>8 || normal.LengthSquared()<.01f)
                throw new InvalidDataException("Bounded points and nonzero normals required.");
            normal=Vector3.Normalize(normal);
            if(MathF.Abs(normal.X)+MathF.Abs(normal.Y)+MathF.Abs(normal.Z)!=1 || !directions.Add(normal))
                throw new InvalidDataException("Six distinct axis directions required.");
            result.Add((point,normal));
        }
        return result;
    }
'''
    # A different validated input reader keeps refusal and occupancy paths within the same allowlist.
    old.XYZ='''    static List<Vector3> ReadXYZ(string path)
    {
        var points=new List<Vector3>();
        foreach(string raw in File.ReadLines(path))
        {
            string line=raw.Trim();
            if(line.Length==0 || line.StartsWith("#")) continue;
            string[] cells=line.Split(new[]{',',';',' ','\\t'},StringSplitOptions.RemoveEmptyEntries);
            if(cells.Length==3 && cells[0].Equals("x",StringComparison.OrdinalIgnoreCase)
                && cells[1].Equals("y",StringComparison.OrdinalIgnoreCase) && cells[2].Equals("z",StringComparison.OrdinalIgnoreCase)) continue;
            if(cells.Length!=3) throw new InvalidDataException("Exactly three coordinates required.");
            float[] values=new float[3];
            for(int j=0;j<3;j++)
                if(!float.TryParse(cells[j],NumberStyles.Float,CultureInfo.InvariantCulture,out values[j])
                    || !float.IsFinite(values[j]) || MathF.Abs(values[j])>8) throw new InvalidDataException("Finite bounded coordinates required.");
            points.Add(new Vector3(values[0],values[1],values[2]));
            if(points.Count>10000) throw new InvalidDataException("Too many observations.");
        }
        if(points.Count==0) throw new InvalidDataException("No observations.");
        return points;
    }
'''
    source=recipe.read_text();node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name=='generate')
    function=ast.get_source_segment(source,node)
    before="families=['initialize','offset-sign','closing','shell','vent','cone-roof','gyroid','diamond','schwarz-p',\n              'scan-normals','debug-api','missing-interfaces','stl-roundtrip','stl-skin-vent','xyz-occupancy','signed-range-refusal']"
    selected=['closing','shell','vent','cone-roof','gyroid','diamond','schwarz-p','scan-normals','debug-api','stl-skin-vent','xyz-occupancy','signed-range-refusal']
    assert before in function
    function=function.replace(before,'families='+repr(selected)).replace("ident=f'rehearsal-","ident=f'state-").replace('==64','==48').replace('>=55','>=40').replace("'count':64","'count':48")
    exec(compile(function,str(Path(__file__)),'exec'),old.__dict__)
    old.generate()
    manifest=json.loads((ROOT/'cases.json').read_text());rows=[]
    prior=[json.loads(x) for x in (ROOT/'train.jsonl').read_text().splitlines()]
    for row,case in zip(prior,manifest['cases']):
        file=ROOT/case['source'];code=file.read_text();family=case['family'];o=case['oracle'];extra=''
        body=None
        if family=='shell':
            body=f'        using Voxels part=new(lib,new RadialSkin({old.vec(o["centre"])},{old.f(o["radius"]-o["wall"]/2)},{old.f(o["wall"]/2)}),new BBox3(new Vector3(-8),new Vector3(8)));'
            extra='''\npublic sealed class RadialSkin : IImplicit
{
    private readonly Vector3 centre; private readonly float middle,halfWidth;
    public RadialSkin(Vector3 centre,float middle,float halfWidth) { this.centre=centre;this.middle=middle;this.halfWidth=halfWidth; }
    public float fSignedDistance(in Vector3 p) => MathF.Abs((p-centre).Length()-middle)-halfWidth;
}
'''
        elif family=='vent':
            c=o['centre'];half=o['half'];w=o['wall'];v=o['vent_radius']
            body=f'        using Voxels part=new(lib,new DrainedBox({old.vec(c)},{old.vec(half)},{old.f(w)},{old.f(v)}),new BBox3(new Vector3(-8),new Vector3(8)));'
            extra='''\npublic sealed class DrainedBox : IImplicit
{
    private readonly Vector3 centre,half; private readonly float wall,radius;
    public DrainedBox(Vector3 centre,Vector3 half,float wall,float radius) { this.centre=centre;this.half=half;this.wall=wall;this.radius=radius; }
    private static float BoxDistance(Vector3 p,Vector3 half)
    {
        Vector3 q=Vector3.Abs(p)-half;
        return Vector3.Max(q,Vector3.Zero).Length()+MathF.Min(MathF.Max(q.X,MathF.Max(q.Y,q.Z)),0f);
    }
    public float fSignedDistance(in Vector3 p)
    {
        Vector3 q=p-centre;
        float outer=BoxDistance(q,half),inner=BoxDistance(q,half-new Vector3(wall));
        float bottom=-half.Z-.6f;
        float port=MathF.Max(MathF.Sqrt(q.X*q.X+q.Y*q.Y)-radius,MathF.Max(bottom-q.Z,q.Z));
        // Difference from a union of voids preserves the outer boundary in one field.
        return MathF.Max(outer,-MathF.Min(inner,port));
    }
}
'''
        elif family=='debug-api':
            body=f'        using Voxels part=new(lib,new FlatCylinder({old.vec(o["centre"])},{old.f(o["radius"])},{old.f(o["half_height"])}),new BBox3(new Vector3(-8),new Vector3(8)));'
            extra='''\npublic sealed class FlatCylinder : IImplicit
{
    private readonly Vector3 centre; private readonly float radius,halfHeight;
    public FlatCylinder(Vector3 centre,float radius,float halfHeight) { this.centre=centre;this.radius=radius;this.halfHeight=halfHeight; }
    public float fSignedDistance(in Vector3 p)
    {
        Vector3 q=p-centre; float radial=MathF.Sqrt(q.X*q.X+q.Y*q.Y)-radius,cap=MathF.Abs(q.Z)-halfHeight;
        return MathF.Sqrt(MathF.Max(radial,0f)*MathF.Max(radial,0f)+MathF.Max(cap,0f)*MathF.Max(cap,0f))+MathF.Min(MathF.Max(radial,cap),0f);
    }
}
'''
        if body is not None:
            anchor='        using Library lib = new(0.2f);';start=code.index(anchor)+len(anchor);end=code.index('        part.CalculateProperties',start)
            code=code[:start]+'\n'+body+'\n'+code[end:]+extra
        if family=='stl-skin-vent':
            code=code.replace('using Voxels cavity=new(part); cavity.Offset','// The input envelope stays untouched until its independent cavity is ready.\n        using Voxels cavity=new(part); cavity.Offset')
        file.write_text(code);case['source_sha256']=sha(file)
        row['messages'][0]['content']+=' Use ordinary explicit constructors and declared private state for all IImplicit helpers; include every helper. Alternative analytic difference fields are permitted if they preserve all required geometry and actual-input behavior.'
        explanation='Use explicit declared state and complete input readers; export the actual final field. Synthetic geometry and minimum walls do not establish LPBF, residual-stress, evacuation or fitment qualification.'
        if family=='shell':explanation='An analytic radial band preserves the specified outer radius without an in-place outer erosion. A sealed geometric shell still has no powder-removal approval.'
        if family=='vent':explanation='The implicit difference combines the inner chamber and bottom port as voids, preserving the outer box. A digital connection alone does not prove physical powder evacuation.'
        row['messages'][1]['content']=explanation+'\n\n```csharp\n'+code+'```';rows.append(row)
    assert len(rows)==manifest['count']==48 and len({c['source_sha256'] for c in manifest['cases']})>=40
    (ROOT/'train.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False,separators=(',',':'))+'\n' for x in rows))
    manifest.update(train_sha256=sha(ROOT/'train.jsonl'),author_sha256=sha(Path(__file__)),reused_recipe_source_sha256=sha(recipe),implementation_changes='Explicit state in five helper classes; analytic radial shell, implicit drained-box void union, analytic flat cylinder; imperative complete plane/XYZ readers. Some scan Boolean sequence semantics remain deliberately unchanged.',final_contents_read=False,native_validation='pending; no row eligible before native proof')
    (ROOT/'cases.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps({'cases':48,'train_sha256':manifest['train_sha256'],'native_validation':'pending'}))
if __name__=='__main__':main()
