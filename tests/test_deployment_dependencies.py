"""Run Linux upgrade control flow with local service, package and pip doubles."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def find_bash():
    binary = shutil.which("bash")
    if not binary and os.name == "nt" and shutil.which("git"):
        candidate = Path(shutil.which("git")).parent.parent / "bin/bash.exe"
        binary = str(candidate) if candidate.is_file() else None
    return binary


def shell_path(path):
    value = Path(path).resolve().as_posix()
    return "/" + value[0].lower() + value[2:] if os.name == "nt" else value


@unittest.skipUnless(find_bash(), "Bash is required for Linux deployment checks")
class DeploymentDependencyTests(unittest.TestCase):
    def test_path_options_without_values_fail_before_deployment(self):
        for script, options in (("deploy.sh", ("--target",)),
                                ("upgrade.sh", ("--package", "--dir", "--target"))):
            for option in options:
                for extra in ([], ["--no-units"]):
                    with self.subTest(script=script, option=option, extra=extra):
                        result = subprocess.run(
                            [find_bash(), shell_path(ROOT / "deploy/linux" / script), option, *extra],
                            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=3,
                        )
                        self.assertEqual(result.returncode, 2)
                        self.assertIn(option, result.stderr)

    def exercise(self, script_name, failure="", browser_missing=False):
        with tempfile.TemporaryDirectory(prefix="douyin-deploy-test-") as directory:
            root = Path(directory)
            target, fixture, commands = (root / name for name in ("target", "fixture", "commands"))
            for path in (target / ".venv/bin", target / ".browsers", fixture / "original_parser",
                         fixture / "deploy/linux", commands):
                path.mkdir(parents=True, exist_ok=True)
            for path in (fixture / "run.py", fixture / "original_parser/guard.py", fixture / "requirements.txt"):
                path.write_text("# isolated test fixture\n", encoding="utf-8")
            archive = root / "fixture.tar.gz"
            archive.touch()
            log = root / "calls.txt"

            def executable(path, body):
                path.write_text("#!/usr/bin/env bash\n" + body, encoding="utf-8", newline="\n")
                path.chmod(0o755)

            executable(commands / "id", "echo 0\n")
            executable(commands / "systemctl", 'echo "service $*" >> "$DEPLOY_TEST_LOG"\n')
            executable(commands / "sleep", "exit 0\n")
            executable(commands / "journalctl", "echo 'protection interval'\n")
            executable(commands / "curl", "exit 0\n")
            # No extraction or backup outside the test fixture.
            executable(commands / "tar", 'if [ "$1" = "-xzf" ]; then cp -a "$DEPLOY_TEST_FIXTURE/." "$4/"; fi\n')
            executable(target / ".venv/bin/python", '''echo "python $*" >> "$DEPLOY_TEST_LOG"
if [ "$1 $2 $3" = "-m pip install" ] && [ "$DEPLOY_TEST_FAILURE" = "install" ]; then exit 9; fi
if [ "$1 $2" = "-m original_parser.check_runtime" ] && [ "$DEPLOY_TEST_FAILURE" = "runtime" ]; then exit 8; fi
if [ "$1" = "-c" ] && [ "$DEPLOY_TEST_BROWSER_MISSING" = "1" ]; then exit 1; fi
exit 0
''')
            env = dict(os.environ, DEPLOY_TEST_LOG=shell_path(log),
                       DEPLOY_TEST_FIXTURE=shell_path(fixture), DEPLOY_TEST_FAILURE=failure,
                       DEPLOY_TEST_BROWSER_MISSING="1" if browser_missing else "0")
            args = [find_bash(), "-c", 'export PATH="$1:$PATH"; shift; exec bash "$@"',
                    "deploy-test", shell_path(commands), shell_path(ROOT / "deploy/linux" / script_name),
                    shell_path(archive), "--target", shell_path(target)]
            if script_name == "upgrade.sh":
                args.append("--no-units")
            result = subprocess.run(args, env=env, capture_output=True, text=True,
                                    encoding="utf-8", errors="replace", timeout=20)
            calls = log.read_text(encoding="utf-8").splitlines() if log.exists() else []
            return result, calls

    def test_dependencies_and_signature_are_checked_before_service_restart(self):
        for script in ("deploy.sh", "upgrade.sh"):
            with self.subTest(script=script):
                result, calls = self.exercise(script)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                install = next(i for i, c in enumerate(calls) if c.startswith("python -m pip install -r "))
                runtime = calls.index("python -m original_parser.check_runtime")
                restart = calls.index("service restart douyin-original-parser")
                self.assertLess(install, runtime)
                self.assertLess(runtime, restart)
                self.assertIn("python -m pip check", calls)
                self.assertFalse(any(c.startswith("python -m playwright install") for c in calls))

    def test_failed_install_or_signature_check_never_starts_service(self):
        for script in ("deploy.sh", "upgrade.sh"):
            for failure in ("install", "runtime"):
                with self.subTest(script=script, failure=failure):
                    result, calls = self.exercise(script, failure=failure)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("service stop douyin-original-parser", calls)
                    self.assertNotIn("service restart douyin-original-parser", calls)

    def test_playwright_update_installs_missing_browser_before_restart(self):
        for script in ("deploy.sh", "upgrade.sh"):
            with self.subTest(script=script):
                result, calls = self.exercise(script, browser_missing=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                browser = calls.index("python -m playwright install --with-deps chromium --no-shell")
                self.assertLess(browser, calls.index("service restart douyin-original-parser"))


if __name__ == "__main__":
    unittest.main()
