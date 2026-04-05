"""
Cleanup executor for disk-monitor skill.
Dry-run by default. Only deletes with --execute flag AND --approved items.
Logs every action to cleanup-log.json.
"""

import json
import shutil
import sys
import os
from datetime import datetime, timezone
from pathlib import Path

SKILL_DIR = Path(__file__).parent
LOG_FILE = SKILL_DIR / "cleanup-log.json"


def load_log():
    """Load existing cleanup log or return empty list."""
    if LOG_FILE.exists():
        with open(LOG_FILE, "r") as f:
            return json.load(f)
    return []


def save_log(entries):
    """Save cleanup log."""
    with open(LOG_FILE, "w") as f:
        json.dump(entries, f, indent=2)


def delete_path(path, dry_run=True):
    """Delete a file or directory. Returns (success, size_freed, error)."""
    path = Path(path)
    if not path.exists():
        return False, 0, "Path does not exist"

    # Calculate size before deletion
    size = 0
    try:
        if path.is_file():
            size = path.stat().st_size
        elif path.is_dir():
            for f in path.rglob("*"):
                if f.is_file():
                    try:
                        size += f.stat().st_size
                    except OSError:
                        pass
    except OSError:
        pass

    if dry_run:
        return True, size, "DRY_RUN"

    try:
        if path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path, ignore_errors=True)
        return True, size, None
    except Exception as e:
        return False, 0, str(e)


def run_cleanup(scan_file, approved_ids, execute=False):
    """
    Run cleanup on approved items from a scan output file.
    Returns list of action records.
    """
    with open(scan_file, "r") as f:
        entries = json.load(f)

    # Filter to approved items only
    targets = []
    for entry in entries:
        entry_id = entry.get("pattern_id", "unknown")
        entry_path = entry.get("path", "")
        # Match by pattern_id or by path
        if entry_id in approved_ids or entry_path in approved_ids:
            targets.append(entry)

    if not targets:
        print("No matching items found for the approved IDs.")
        return []

    actions = []
    log = load_log()
    timestamp = datetime.now(timezone.utc).isoformat()

    for entry in targets:
        path = entry["path"]
        category = entry.get("category", "UNKNOWN")

        # Safety check: NEVER-TOUCH items cannot be cleaned even if approved
        if category == "NEVER-TOUCH":
            print(f"  BLOCKED: {path} is NEVER-TOUCH — skipping even though approved")
            actions.append({
                "timestamp": timestamp,
                "path": path,
                "action": "BLOCKED",
                "reason": "NEVER-TOUCH category",
                "dry_run": not execute,
                "size_bytes": entry.get("size_bytes", 0),
            })
            continue

        success, size, error = delete_path(path, dry_run=not execute)
        status = "DRY_RUN" if not execute else ("DELETED" if success else "FAILED")

        action = {
            "timestamp": timestamp,
            "path": path,
            "category": category,
            "pattern_id": entry.get("pattern_id", "unknown"),
            "action": status,
            "size_bytes": size,
            "size_mb": round(size / (1024 * 1024), 1),
            "error": error,
            "dry_run": not execute,
        }
        actions.append(action)
        log.append(action)

        icon = "🗑️" if status == "DELETED" else "👁️" if status == "DRY_RUN" else "❌"
        size_str = f"{action['size_mb']:.1f} MB"
        print(f"  {icon} {status}: {path} ({size_str})")

    save_log(log)
    return actions


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Execute approved cleanup actions")
    parser.add_argument("--scan-file", required=True, help="Path to scan.py JSON output")
    parser.add_argument("--approved", required=True, help="Comma-separated pattern_ids or paths to clean")
    parser.add_argument("--execute", action="store_true", help="Actually delete (default: dry run)")
    parser.add_argument("--json", action="store_true", help="Output JSON results")
    args = parser.parse_args()

    approved_ids = set(a.strip() for a in args.approved.split(","))

    if not args.execute:
        print("\n  DRY RUN — no files will be deleted. Add --execute to actually clean.\n")

    actions = run_cleanup(args.scan_file, approved_ids, execute=args.execute)

    total_size = sum(a.get("size_bytes", 0) for a in actions)
    total_mb = round(total_size / (1024 * 1024), 1)
    total_gb = round(total_mb / 1024, 2)

    verb = "Would free" if not args.execute else "Freed"
    print(f"\n  {verb}: {total_gb} GB ({total_mb} MB) across {len(actions)} items")

    if args.json:
        print(json.dumps(actions, indent=2))


if __name__ == "__main__":
    main()
