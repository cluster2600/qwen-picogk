"""Repeat a recorded text-to-C# probe; always preserve raw output without executing it."""
import argparse
import fcntl
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import infer


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('transcript',type=Path)
    parser.add_argument('output',type=Path)
    parser.add_argument('--base',type=Path)
    args=parser.parse_args()
    if args.output.exists() or args.transcript.stat().st_size>65536:
        parser.error('Use a new output directory and a transcript below 64 KiB')
    messages=json.loads(args.transcript.read_text())['messages']
    if [m['role']for m in messages]!=['system','user'] or any(type(m['content'])is not str for m in messages):
        parser.error('Exactly one text system message and one text user message are required')
    with(ROOT/'models/planner/.lock').open('a')as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        model,tokenizer=infer.load_model(base=args.base)
        prompt=tokenizer.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
        if len(tokenizer.encode(prompt))>1024:parser.error('Probe exceeds the registered input context')
        from mlx_lm import stream_generate
        from mlx_lm.sample_utils import make_sampler
        args.output.mkdir(parents=True)
        text,last='',None
        for last in stream_generate(model,tokenizer,prompt=prompt,max_tokens=1024,sampler=make_sampler(temp=0)):
            text+=last.text
        receipt=dict(schema='qwen-picogk.csharp-probe@1',messages=messages,raw_response=text,
                     finish_reason=last.finish_reason if last else None,
                     adapter_sha256=infer.digest(ROOT/'models/planner/adapters.safetensors'),
                     input_tokens=len(tokenizer.encode(prompt)),max_new_tokens=1024,
                     code_executed=False,scan_input=False)
        (args.output/'llm.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
        (args.output/'response.cs.txt').write_text(text+'\n')
        print(json.dumps({k:v for k,v in receipt.items()if k not in ['messages','raw_response']}))


if __name__=='__main__':main()
