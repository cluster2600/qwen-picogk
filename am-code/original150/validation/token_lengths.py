#!/usr/bin/env python3
"""Measure exact tokens from the local tokenizer; never load model weights."""

import argparse
import hashlib
import json
from pathlib import Path
import sys

from tokenizers import Tokenizer


def main():
    directory = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=directory.parent / "data" / "picogk-am-150.jsonl")
    parser.add_argument("--tokenizer", type=Path, default=Path(__file__).resolve().parents[3]/"model/tokenizer.json")
    parser.add_argument("--max-seq-length", type=int, default=16384)
    args = parser.parse_args()
    if args.max_seq_length <= 0:
        parser.error("max-seq-length must be positive")
    tokenizer = Tokenizer.from_file(str(args.tokenizer))
    specials = {token: tokenizer.token_to_id(token) for token in ("<|im_start|>", "<|im_end|>")}
    if any(value is None for value in specials.values()):
        raise ValueError("Tokenizer lacks the required ChatML special tokens")
    lengths = []
    for number, line in enumerate(args.dataset.read_text().splitlines(), 1):
        text = json.loads(line)["text"]
        encoding = tokenizer.encode(text, add_special_tokens=False)
        for token, token_id in specials.items():
            if encoding.ids.count(token_id) != 2:
                raise ValueError(f"Example {number}: {token} is not encoded twice as one special token")
        lengths.append({"id": number, "tokens": len(encoding.ids)})
    ordered = sorted(item["tokens"] for item in lengths)
    too_long = [item for item in lengths if item["tokens"] > args.max_seq_length]
    report = {
        "status": "passed", "weights_loaded": False,
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "tokenizer": str(args.tokenizer),
        "tokenizer_sha256": hashlib.sha256(args.tokenizer.read_bytes()).hexdigest(),
        "special_tokens": specials, "count": len(lengths),
        "minimum": min(ordered), "median": ordered[len(ordered) // 2],
        "p95": ordered[(95 * (len(ordered) - 1)) // 100], "maximum": max(ordered),
        "total": sum(ordered), "configured_max_seq_length": args.max_seq_length,
        "examples_exceeding_max_seq_length": too_long,
        "examples": lengths,
    }
    report["suggested_minimum_no_truncation"] = 256 * ((max(ordered) + 255) // 256)
    output = directory / "token-lengths.json"
    output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: value for key, value in report.items() if key != "examples"}, indent=2))
    return 0 if not too_long else 1


if __name__ == "__main__":
    sys.exit(main())
