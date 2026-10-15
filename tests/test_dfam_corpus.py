"""Contract checks for the DfAM code corpus that need neither .NET nor PicoGK."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import dfam_corpus  # noqa: E402


class DfamCorpusTest(unittest.TestCase):
    def setUp(self):
        self.cases = dfam_corpus.load_cases(ROOT / 'data/dfam-code/cases.jsonl')
        self.bib = dfam_corpus.bibliography()

    def test_cases_pass_lint(self):
        self.assertEqual(dfam_corpus.lint(self.cases), {})

    def test_bibliography_entries_are_scoped(self):
        for key, entry in self.bib.items():
            self.assertEqual(set(entry), {'cite', 'entry', 'scope'}, key)
            self.assertIn(entry['cite'].split('(')[-1].rstrip(')'), entry['entry'], key)

    def test_every_case_has_a_passing_receipt(self):
        receipt = json.loads((ROOT / 'evidence/dfam-code/verification.json').read_text())
        self.assertEqual(receipt['picogk_package'], '2.3.0')
        for case in self.cases:
            record = receipt['cases'][case['id']]
            self.assertTrue(record['passed'], case['id'])
            self.assertEqual(record['case_sha256'], dfam_corpus.case_sha(case), case['id'])

    def test_lint_rejects_known_invalid_api(self):
        case = dict(self.cases[0], code=self.cases[0]['code'] + '\n// voxPart.Sub(voxVents);\n')
        problems = dfam_corpus.lint_case(case, self.bib)
        self.assertTrue(any('Sub()' in p for p in problems))

    def test_text_format(self):
        row = dfam_corpus.assemble_text(self.cases[0], self.bib)
        self.assertEqual(set(row), {'text'})
        self.assertTrue(row['text'].startswith('<|im_start|>user\n'))
        self.assertIn('\n<|im_end|>\n<|im_start|>assistant\n', row['text'])
        self.assertTrue(row['text'].endswith('\n<|im_end|>'))
        self.assertIn('```csharp\n', row['text'])


if __name__ == '__main__':
    unittest.main()
