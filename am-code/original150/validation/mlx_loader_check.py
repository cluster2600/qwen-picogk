#!/usr/bin/env python3
"""Verify the installed MLX-LM text loader on local JSONL without model weights."""

import hashlib
import inspect
import json
from pathlib import Path
import types

from mlx_lm.tuner.datasets import load_local_dataset, TextDataset
from transformers import AutoTokenizer


def main():
    directory = Path(__file__).resolve().parent
    data = directory.parent / "data"
    model = Path(__file__).resolve().parents[3]/"model"
    tokenizer = AutoTokenizer.from_pretrained(str(model), local_files_only=True, trust_remote_code=False)
    config = types.SimpleNamespace(mask_prompt=False, text_feature="text")
    train, valid, test = load_local_dataset(data, tokenizer, config)
    assert isinstance(train, TextDataset) and len(train) == 150
    lengths = []
    for index in range(len(train)):
        tokens, offset = train.process(train[index])
        assert offset == 0 and tokens[-1] == tokenizer.eos_token_id
        assert tokens.count(tokenizer.convert_tokens_to_ids("<|im_start|>")) == 2
        assert tokens.count(tokenizer.convert_tokens_to_ids("<|im_end|>")) == 2
        lengths.append(len(tokens))
    # The required text format has whole-sequence loss; MLX-LM forbids prompt masking here.
    try:
        load_local_dataset(data, tokenizer, types.SimpleNamespace(mask_prompt=True, text_feature="text"))
    except ValueError as failure:
        assert "Prompt masking not supported" in str(failure)
    else:
        raise AssertionError("Expected text-format prompt masking rejection")
    source = Path(inspect.getfile(load_local_dataset))
    report = {
        "status": "passed", "weights_loaded": False, "training_started": False,
        "local_files_only": True, "trust_remote_code": False,
        "loader": str(source), "loader_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "dataset_type": type(train).__name__, "train_examples": len(train),
        "valid_examples": len(valid), "test_examples": len(test),
        "tokenizer_class": type(tokenizer).__name__, "minimum_tokens": min(lengths),
        "maximum_tokens": max(lengths), "total_tokens": sum(lengths),
        "text_format_loss": "whole sequence; mask_prompt must remain false",
        "prompt_masking_rejection_verified": True,
        "train_sha256": hashlib.sha256((data / "train.jsonl").read_bytes()).hexdigest(),
    }
    (directory / "mlx-loader.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
