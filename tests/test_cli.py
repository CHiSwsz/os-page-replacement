"""End-to-end input, output and failure-contract tests; no third-party packages."""
import csv
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BINARY = str(Path(sys.argv.pop(1)).resolve())


class CliTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.trace = self.root / "trace with spaces.txt"
        self.trace.write_text("  0xA\n b\r\n a\n c\n", encoding="ascii")

    def run_cli(self, *args):
        return subprocess.run([BINARY, *map(str, args)], capture_output=True, text=True, check=False)

    def test_all_and_events(self):
        result = self.run_cli("--trace", self.trace, "--algorithm", "all", "--frames", "1,2")
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = list(csv.DictReader(io.StringIO(result.stdout)))
        self.assertEqual(len(rows), 14)
        self.assertEqual({row["algorithm"] for row in rows}, {"random", "fifo", "opt", "lfu", "lru", "second_chance", "adaptive"})
        for row in rows:
            self.assertEqual(int(row["references"]), 4)
            self.assertEqual(int(row["hits"]) + int(row["faults"]), 4)
        events = self.root / "events.csv"
        result = self.run_cli("--trace", self.trace, "--algorithm", "lru", "--frames", 2, "--events", events)
        self.assertEqual(result.returncode, 0, result.stderr)
        with events.open() as stream:
            records = list(csv.DictReader(stream))
        self.assertEqual([r["hit"] for r in records], ["0", "0", "1", "0"])
        self.assertEqual(records[-1]["evicted"], "b")

    def test_invalid_arguments_and_trace(self):
        base = ["--trace", self.trace, "--algorithm", "lru", "--frames"]
        for frames in ["0", "-1", "1,", "1,,2", "1,1", "18446744073709551616"]:
            with self.subTest(frames=frames):
                self.assertEqual(self.run_cli(*base, frames).returncode, 2)
        self.assertEqual(self.run_cli("--trace").returncode, 2)
        self.assertEqual(self.run_cli(*base, 2, "--unknown", "x").returncode, 2)
        self.assertEqual(self.run_cli(*base, 2, "--seed", "-1").returncode, 2)
        self.assertEqual(self.run_cli(*base, 2, "--seed", "18446744073709551616").returncode, 2)
        self.assertEqual(self.run_cli(*base, 2, "--trace", self.trace).returncode, 2)
        self.trace.write_text("abc\nnot-a-page\n")
        result = self.run_cli(*base, 2)
        self.assertEqual(result.returncode, 2)
        self.assertIn("line 2", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_missing_file_and_output_contract(self):
        result = self.run_cli("--trace", self.root / "absent", "--algorithm", "lru", "--frames", 2)
        self.assertEqual(result.returncode, 2)
        result = self.run_cli("--trace", self.trace, "--algorithm", "all", "--frames", 2, "--events", self.root / "out")
        self.assertEqual(result.returncode, 2)
        original = self.trace.read_bytes()
        for destination in [self.trace, self.root / "trace-alias"]:
            if destination != self.trace:
                destination.symlink_to(self.trace)
            result = self.run_cli("--trace", self.trace, "--algorithm", "lru", "--frames", 2, "--events", destination)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(self.trace.read_bytes(), original)

    def test_empty_trace_and_min_alias(self):
        self.trace.write_text("\n  \n")
        result = self.run_cli("--trace", self.trace, "--algorithm", "min", "--frames", 100)
        self.assertEqual(result.returncode, 0, result.stderr)
        row = next(csv.DictReader(io.StringIO(result.stdout)))
        self.assertEqual(row["algorithm"], "opt")
        self.assertEqual(row["faults"], "0")
        self.assertEqual(float(row["fault_rate"]), 0.0)

    def test_seed_reproducibility(self):
        args = ["--trace", self.trace, "--algorithm", "random", "--frames", 1, "--seed", "18446744073709551615"]
        first = self.run_cli(*args)
        second = self.run_cli(*args)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)

    def test_adaptive_options(self):
        args = ["--trace", self.trace, "--algorithm", "adaptive", "--frames", 2]
        for invalid in [0, 5, -1]:
            self.assertEqual(self.run_cli(*args, "--adaptive-version", invalid).returncode, 2)
        self.assertEqual(self.run_cli(*args, "--adaptive-version", 1).stdout,
                         self.run_cli(*args, "--adaptive-version", 2).stdout)
        for option in ["--window-factor", "--history-factor"]:
            for invalid in [0, -1, 65]:
                self.assertEqual(self.run_cli(*args, option, invalid).returncode, 2)
        result = self.run_cli(*args, "--window-factor", 2, "--history-factor", 8)
        self.assertEqual(result.returncode, 0, result.stderr)
        row = next(csv.DictReader(io.StringIO(result.stdout)))
        self.assertEqual(sum(int(row[key]) for key in ["policy_random", "policy_lru", "policy_predict"]), 4)

    def test_contest_five_counts_and_mean(self):
        self.trace.write_text(''.join(f'{i % 23:x}\n' for i in range(1300)))
        got = self.run_cli(self.trace, '--format', 'json')
        self.assertEqual(got.returncode, 0, got.stderr)
        payload = json.loads(got.stdout)
        self.assertEqual(payload['version'], 4)
        self.assertEqual([r['frames'] for r in payload['results']], [5,10,20,50,100])
        self.assertEqual(payload['average_faults'], sum(r['faults'] for r in payload['results']) / 5)
        old_interface = self.run_cli('--trace', self.trace, '--algorithm', 'adaptive', '--frames', '5,10,20,50,100', '--adaptive-version', 4)
        expected = list(csv.DictReader(io.StringIO(old_interface.stdout)))
        self.assertEqual([r['faults'] for r in payload['results']], [int(r['faults']) for r in expected])
        text = self.run_cli('--contest', '--trace', self.trace)
        self.assertIn(f"Average page faults (5 capacities): {payload['average_faults']:.2f}", text.stdout)
        result_csv = self.run_cli(self.trace, '--format', 'csv')
        rows = list(csv.DictReader(io.StringIO(result_csv.stdout)))
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[-1]['frames'], 'average')
        self.assertEqual(float(rows[-1]['faults']), payload['average_faults'])

    def test_contest_formats_bom_crlf_stdin_and_labels(self):
        decimal = '\ufeff 10\r\n\r\n2\n10\n18446744073709551615\n0\n'
        self.trace.write_text(decimal, encoding='utf-8')
        got = self.run_cli(self.trace, '--page-format', 'decimal', '--format', 'json')
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual([r['faults'] for r in json.loads(got.stdout)['results']], [4]*5)
        stdin = subprocess.run([BINARY, '--contest', '-', '--page-format', 'decimal', '--format', 'json'],
                               input=decimal, text=True, capture_output=True)
        self.assertEqual(stdin.stdout, got.stdout)
        self.trace.write_text('\ufeffA\r\n-1\nA\n'+('9'*100)+'\n零\n')
        labeled = self.run_cli(self.trace, '--page-format', 'token', '--format', 'json')
        self.assertEqual(labeled.returncode, 0, labeled.stderr)
        self.assertEqual(json.loads(labeled.stdout)['average_faults'], 4)
        self.trace.write_text('\ufeff0xA\r\na\n000a\n')
        got = self.run_cli(self.trace, '--format', 'json')
        self.assertEqual(json.loads(got.stdout)['average_faults'], 1)
        legacy = self.run_cli('--trace', self.trace, '--algorithm', 'lru', '--frames', 5)
        self.assertEqual(legacy.returncode, 0, legacy.stderr)

    def test_contest_empty_errors_and_no_partial_score(self):
        for bad in [['--contest'], [self.trace, '--format', 'xml'], [self.trace, '--page-format', 'auto'],
                    [self.trace, self.trace], [self.trace, '--trace', self.trace],
                    [self.trace, '--seed', '-1'], [self.trace, '--window-factor', 0],
                    [self.trace, '--history-factor', 65], [self.trace, '--format'],
                    [self.trace, '--format', 'json', '--format', 'csv']]:
            result = self.run_cli(*bad)
            self.assertEqual(result.returncode, 2, str(bad))
            self.assertEqual(result.stdout, '')
        self.trace.write_text('\ufeff\n \r\n')
        empty = self.run_cli(self.trace, '--format', 'json')
        self.assertEqual(json.loads(empty.stdout)['average_faults'], 0)
        self.assertEqual(json.loads(empty.stdout)['references'], 0)
        for fmt, bad_page in [('hex','xyz'),('hex','10000000000000000'),('decimal','0x1'),('token','one two')]:
            self.trace.write_text('1\n2\n'+bad_page+'\n')
            bad = self.run_cli(self.trace, '--page-format', fmt)
            self.assertEqual(bad.returncode, 2)
            self.assertIn('line 3', bad.stderr)
            self.assertEqual(bad.stdout, '')
        self.assertEqual(self.run_cli('--contest', '--help').returncode, 0)


if __name__ == "__main__":
    unittest.main()
