"""
Git hygiene analyzer for disk-monitor skill.
Finds all .git/ directories under user profile.
Reports: uncommitted changes, stale branches, untracked large files, orphan repos.
Output: JSON to stdout.
"""

import json
import subprocess
import sys
import os
from pathlib import Path
from datetime import datetime, timezone

USER_HOME = Path(os.environ.get("USERPROFILE") or os.path.expanduser("~"))

# Directories to skip during .git search (performance)
SKIP_DIRS = {
    "node_modules", ".cache", "AppData", "ProgramData",
    "__pycache__", ".pytest_cache", "venv", ".venv",
    "site-packages", ".git", "archive"
}

# PowerShell script to find .git directories fast
PS_FIND_GIT = r"""
$ErrorActionPreference = 'SilentlyContinue'
$root = $args[0]
$maxDepth = [int]$args[1]

function Find-GitDirs {
    param([string]$Path, [int]$Depth)
    if ($Depth -gt $maxDepth) { return }

    $gitPath = Join-Path $Path ".git"
    if (Test-Path $gitPath) {
        $Path
        return  # Don't recurse into git repos looking for nested repos
    }

    $skipNames = @('node_modules', '.cache', 'AppData', 'ProgramData', '__pycache__', '.pytest_cache', 'venv', '.venv', 'site-packages', 'archive')

    Get-ChildItem -Path $Path -Directory -Force -ErrorAction SilentlyContinue | Where-Object {
        $skipNames -notcontains $_.Name
    } | ForEach-Object {
        Find-GitDirs $_.FullName ($Depth + 1)
    }
}

Find-GitDirs $root 0
"""


