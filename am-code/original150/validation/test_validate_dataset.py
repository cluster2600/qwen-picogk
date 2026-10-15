import json
from pathlib import Path
import tempfile
import unittest

from validate_dataset import parse_record, strict_object, without_example_identity, validate


class ContractTests(unittest.TestCase):
    def sample(self):
        return json.dumps({"text": "<|im_start|>user\nRead oriented synthetic points.\n<|im_end|>\n"
                           "<|im_start|>assistant\nUse explicit physical units.\n```csharp\n"
                           "namespace AmDataset.Ex001;\nusing Library lib = new(0.2f);\n```\n<|im_end|>"})

    def test_complete_example_is_extracted(self):
        self.assertIn("namespace AmDataset.Ex001", parse_record(self.sample(), 1)[3])

    def test_unbalanced_code_fence_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "fence"):
            parse_record(self.sample().replace("```csharp", "```"), 1)

    def test_wrong_namespace_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "namespace"):
            parse_record(self.sample(), 2)

    def test_extra_json_fields_are_rejected(self):
        example = json.loads(self.sample())
        example["extra"] = "invalid"
        with self.assertRaisesRegex(ValueError, "exactly one"):
            parse_record(json.dumps(example), 1)

    def test_duplicate_json_keys_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Duplicate JSON key"):
            json.loads('{"text":"one","text":"two"}', object_pairs_hook=strict_object)

    def test_namespace_and_prompt_id_do_not_create_fake_uniqueness(self):
        first = "Engineering exercise 001: test; namespace AmDataset.Ex001;"
        second = "Engineering exercise 002: test; namespace AmDataset.Ex002;"
        self.assertEqual(without_example_identity(first), without_example_identity(second))

    def test_corrupted_metadata_bindings_are_rejected(self):
        root = Path(__file__).resolve().parent.parent
        for field, value, message in (("code_sha256", "0" * 64, "code hash"),
                                      ("load_mode", "range", "input mode"),
                                      ("title", "Incorrect title", "title")):
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                metadata = json.loads((root / "metadata.json").read_text())
                metadata["examples"][0][field] = value
                path = Path(temporary) / "metadata.json"
                path.write_text(json.dumps(metadata))
                with self.assertRaisesRegex(ValueError, message):
                    validate(root / "data/picogk-am-150.jsonl", path)


if __name__ == "__main__":
    unittest.main()
