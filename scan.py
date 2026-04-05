"""
Disk scanner for disk-monitor skill.
Uses PowerShell to enumerate directory sizes under C:\\Users\\joelg.
Categorizes each directory using patterns.json.
Output: JSON to stdout.
"""

import json
import subprocess
import sys
import os
import fnmatch
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

SKILL_DIR = Path(__file__).parent
PATTERNS_FILE = SKILL_DIR / "patterns.json"
USER_HOME = Path(os.environ.get("USERPROFILE", r"C:\Users\joelg"))

# PowerShell script to enumerate top-level directory sizes
PS_SCRIPT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$root = $args[0]
$depth = [int]$args[1]

function Get-DirInfo {
    param([string]$Path)
    $info = @{
        path = $Path
        size_bytes = 0
        file_count = 0
        last_modified = $null
    }
    try {
        $items = Get-ChildItem -Path $Path -Recurse -File -Force -ErrorAction SilentlyContinue
        if ($items) {
            $info.size_bytes = ($items | Measure-Object -Property Length -Sum).Sum
            $info.file_count = $items.Count
            $newest = ($items | Sort-Object LastWriteTime -Descending | Select-Object -First 1)
            if ($newest) {
                $info.last_modified = $newest.LastWriteTime.ToUniversalTime().ToString("o")
            }
        }
    } catch {}
    $info | ConvertTo-Json -Compress
}

