"""CPU-only lexical/profile regressions; candidate programs are never executed."""
from contextlib import contextmanager
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import policy_v2 as policy


def program(body):
    return 'using System; public class Program { public static void Main(string[] args) { ' + body + ' } }'


@contextmanager
def fixture_profile():
    with tempfile.TemporaryDirectory(prefix='policy-v2-test-', dir=Path(__file__).parent) as temporary:
        root = Path(temporary)
        files = {}
        for name in policy.REQUIRED_FILES:
            target = root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'fixture dependency\n')
            files[name] = policy.digest(target)
        external = root / 'external-runtime.dll'
        external.write_bytes(b'fixture installed runtime\n')
        profile = {'schema': policy.SCHEMA, 'policy': policy.POLICY, 'files': files,
                   'external_files': {str(external): policy.digest(external)}}
        path = root / 'checker-profile-v2.json'
        with patch.object(policy, 'EXTERNAL_FILES', frozenset({str(external)})):
            def write(value):
                path.write_text(json.dumps(value, sort_keys=True) + '\n')
                path.with_suffix('.sha256').write_text(policy.digest(path) + '\n')
            write(profile)
            yield root, path, profile, write


class LexicalPolicyTests(unittest.TestCase):
    def inspect(self, source):
        facts = policy.lexer_facts(source)
        self.assertEqual(facts['parse_errors'], [])
        return policy.check_facts(facts)

    def test_independent_eighteen_case_fixture(self):
        path = policy.ROOT / 'diagnostics/evaluation-policy-v2/lexical-testcases.json'
        fixture = json.loads(path.read_text())
        self.assertEqual(len(fixture['cases']), 18)
        self.assertEqual(sum(case['expected_policy_acceptance'] for case in fixture['cases']), 7)
        for case in fixture['cases']:
            with self.subTest(case=case['id']):
                if case['expected_policy_acceptance']:
                    self.assertTrue(self.inspect(case['source']))
                else:
                    with self.assertRaises(ValueError):
                        self.inspect(case['source'])

    def test_literal_paths_remain_rejected_in_every_string_form(self):
        expressions = ['"/private/example"', '@"C:\\example"', '"../example"',
                       '"""../example"""', '$"/private/{args.Length}"',
                       '$$"""/private/{{args.Length}}"""', '"~/.example"']
        for expression in expressions:
            with self.subTest(expression=expression), self.assertRaises(ValueError):
                self.inspect(program('Console.WriteLine(' + expression + ');'))

    def test_namespace_and_identifier_boundaries(self):
        safe = 'using System /* Process */ . IO; ' + program('Console.WriteLine("mm³ 🚀");')
        self.assertTrue(self.inspect(safe))
        for body in ('System . Func<int,int> f = x => x;',
                     'System /* x */ . Func<int,int> f = x => x;',
                     'System.IO.StreamReader reader = null;',
                     'global::System.IO.Path.Combine("a","b");',
                     'dynamic value = null;', 'int épaisseur = 1;'):
            with self.subTest(body=body), self.assertRaises(ValueError):
                self.inspect(program(body))
        for prefix in ('using Alias = System.IO.Path;', 'using static System.Math;',
                       'using System.Net;'):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                self.inspect(prefix + program('Console.WriteLine("ok");'))
        with self.assertRaises(ValueError):
            self.inspect('namespace System.IO { ' + program('') + ' }')

    def test_syntax_main_directive_and_size_fail_closed(self):
        for source in (program('Console.WriteLine("unterminated);'),
                       'public class Program { public static void Main() {} }',
                       '#if true\n' + program('') + '\n#endif\n'):
            with self.subTest(source=source), self.assertRaises(ValueError):
                policy.check_facts(policy.lexer_facts(source))
        with self.assertRaises(ValueError):
            policy.lexer_facts(' ' * 180001)

    def test_guard_verifies_current_profile_before_helper_and_refuses_race(self):
        with patch.object(policy, 'verify_checker_profile', return_value={
                'checker_profile_sha256': 'a' * 64, 'profile': {}}) as verify:
            self.assertTrue(policy.static_gate(program('Console.WriteLine("Process complete.");'),
                                               expected_profile_sha256='a' * 64))
            verify.assert_called_once_with(None)
            with patch.object(policy, 'lexer_facts', side_effect=AssertionError('helper must not run')):
                with self.assertRaises(ValueError):
                    policy.static_gate(program(''), expected_profile_sha256='b' * 64)
        with patch.object(policy, 'verify_checker_profile', side_effect=ValueError('untrusted')):
            with patch.object(policy, 'lexer_facts', side_effect=AssertionError('helper must not run')):
                with self.assertRaises(ValueError):
                    policy.static_gate(program(''))

    def test_single_fence_and_source_bytes_are_preserved(self):
        source = program('Console.WriteLine("Process complete.");') + '\n'
        with patch.object(policy, 'verify_checker_profile', return_value={
                'checker_profile_sha256': 'a' * 64, 'profile': {}}):
            self.assertEqual(policy.extract('Explanation\n```csharp\n' + source + '```'), source)
            for response in ('```csharp\n' + source, '```cs\n' + source + '```\n```cs\n' + source + '```'):
                with self.subTest(response=response), self.assertRaises(ValueError):
                    policy.extract(response)


