"""Host-side boundary tests, independent of Docker availability."""
import json
from pathlib import Path
import tempfile
import unittest
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

