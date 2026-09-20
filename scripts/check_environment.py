"""Check Step 2 prerequisites without reading datasets or calling models."""

import argparse
from pathlib import Path
import sqlite3
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def report(name, passed, detail):
    print(f"{'PASS' if passed else 'FAIL'}: {name} - {detail}")
    return passed


def command_check(name, command, expected=None):
    """Run a bounded external check and preserve useful failure output."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            cwd=ROOT,
            check=False,
        )
    except FileNotFoundError:
        return report(name, False, f"Command not found: {command[0]}")
    except subprocess.TimeoutExpired:
        return report(name, False, "Command exceeded 30 seconds")

    output = result.stdout.strip()
    passed = result.returncode == 0 and (
        expected is None or expected in output
    )
    if passed:
        detail = output.splitlines()[0] if output else "Command succeeded"
    else:
        detail = f"Exit {result.returncode}: {output}\n{result.stderr.strip()}"
    return report(name, passed, detail)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--docker-smoke",
        action="store_true",
        help="Run the cached hello-world container without network access",
    )
    args = parser.parse_args()
    checks = [
        report("Python 3.12", sys.version_info[:2] == (3, 12), sys.version.split()[0]),
        report(
            "Project virtual environment",
            Path(sys.prefix).resolve() == (ROOT / ".venv").resolve()
            and sys.prefix != sys.base_prefix,
            sys.executable,
        ),
    ]

    try:
        connection = sqlite3.connect(":memory:")
        try:
            sqlite_ok = connection.execute("SELECT 1").fetchone() == (1,)
        finally:
            connection.close()
        checks.append(report("SQLite", sqlite_ok, sqlite3.sqlite_version))
    except sqlite3.Error as error:
        checks.append(report("SQLite", False, str(error)))

    checks.append(command_check("pip", [sys.executable, "-m", "pip", "check"]))
    checks.append(command_check("Git", ["git", "--version"]))
    checks.append(command_check("Docker Compose", ["docker", "compose", "version"]))
    checks.append(command_check(
        "Docker Linux engine", ["docker", "info", "--format", "{{.OSType}}"], "linux"
    ))
    if args.docker_smoke:
        checks.append(command_check(
            "Docker smoke",
            ["docker", "run", "--rm", "--network", "none", "--pull=never", "hello-world:latest"],
            "Hello from Docker!",
        ))

    print(f"\nStep 2 checks: {sum(checks)}/{len(checks)} passed.")
    print("Model inference, OCR, application behavior, and evaluation remain unverified.")
    return 0 if all(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