class ProfileBindingTests(unittest.TestCase):
    def test_closed_anchored_profile(self):
        with fixture_profile() as (_, path, profile, _):
            binding = policy.verify_checker_profile(path)
            self.assertEqual(binding['checker_profile_sha256'], policy.digest(path))
            self.assertEqual(binding['profile'], profile)

    def test_missing_anchor_and_tampered_dependencies(self):
        with fixture_profile() as (root, path, _, _):
            (root / 'evaluation/PolicyLexer/Program.cs').write_text('changed')
            with self.assertRaises(ValueError):
                policy.verify_checker_profile(path)
        with fixture_profile() as (root, path, _, _):
            (root / 'external-runtime.dll').write_text('changed')
            with self.assertRaises(ValueError):
                policy.verify_checker_profile(path)
        with fixture_profile() as (_, path, _, _):
            path.with_suffix('.sha256').unlink()
            with self.assertRaises(ValueError):
                policy.verify_checker_profile(path)

    def test_extra_missing_traversal_final_and_duplicate_keys(self):
        with fixture_profile() as (_, path, profile, write):
            mutations = [dict(profile, extra=True), dict(profile, policy='legacy'),
                         dict(profile, files={**profile['files'], '../outside.cs': 'a' * 64}),
                         dict(profile, files={**profile['files'], 'evaluation/final.json': 'a' * 64}),
                         dict(profile, files={key: value for key, value in profile['files'].items()
                                              if key != 'evaluation/evaluate.py'})]
            for value in mutations:
                with self.subTest(keys=set(value)), self.assertRaises(ValueError):
                    write(value)
                    policy.verify_checker_profile(path)
            path.write_text('{"schema":"one","schema":"two"}')
            path.with_suffix('.sha256').write_text(policy.digest(path) + '\n')
            with self.assertRaises(ValueError):
                policy.verify_checker_profile(path)

    def test_dependency_symlinks_and_stale_inspector_cache(self):
        with fixture_profile() as (root, path, _, _):
            dependency = root / 'evaluation/evaluate.py'
            dependency.unlink()
            dependency.symlink_to(root / 'evaluation/policy_v2.py')
            with self.assertRaises(ValueError):
                policy.verify_checker_profile(path)
        with fixture_profile() as (root, path, profile, write):
            cached = root / 'evaluation/inspector-build/Program.cs'
            cached.write_text('stale cached Inspector')
            profile['files'][cached.relative_to(root).as_posix()] = policy.digest(cached)
            write(profile)
            with self.assertRaisesRegex(ValueError, 'cached Inspector'):
                policy.verify_checker_profile(path)

    def test_reserved_profile_and_reference_are_refused_before_read(self):
        with patch.object(Path, 'read_text', side_effect=AssertionError('no reserved read')):
            with self.assertRaises(ValueError):
                policy.verify_checker_profile(policy.ROOT / 'evaluation/final.json')
            with self.assertRaises(ValueError):
                policy.verify_reference_artifacts({'id': 'final-private'}, 'evaluation')


if __name__ == '__main__':
    unittest.main()
