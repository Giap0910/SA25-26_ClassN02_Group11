"""Kiểm tra đặc tả, sinh mã và đối chiếu C sinh ra với oracle độc lập."""
import copy
import json
import os
from pathlib import Path
import subprocess
import unittest
import uuid
from unittest.mock import patch

import fuzz_runner as runner
import generate_simulator as generator


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.spec = generator.load_spec()
        cls.directory = runner.OUTPUT / ('generator-tests-' + uuid.uuid4().hex[:8])
        cls.directory.mkdir(parents=True)
        cls.gcc = runner.OUTPUT / 'toolchain/mingw64/bin/gcc.exe'
        os.environ['PATH'] = str(cls.gcc.parent) + os.pathsep + os.environ.get('PATH', '')

    def compile_spec(self, spec, label):
        directory = self.directory / label
        directory.mkdir()
        source = directory / 'generated.c'
        source.write_text(generator.generate(spec), encoding='utf-8')
        return runner.compile_target(directory, str(self.gcc), source), directory

    def test_backend_fingerprint(self):
        self.assertEqual(len(self.spec['backend_sha256']), 2)

    def test_reject_arbitrary_code(self):
        for text in ('__import__("os")', 'q.__class__', 'q * q', 'unknown', '2147483648'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                generator.translate(text)

    def test_generation_is_deterministic(self):
        self.assertEqual(generator.generate(self.spec), generator.generate(copy.deepcopy(self.spec)))

    def test_generated_regressions(self):
        binary, directory = self.compile_spec(self.spec, 'regression')
        self.assertEqual(runner.regressions(binary, directory), 25)

    def test_spec_changes_executed_behavior(self):
        changed = copy.deepcopy(self.spec)
        changed['operations']['reserve'][0]['when'] = 'q < 1 or q > 50'
        binary, directory = self.compile_spec(changed, 'changed-limit')
        data = directory / 'quantity-51.bin'
        data.write_bytes(runner.pack(100, 0, 100, 0, 51, 0))
        process = subprocess.run([str(binary), str(data)], capture_output=True, text=True, timeout=2)
        self.assertEqual(process.returncode, 0)
        self.assertEqual(json.loads(process.stdout)['status'], 'rejected')
        self.assertEqual(runner.oracle(data.read_bytes())[0], 'accepted')

    def test_operation_sets_are_present(self):
        source = generator.generate(self.spec)
        self.assertIn('static int reserve(', source)
        self.assertIn('static int settle(', source)
        self.assertNotEqual(source, runner.SOURCE.read_text(encoding='utf-8'))

    def test_handwritten_business_rules_are_not_copied(self):
        expected = generator.generate(self.spec)
        adapter = runner.SOURCE.read_text(encoding='utf-8').replace('q > 100', 'q > 3')
        with patch.object(Path, 'read_text', return_value=adapter):
            self.assertEqual(generator.generate(self.spec), expected)

    def test_backend_change_stops_generation(self):
        changed = copy.deepcopy(self.spec)
        changed['backend_sha256']['OrderService.java'] = '0' * 64
        path = self.directory / 'stale-spec.json'
        path.write_text(json.dumps(changed), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'đã đổi'):
            generator.load_spec(path)

    def test_requirement_traceability(self):
        tables = self.spec['teacher_tables']
        requirements = {row[0] for row in tables['YeuCauChucNang'][1:]}
        cases = {row[0]: row[1] for row in tables['TestCase'][1:]}
        self.assertEqual(len(tables), 10)
        self.assertEqual({row['requirement'] for row in self.spec['traceability']}, requirements)
        for row in self.spec['traceability']:
            self.assertEqual(cases[row['cases']], row['requirement'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
