"""Run the pinned planner on five exposed examples and retain real PicoGK meshes."""
import argparse
import fcntl
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import contracts
import evaluate
import infer


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', type=Path)
    parser.add_argument('--output', type=Path, required=True, help='New gallery directory, never overwritten')
    parser.add_argument('--native-host', type=Path, default=ROOT/'native/bin/GeometryHost.dll')
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a new gallery directory; preserve preceding receipts')
    source = ROOT/'data/planner/cases.json'
    cases = {row['id']: row for row in json.loads(source.read_text())}
    selection = json.loads((ROOT/'docs/visuals/cases.json').read_text())
    release = json.loads((ROOT/'release.json').read_text())
    with (ROOT/'models/planner/.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        model, tokenizer = infer.load_model(base=args.base)
        args.output.mkdir(parents=True)
        records = []
        for selected in selection:
            case = cases[selected['id']]
            assert case['split'] == 'test' and case['language'] == selected['language']
            messages = case['messages'][:2]
            assert messages[0]['content'] == release['system_prompt']
            text, finish = infer.generate(model, tokenizer, messages[0]['content'], messages[1]['content'])
            folder = args.output/selected['recipe']
            transcript = dict(case_id=case['id'], messages=messages, raw_response=text, finish_reason=finish,
                              adapter_sha256=release['adapters']['planner']['adapters.safetensors'],
                              greedy_temperature=0, seed=release['decoding']['seed'], canonical_input=False)
            plan = contracts.accepted(text, finish, case['request'])
            assert plan['recipe'] == selected['recipe']
            metrics = evaluate.native(plan, args.native_host, output_dir=folder)
            (folder/'llm.json').write_text(json.dumps(transcript, ensure_ascii=False, indent=2)+'\n')
            (folder/'request.json').write_text(json.dumps(case['request'], ensure_ascii=False, indent=2)+'\n')
            (folder/'native.json').write_text(json.dumps(metrics, indent=2)+'\n')
            records.append(dict(**selected, parameters_mm=plan['parameters_mm'],
                                volume_mm3=metrics['volume'], triangles=metrics['triangles'],
                                geometry_screen_passed=True, model_called=True, manufacturing_qualified=False,
                                files_sha256={str(path.relative_to(args.output)): infer.digest(path)
                                              for path in folder.iterdir() if path.is_file()}))
            print('LLM and native mesh completed: '+selected['recipe'], flush=True)
        receipt = dict(schema='qwen-picogk.gallery@1', records=records, corpus_sha256=infer.digest(source),
                       adapter_sha256=release['adapters']['planner']['adapters.safetensors'],
                       base_revision=release['base']['revision'], voxel_mm=0.5,
                       selection='Five exposed passing final examples, one recipe/language each. Demonstrations, not a new benchmark.',
                       source_sha256={name: infer.digest(ROOT/name) for name in
                                      ['scripts/build_gallery.py', 'infer.py', 'contracts/__init__.py', 'scripts/evaluate.py', 'native/GeometryHost.cs']},
                       rendering='Pending mesh rendering; no generated illustration or measured vehicle part',
                       manufacturing_qualified=False)
        (args.output/'gallery.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+'\n')


if __name__ == '__main__':
    main()