def find_git_repos(root=None, max_depth=5):
    """Find all directories containing .git/ under root."""
    import tempfile
    scan_root = root or str(USER_HOME)

    ps_file = tempfile.NamedTemporaryFile(mode="w", suffix=".ps1", delete=False)
    try:
        ps_file.write(PS_FIND_GIT)
        ps_file.close()
        cmd = [
            "powershell.exe", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass",
            "-File", ps_file.name, scan_root, str(max_depth)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    finally:
        os.unlink(ps_file.name)

    repos = []
    for line in result.stdout.strip().splitlines():
        line = line.strip()
        if line and os.path.isdir(os.path.join(line, ".git")):
            repos.append(line)
    return repos


def git_cmd(repo_path, *args):
    """Run a git command in a repo and return stdout."""
    cmd = ["git", "-C", repo_path] + list(args)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def analyze_repo(repo_path):
    """Analyze a single git repo and return a dict of findings."""
    info = {
        "path": repo_path,
        "name": os.path.basename(repo_path),
        "issues": [],
        "branch": "",
        "remote": "",
        "uncommitted_files": 0,
        "untracked_files": 0,
        "stale_branches": [],
        "large_untracked": [],
        "last_commit_date": None,
        "total_branches": 0,
    }

    # Current branch
    info["branch"] = git_cmd(repo_path, "branch", "--show-current") or "(detached)"

    # Remote URL
    info["remote"] = git_cmd(repo_path, "remote", "get-url", "origin")
    if not info["remote"]:
        info["issues"].append("NO_REMOTE")

    # Status (porcelain for parsing)
    status = git_cmd(repo_path, "status", "--porcelain")
    if status:
        lines = status.splitlines()
        info["uncommitted_files"] = len([l for l in lines if not l.startswith("??")])
        info["untracked_files"] = len([l for l in lines if l.startswith("??")])
        if info["uncommitted_files"] > 0:
            info["issues"].append("UNCOMMITTED_CHANGES")
        if info["untracked_files"] > 5:
            info["issues"].append("MANY_UNTRACKED")

    # Last commit date
    last_date = git_cmd(repo_path, "log", "-1", "--format=%aI")
    if last_date:
        info["last_commit_date"] = last_date
        try:
            dt = datetime.fromisoformat(last_date)
            age_days = (datetime.now(timezone.utc) - dt).days
            if age_days > 90:
                info["issues"].append(f"STALE_{age_days}d")
        except ValueError:
            pass

    # Branches
    branches_raw = git_cmd(repo_path, "branch", "--list")
    if branches_raw:
        branches = [b.strip().lstrip("* ") for b in branches_raw.splitlines()]
        info["total_branches"] = len(branches)

        # Check for stale branches (merged into current)
        merged = git_cmd(repo_path, "branch", "--merged")
        if merged:
            merged_branches = [b.strip().lstrip("* ") for b in merged.splitlines()]
            current = info["branch"]
            info["stale_branches"] = [b for b in merged_branches if b and b != current and b not in ("main", "master")]
            if info["stale_branches"]:
                info["issues"].append("STALE_BRANCHES")

    # Large untracked files (>1MB)
    if status:
        for line in status.splitlines():
            if line.startswith("??"):
                filepath = line[3:].strip()
                full = os.path.join(repo_path, filepath)
                if os.path.isfile(full):
                    try:
                        size = os.path.getsize(full)
                        if size > 1_000_000:
                            info["large_untracked"].append({
                                "path": filepath,
                                "size_mb": round(size / 1_000_000, 1)
                            })
                    except OSError:
                        pass
        if info["large_untracked"]:
            info["issues"].append("LARGE_UNTRACKED")

    return info


def print_summary(repos):
    """Print human-readable summary."""
    print(f"\n{'='*70}")
    print(f"Git Hygiene Report -- {len(repos)} repositories")
    print(f"{'='*70}")

    issues_repos = [r for r in repos if r["issues"]]
    clean_repos = [r for r in repos if not r["issues"]]

    if issues_repos:
        print(f"\n  Repos with issues: {len(issues_repos)}")
        print(f"{'-'*70}")
        for r in issues_repos:
            path = r["path"].replace(str(USER_HOME), "~")
            issues = ", ".join(r["issues"])
            print(f"  {path}")
            print(f"    Branch: {r['branch']}  |  Issues: {issues}")
            if r["stale_branches"]:
                print(f"    Stale branches: {', '.join(r['stale_branches'][:5])}")
            if r["large_untracked"]:
                for f in r["large_untracked"][:3]:
                    print(f"    Large untracked: {f['path']} ({f['size_mb']} MB)")
            print()

    if clean_repos:
        print(f"\n  Clean repos: {len(clean_repos)}")
        print(f"{'-'*70}")
        for r in clean_repos:
            path = r["path"].replace(str(USER_HOME), "~")
            print(f"  {path} ({r['branch']})")

    print(f"{'-'*70}\n")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Analyze git repository hygiene")
    parser.add_argument("--root", default=None, help="Root directory to search (default: user home)")
    parser.add_argument("--max-depth", type=int, default=5, help="Max search depth for .git dirs")
    parser.add_argument("--json", action="store_true", help="Output raw JSON")
    parser.add_argument("--output", help="Write JSON to file")
    args = parser.parse_args()

    print("Finding git repositories...", file=sys.stderr)
    repo_paths = find_git_repos(root=args.root, max_depth=args.max_depth)
    print(f"Found {len(repo_paths)} repos. Analyzing...", file=sys.stderr)

    repos = []
    for path in repo_paths:
        repos.append(analyze_repo(path))

    # Sort: repos with issues first, then by path
    repos.sort(key=lambda r: (0 if r["issues"] else 1, r["path"]))

    if args.json:
        output = json.dumps(repos, indent=2)
        if args.output:
            with open(args.output, "w") as f:
                f.write(output)
            print(f"Wrote {len(repos)} repos to {args.output}", file=sys.stderr)
        else:
            print(output)
    else:
        print_summary(repos)
        if args.output:
            with open(args.output, "w") as f:
                json.dump(repos, f, indent=2)
            print(f"JSON also written to {args.output}")


if __name__ == "__main__":
    main()
