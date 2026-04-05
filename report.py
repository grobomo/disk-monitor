"""
Report generator for disk-monitor skill.
Combines scan.py + git-hygiene.py output into a formatted email report.
Sends via email-manager skill.
"""

import json
import subprocess
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).parent
EMAIL_MANAGER = Path(os.environ.get("USERPROFILE") or os.path.expanduser("~")) / "Documents" / "ProjectsCL1" / "email-manager"


def generate_report(scan_file=None, git_file=None):
    """Generate a formatted text report from scan and git hygiene data."""
    scan_data = []
    git_data = []

    if scan_file and os.path.exists(scan_file):
        with open(scan_file) as f:
            scan_data = json.load(f)

    if git_file and os.path.exists(git_file):
        with open(git_file) as f:
            git_data = json.load(f)

    lines = []
    lines.append("=" * 60)
    lines.append("DISK MONITOR REPORT")
    lines.append(f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
    lines.append("=" * 60)

    # Disk scan section
    if scan_data:
        total_gb = sum(e.get("size_gb", 0) for e in scan_data)
        by_cat = {}
        for e in scan_data:
            cat = e.get("category", "UNKNOWN")
            by_cat.setdefault(cat, [])
            by_cat[cat].append(e)

        lines.append(f"\nDISK USAGE: {total_gb:.1f} GB scanned across {len(scan_data)} directories\n")

        for cat in ["AUTO-SAFE", "REVIEW", "NEVER-TOUCH"]:
            items = by_cat.get(cat, [])
            if not items:
                continue
            cat_gb = sum(e.get("size_gb", 0) for e in items)
            lines.append(f"--- {cat} ({len(items)} items, {cat_gb:.1f} GB) ---")
            for e in items[:15]:
                path = e.get("path", "?")
                size = f"{e.get('size_gb', 0):.1f} GB" if e.get("size_gb", 0) >= 1 else f"{e.get('size_mb', 0):.0f} MB"
                desc = e.get("pattern_description", "")
                lines.append(f"  {size:>8}  {path}")
                if desc and desc != "No matching pattern — defaults to REVIEW":
                    lines.append(f"           {desc}")
            if len(items) > 15:
                lines.append(f"  ... and {len(items) - 15} more")
            lines.append("")

    # Git hygiene section
    if git_data:
        issues_repos = [r for r in git_data if r.get("issues")]
        clean_repos = [r for r in git_data if not r.get("issues")]

        lines.append(f"\nGIT HYGIENE: {len(git_data)} repos ({len(issues_repos)} with issues)\n")

        if issues_repos:
            lines.append("--- REPOS WITH ISSUES ---")
            for r in issues_repos:
                lines.append(f"  {r['path']}")
                lines.append(f"    Branch: {r.get('branch', '?')}  Issues: {', '.join(r.get('issues', []))}")
                if r.get("stale_branches"):
                    lines.append(f"    Stale branches: {', '.join(r['stale_branches'][:5])}")
                if r.get("large_untracked"):
                    for f in r["large_untracked"][:3]:
                        lines.append(f"    Large untracked: {f['path']} ({f['size_mb']} MB)")
            lines.append("")

        if clean_repos:
            lines.append(f"--- CLEAN REPOS ({len(clean_repos)}) ---")
            for r in clean_repos[:10]:
                lines.append(f"  {r['path']} ({r.get('branch', '?')})")
            if len(clean_repos) > 10:
                lines.append(f"  ... and {len(clean_repos) - 10} more")
            lines.append("")

    # Action items
    if scan_data:
        auto_safe = [e for e in scan_data if e.get("category") == "AUTO-SAFE"]
        review = [e for e in scan_data if e.get("category") == "REVIEW"]
        if auto_safe or review:
            lines.append("=" * 60)
            lines.append("ACTION ITEMS")
            lines.append("=" * 60)
            if auto_safe:
                safe_gb = sum(e.get("size_gb", 0) for e in auto_safe)
                lines.append(f"\nAUTO-SAFE candidates: {len(auto_safe)} items, {safe_gb:.1f} GB")
                lines.append("Reply 'approve auto-safe' to clean these.")
            if review:
                rev_gb = sum(e.get("size_gb", 0) for e in review)
                lines.append(f"\nREVIEW candidates: {len(review)} items, {rev_gb:.1f} GB")
                lines.append("Reply with specific paths to approve.")
            lines.append("")

    return "\n".join(lines)


def send_email(subject, body):
    """Send report via email-manager."""
    send_script = EMAIL_MANAGER / "send.py"
    if not send_script.exists():
        print(f"email-manager not found at {send_script}", file=sys.stderr)
        print("Report printed to stdout instead.\n")
        print(body)
        return False

    cmd = [
        sys.executable, str(send_script),
        "--to", "me",
        "--subject", subject,
        "--body", body
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode == 0:
        print(f"Report emailed successfully.")
        return True
    else:
        print(f"Email failed: {result.stderr}", file=sys.stderr)
        print("Report printed to stdout instead.\n")
        print(body)
        return False


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate and email disk monitor report")
    parser.add_argument("--scan-file", help="Path to scan.py JSON output")
    parser.add_argument("--git-file", help="Path to git-hygiene.py JSON output")
    parser.add_argument("--email", action="store_true", help="Send report via email")
    parser.add_argument("--output", help="Write report to file")
    args = parser.parse_args()

    report = generate_report(scan_file=args.scan_file, git_file=args.git_file)

    if args.output:
        with open(args.output, "w") as f:
            f.write(report)
        print(f"Report written to {args.output}")

    if args.email:
        subject = f"Disk Monitor Report — {datetime.now().strftime('%Y-%m-%d')}"
        send_email(subject, report)
    else:
        print(report)


if __name__ == "__main__":
    main()