# Enumerate directories at the requested depth
$dirs = Get-ChildItem -Path $root -Directory -Force -ErrorAction SilentlyContinue
foreach ($dir in $dirs) {
    if ($depth -le 1) {
        Get-DirInfo $dir.FullName
    } else {
        $subdirs = Get-ChildItem -Path $dir.FullName -Directory -Force -ErrorAction SilentlyContinue
        if ($subdirs) {
            foreach ($sub in $subdirs) {
                Get-DirInfo $sub.FullName
            }
        } else {
            Get-DirInfo $dir.FullName
        }
    }
}
"""


def load_patterns():
    """Load patterns.json and return list of pattern dicts."""
    with open(PATTERNS_FILE, "r") as f:
        data = json.load(f)
    return data["patterns"]


def _glob_to_regex(glob_pattern):
    """Convert a glob pattern with ** support into a regex."""
    import re
    # Normalize separators
    pattern = glob_pattern.replace("\\", "/")
    # Escape regex special chars except * and ?
    parts = []
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == '*' and i + 1 < len(pattern) and pattern[i + 1] == '*':
            # ** matches any path segments
            parts.append(".*")
            i += 2
            if i < len(pattern) and pattern[i] == '/':
                i += 1  # skip trailing slash after **
        elif c == '*':
            parts.append("[^/]*")
            i += 1
        elif c == '?':
            parts.append("[^/]")
            i += 1
        elif c in r'\.+^${}()|[]':
            parts.append('\\' + c)
            i += 1
        else:
            parts.append(c)
            i += 1
    return re.compile("".join(parts), re.IGNORECASE)


def categorize(path_str, last_modified_str, patterns):
    """
    Match a path against patterns. Returns (category, pattern_id, description).
    Most specific match wins (longest glob). Default: REVIEW.
    """
    import re
    normalized = path_str.replace("\\", "/")
    matches = []

    for p in patterns:
        regex = _glob_to_regex(p["glob"])
        if regex.search(normalized):
            # Check min_age_days if applicable
            if p.get("min_age_days") is not None and p["min_age_days"] > 0 and last_modified_str:
                try:
                    last_mod = datetime.fromisoformat(last_modified_str.replace("Z", "+00:00"))
                    age = datetime.now(timezone.utc) - last_mod
                    if age.days < p["min_age_days"]:
                        continue  # Too recent for this pattern
                except (ValueError, TypeError):
                    pass
            matches.append(p)

    if not matches:
        return "REVIEW", "unknown", "No matching pattern -- defaults to REVIEW"

    # Most specific = longest glob (proxy for specificity)
    best = max(matches, key=lambda p: len(p["glob"]))
    return best["category"], best["id"], best["description"]


def run_scan(scan_root=None, depth=1, min_size_mb=0):
    """Run PowerShell scan and return categorized results."""
    root = scan_root or str(USER_HOME)
    patterns = load_patterns()

    # Write PS script to temp file and execute
    ps_file = tempfile.NamedTemporaryFile(mode="w", suffix=".ps1", delete=False)
    try:
        ps_file.write(PS_SCRIPT)
        ps_file.close()
        cmd = [
            "powershell.exe", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-File", ps_file.name, root, str(depth)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    finally:
        os.unlink(ps_file.name)

    if result.returncode != 0 and not result.stdout.strip():
        print(f"PowerShell error: {result.stderr}", file=sys.stderr)
        sys.exit(1)

    # Parse output — each line is a JSON object
    entries = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue

        size_mb = entry.get("size_bytes", 0) / (1024 * 1024)
        if size_mb < min_size_mb:
            continue

        category, pattern_id, description = categorize(
            entry["path"],
            entry.get("last_modified"),
            patterns
        )
        entry["size_mb"] = round(size_mb, 1)
        entry["size_gb"] = round(size_mb / 1024, 2)
        entry["category"] = category
        entry["pattern_id"] = pattern_id
        entry["pattern_description"] = description
        entries.append(entry)

    # Sort by size descending
    entries.sort(key=lambda e: e.get("size_bytes", 0), reverse=True)
    return entries


def print_summary(entries):
    """Print human-readable summary."""
    total_gb = sum(e.get("size_gb", 0) for e in entries)
    by_category = {}
    for e in entries:
        cat = e["category"]
        by_category.setdefault(cat, {"count": 0, "size_gb": 0})
        by_category[cat]["count"] += 1
        by_category[cat]["size_gb"] += e.get("size_gb", 0)

    print(f"\n{'='*70}")
    print(f"Disk Scan Summary -- {len(entries)} directories, {total_gb:.1f} GB total")
    print(f"{'='*70}")

    for cat in ["AUTO-SAFE", "REVIEW", "NEVER-TOUCH"]:
        if cat in by_category:
            info = by_category[cat]
            print(f"\n  {cat}: {info['count']} dirs, {info['size_gb']:.1f} GB")

    print(f"\n{'-'*70}")
    print(f"{'Path':<50} {'Size':>8} {'Category':<12}")
    print(f"{'-'*70}")
    for e in entries[:30]:  # Top 30 by size
        path = e["path"].replace(str(USER_HOME), "~")
        if len(path) > 48:
            path = "..." + path[-45:]
        size = f"{e['size_gb']:.1f} GB" if e["size_gb"] >= 1 else f"{e['size_mb']:.0f} MB"
        print(f"  {path:<48} {size:>8} {e['category']:<12}")

    print(f"{'-'*70}\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Scan disk usage and categorize directories")
    parser.add_argument("--root", default=None, help="Root directory to scan (default: user home)")
    parser.add_argument("--depth", type=int, default=1, help="Scan depth (1=top-level, 2=one deeper)")
    parser.add_argument("--min-size-mb", type=float, default=10, help="Minimum size in MB to report (default: 10)")
    parser.add_argument("--json", action="store_true", help="Output raw JSON instead of summary")
    parser.add_argument("--output", help="Write JSON to file")
    args = parser.parse_args()

    entries = run_scan(scan_root=args.root, depth=args.depth, min_size_mb=args.min_size_mb)

    if args.json:
        output = json.dumps(entries, indent=2)
        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
            print(f"Wrote {len(entries)} entries to {args.output}", file=sys.stderr)
        else:
            print(output)
    else:
        print_summary(entries)
        if args.output:
            with open(args.output, "w") as f:
                json.dump(entries, f, indent=2)
            print(f"JSON also written to {args.output}")


if __name__ == "__main__":
    main()
