"""
Weekly disk monitor: scan, git hygiene, generate report, email.
Called by claude-scheduler on a weekly interval.
"""

import json
import subprocess
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).parent
USER_HOME = Path(os.environ.get("USERPROFILE") or os.path.expanduser("~"))
SCAN_OUTPUT = SKILL_DIR / "last-scan.json"
GIT_OUTPUT = SKILL_DIR / "last-git-hygiene.json"


def run_step(name, cmd, timeout=600):
    """Run a subprocess step with error handling."""
    print(f"[{name}] Running...")
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            print(f"[{name}] Warning: exit code {result.returncode}")
            if result.stderr:
                print(f"  stderr: {result.stderr[:200]}")
            return False
        print(f"[{name}] Done.")
        return True
    except subprocess.TimeoutExpired:
        print(f"[{name}] Timed out after {timeout}s")
        return False
    except Exception as e:
        print(f"[{name}] Error: {e}")
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Weekly disk monitor run")
    parser.add_argument("--no-email", action="store_true", help="Skip email, print report only")
    parser.add_argument("--min-size-mb", type=float, default=50, help="Min dir size to report (MB)")
    args = parser.parse_args()

    py = sys.executable

    # Step 1: Disk scan
    scan_ok = run_step("scan", [
        py, str(SKILL_DIR / "scan.py"),
        "--min-size-mb", str(args.min_size_mb),
        "--depth", "1",
        "--json", "--output", str(SCAN_OUTPUT)
    ], timeout=600)

    # Step 2: Git hygiene
    git_ok = run_step("git-hygiene", [
        py, str(SKILL_DIR / "git-hygiene.py"),
        "--root", str(USER_HOME / "Documents" / "ProjectsCL1"),
        "--json", "--output", str(GIT_OUTPUT)
    ], timeout=120)

    # Step 3: Generate and send report
    if not scan_ok and not git_ok:
        print("Both scans failed. No report generated.")
        sys.exit(1)

    report_cmd = [
        py, str(SKILL_DIR / "report.py"),
    ]
    if scan_ok:
        report_cmd.extend(["--scan-file", str(SCAN_OUTPUT)])
    if git_ok:
        report_cmd.extend(["--git-file", str(GIT_OUTPUT)])
    if not args.no_email:
        report_cmd.append("--email")

    report_ok = run_step("report", report_cmd, timeout=60)

    if scan_ok and git_ok and report_ok:
        print("\nWeekly disk monitor completed successfully.")
    else:
        print("\nWeekly disk monitor completed with warnings.")
        sys.exit(0 if (scan_ok or git_ok) else 1)


if __name__ == "__main__":
    main()
