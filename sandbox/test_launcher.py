"""Host-side boundary tests, independent of Docker availability."""
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch

from sandbox.launcher import SandboxRunner, RunnerError, scan_outputs, validate_name, MAX_OUTPUT


class HostPolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.runner = SandboxRunner(self.root / "runs", docker_bin="does-not-exist-docker")

    def tearDown(self):
        self.tmp.cleanup()

    def test_unavailable_never_executes_python(self):
        marker = self.root / "host-executed"
        result = self.runner.run(f"open({str(marker)!r}, 'w').write('unsafe')", {}, project_id="A")
        self.assertEqual(result["status"], "runner_unavailable")
        self.assertFalse(marker.exists())

    def test_cli_does_not_inherit_open_rpc_input_pipe(self):
        # Trusted fake CLI, not generated analysis code. Keep the parent's RPC
        # stdin open: a child inheriting it blocks (or steals protocol bytes).
        probe=("from sandbox.launcher import SandboxRunner\nimport sys\n"
               f"r=SandboxRunner({str(self.root/'pipe-probe')!r},docker_bin=sys.executable)\n"
               "p=r._exec(['-c',\"import sys; print('EOF', repr(sys.stdin.read()))\"],timeout=2)\n"
               "print(p.stdout.strip())\n")
        child=subprocess.Popen([sys.executable,'-c',probe],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            child.wait(timeout=8)
            self.assertEqual(child.returncode,0,child.stderr.read().decode())
            self.assertIn(b"EOF ''",child.stdout.read())
        finally:
            if child.poll() is None:child.kill();child.wait()
            child.stdin.close();child.stdout.close();child.stderr.close()

    def test_code_and_timeout_bounds(self):
        for code, timeout in [("", 120), ("print(1)", 121), ("print(1)", 0), ("print(1)", True)]:
            with self.assertRaises(RunnerError):
                self.runner.run(code, {}, project_id="A", timeout_seconds=timeout)

    def test_input_path_names(self):
        for name in ["../x", r"..\x", "/absolute", "C:x", ".", "..", "NUL", "con.txt", "x.", "x "]:
            with self.subTest(name=name), self.assertRaises(RunnerError):
                validate_name(name)
        self.assertEqual(validate_name("营业收入.csv"), "营业收入.csv")

    def test_source_link_refused(self):
        original = self.root / "source.json"
        original.write_text("{}")
        link = self.root / "link.json"
        try:
            link.symlink_to(original)
        except OSError:
            self.skipTest("OS does not permit symlink creation")
        with self.assertRaises(RunnerError):
            self.runner.run("print(1)", {"input.json": link}, project_id="A")

    def test_manifest_rejects_oversize(self):
        output = self.root / "output"
        output.mkdir()
        with (output / "too-big").open("wb") as stream:
            stream.seek(MAX_OUTPUT)
            stream.write(b"x")
        with self.assertRaisesRegex(RunnerError, "50 MiB"):
            scan_outputs(output)

    def test_manifest_rejects_symlink(self):
        output = self.root / "output"
        output.mkdir()
        try:
            (output / "escape").symlink_to(self.root, target_is_directory=True)
        except OSError:
            self.skipTest("OS does not permit symlink creation")
        with self.assertRaisesRegex(RunnerError, "links"):
            scan_outputs(output)

    def test_manifest_regular_files(self):
        output = self.root / "output"
        output.mkdir()
        (output / "chart.png").write_bytes(b"abc")
        self.assertEqual(scan_outputs(output), [{"name": "chart.png", "size": 3}])

    def test_project_isolation_and_idempotent_ids(self):
        state = self.runner.run("print(1)", {}, project_id="A", run_id="same")
        with self.assertRaises(RunnerError):
            self.runner.status("same", project_id="B")
        with self.assertRaises(RunnerError):
            self.runner.run("print(1)", {}, project_id="A", run_id="same")
        self.assertEqual(self.runner.status("same", project_id="A"), state)

    def test_script_output_and_error_reach_returned_and_persisted_result(self):
        from unittest.mock import patch
        def command(args, **kwargs):
            stdout = ''
            stderr = ''
            if args[0] == 'inspect':
                stdout = json.dumps({'Running': False, 'ExitCode': 1}) if '--format' in args else '[{}]'
            elif args[0] == 'logs':
                stdout = 'loaded 612 rows\n'
                stderr = 'File /input/analysis.py, line 7\nNameError: missing_series\n'
            return subprocess.CompletedProcess(args, 0, stdout, stderr)
        with patch.object(self.runner, 'availability', return_value={'available': True, 'image_id': 'sha256:'+'a'*64}), patch.object(self.runner, '_exec', side_effect=command), patch.object(self.runner, '_verify_config'):
            state = self.runner.run('print(1)', {}, project_id='A')
        self.assertEqual(state['status'], 'failed')
        self.assertEqual(state['stdout'], 'loaded 612 rows\n')
        self.assertIn('NameError: missing_series', state['stderr'])
        self.assertEqual(self.runner.status(state['run_id'], project_id='A')['stderr'], state['stderr'])

    def _run_with_fake_engine(self, runner, inputs):
        def command(args, **kwargs):
            stdout = ''
            if args[0] == 'inspect':
                stdout = json.dumps({'Running': False, 'ExitCode': 0}) if '--format' in args else '[{}]'
            return subprocess.CompletedProcess(args, 0, stdout, '')
        with patch.object(runner, 'availability', return_value={'available': True, 'image_id': 'sha256:'+'a'*64}), patch.object(runner, '_exec', side_effect=command), patch.object(runner, '_verify_config'):
            return runner.run('print(1)', inputs, project_id='A')

    def test_shared_snapshots_are_linked_and_every_other_input_is_copied(self):
        import os
        from sandbox.launcher import SHARED_FOLDER, digest
        exports = self.root / 'exports'
        store = exports / 'A' / SHARED_FOLDER
        store.mkdir(parents=True)
        snapshot = store / ('b' * 64 + '.json')
        snapshot.write_text('{"pages":[]}', encoding='utf-8')
        script = exports / 'A' / 'run' / 'analysis.py'
        script.parent.mkdir()
        script.write_text('pass', encoding='utf-8')
        # Same folder name outside the configured root is an ordinary file.
        foreign = self.root / 'elsewhere' / SHARED_FOLDER / 'data.json'
        foreign.parent.mkdir(parents=True)
        foreign.write_text('{}', encoding='utf-8')
        runner = SandboxRunner(self.root / 'linked-runs', docker_bin='does-not-exist-docker', shared_inputs=exports)
        state = self._run_with_fake_engine(runner, {'pages.json': snapshot, 'analysis.py': script, 'data.json': foreign})
        self.assertEqual(state['status'], 'succeeded', state.get('error'))
        mounted = runner.root / state['run_id'] / 'input'
        self.assertTrue(os.path.samefile(mounted / 'pages.json', snapshot))
        self.assertFalse(os.path.samefile(mounted / 'analysis.py', script))
        self.assertFalse(os.path.samefile(mounted / 'data.json', foreign))
        self.assertEqual((mounted / 'analysis.py').read_text(encoding='utf-8'), 'pass')
        self.assertEqual(state['input_sha256']['pages.json'], digest(snapshot))
        self.assertEqual(sorted(state['input_sha256']), ['analysis.py', 'data.json', 'pages.json'])
        # Without a configured root nothing is linked, as before.
        plain = self._run_with_fake_engine(self.runner, {'pages.json': snapshot})
        self.assertFalse(os.path.samefile(self.runner.root / plain['run_id'] / 'input' / 'pages.json', snapshot))

    def test_snapshot_that_cannot_be_linked_is_copied(self):
        import os
        from sandbox.launcher import SHARED_FOLDER
        exports = self.root / 'exports'
        snapshot = exports / 'A' / SHARED_FOLDER / ('c' * 64 + '.json')
        snapshot.parent.mkdir(parents=True)
        snapshot.write_text('[1]', encoding='utf-8')
        runner = SandboxRunner(self.root / 'copied-runs', docker_bin='does-not-exist-docker', shared_inputs=exports)
        with patch('sandbox.launcher.os.link', side_effect=OSError(31, 'Too many links')):
            state = self._run_with_fake_engine(runner, {'pages.json': snapshot})
        self.assertEqual(state['status'], 'succeeded', state.get('error'))
        mounted = runner.root / state['run_id'] / 'input' / 'pages.json'
        self.assertFalse(os.path.samefile(mounted, snapshot))
        self.assertEqual(mounted.read_text(encoding='utf-8'), '[1]')

    def test_artifact_refuses_traversal_and_tampering(self):
        run = self.runner.root / "known"
        output = run / "output"
        output.mkdir(parents=True)
        path = output / "chart.png"
        path.write_bytes(b"abc")
        from sandbox.launcher import digest
        state = {"run_id": "known", "project_id": "A", "status": "succeeded",
                 "artifacts": [{"name": "chart.png", "size": 3, "sha256": digest(path)}]}
        self.runner._write(run, state)
        self.assertEqual(self.runner.artifact_path("known", "chart.png", project_id="A"), path)
        nested=output/'model'/'forecast.csv'
        nested.parent.mkdir();nested.write_bytes(b'year,value\n2025,1\n')
        state['artifacts'].append({'name':'model/forecast.csv','size':nested.stat().st_size,'sha256':digest(nested)})
        self.runner._write(run,state)
        self.assertEqual(self.runner.artifact_path('known','model/forecast.csv',project_id='A'),nested)
        with self.assertRaises(RunnerError):self.runner.artifact_path('known','model/forecast.csv',project_id='other')
        for name in ["../chart.png", "/chart.png", r"..\chart.png", "missing", "./chart.png", "C:chart.png"]:
            with self.subTest(name=name), self.assertRaises(RunnerError):
                self.runner.artifact_path("known", name, project_id="A")
        path.write_bytes(b"changed")
        with self.assertRaisesRegex(RunnerError, "integrity"):
            self.runner.artifact_path("known", "chart.png", project_id="A")

    def test_command_has_required_boundary(self):
        cmd = self.runner.command(run_id="r1", input_dir=self.root / "in",
                                  output_dir=self.root / "out", image_id="sha256:" + "a" * 64)
        pairs = dict(zip(cmd[1::2], cmd[2::2]))
        self.assertIn("--read-only", cmd)
        for flag, value in [("--network", "none"), ("--user", "10001:10001"), ("--cpus", "2"),
                            ("--memory", "2g"), ("--memory-swap", "2g"), ("--pids-limit", "64"),
                            ("--security-opt", "no-new-privileges=true"), ("--cap-drop", "ALL")]:
            self.assertEqual(cmd[cmd.index(flag) + 1], value)
        self.assertFalse(any("docker.sock" in item or "API_KEY" in item for item in cmd))

    def test_config_audit_rejects_missing_policy(self):
        with self.assertRaisesRegex(RunnerError, "NetworkMode"):
            self.runner._verify_config({"HostConfig": {}, "Config": {}})


if __name__ == "__main__":
    unittest.main(verbosity=2)
