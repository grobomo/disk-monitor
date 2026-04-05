"""
Batch-migrate skills from ~/.claude/skills/ to individual grobomo repos.
Dry-run by default. Use --execute to actually create repos and push.

Skips:
- Skills that already have .git/
- PII skills (weekly-update, dynamics-api, etc.)
- Non-skill dirs (archive, templates, disk-cleanup)
- Skills that already exist as grobomo repos
"""

import json
import subprocess
import sys
import os
from pathlib import Path

SKILLS_DIR = Path(os.environ.get("USERPROFILE") or os.path.expanduser("~")) / ".claude" / "skills"

# Skills that contain PII or internal data -- must NOT be published
PII_SKILLS = {
    "weekly-update", "weekly-data", "dynamics-api", "email-checker",
    "jumpbox", "rdp", "v1-api", "v1-oat-report", "v1-policy", "v1-report",
    "apex-central-api", "trend-docs", "smtp-relay", "network-scan",
    "rone-chat", "wiki-api", "pm-report",
}

# Non-skill directories to skip
SKIP_DIRS = {
    "archive", "templates", "disk-cleanup", "skill-marketplace",
}

# Map skill names to existing grobomo repo names (if different)
EXISTING_REPO_MAP = {
    "hook-runner": "hook-runner",
    "mcp-manager": "mcp-manager",
    "chat-export": "claude-code-chat-export",
    "claude-report": "claude-report",
    "terraform-skill": None,  # has .git but check remote
}


def get_existing_grobomo_repos():
    """Get list of existing grobomo repo names."""
    result = subprocess.run(
        ["gh", "repo", "list", "grobomo", "--limit", "200", "--json", "name", "-q", ".[].name"],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"Failed to list grobomo repos: {result.stderr}", file=sys.stderr)
        return set()
    return set(result.stdout.strip().splitlines())


def get_skill_dirs():
    """Get all skill directories."""
    dirs = []
    for entry in sorted(SKILLS_DIR.iterdir()):
        if entry.is_dir() and not entry.name.startswith("."):
            dirs.append(entry)
    return dirs


def classify_skill(skill_dir, existing_repos):
    """Classify a skill for migration. Returns (action, reason)."""
    name = skill_dir.name

    if name in SKIP_DIRS:
        return "SKIP", "non-skill directory"

    if name in PII_SKILLS:
        return "SKIP_PII", "contains PII/internal data"

    if (skill_dir / ".git").is_dir():
        return "ALREADY_GIT", "already has .git/"

    # Check if repo already exists on grobomo
    repo_name = EXISTING_REPO_MAP.get(name, name)
    if repo_name and repo_name in existing_repos:
        return "REPO_EXISTS", f"grobomo/{repo_name} already exists"

    # Check if it has a SKILL.md (valid skill)
    if not (skill_dir / "SKILL.md").exists():
        return "NO_SKILL_MD", "no SKILL.md found"

    return "MIGRATE", "ready for migration"


def migrate_skill(skill_dir, execute=False):
    """Migrate a single skill to a grobomo repo."""
    name = skill_dir.name
    repo_name = name

    if not execute:
        print(f"  [DRY RUN] Would create grobomo/{repo_name} from {skill_dir}")
        return True

    # Read SKILL.md for description
    desc = f"Claude Code skill: {name}"
    skill_md = skill_dir / "SKILL.md"
    if skill_md.exists():
        try:
            content = skill_md.read_text(encoding="utf-8", errors="replace")
            for line in content.splitlines():
                if line.startswith("description:"):
                    desc = line.split(":", 1)[1].strip()
                    break
        except Exception:
            pass  # Keep default desc

    # Create .github/publish.json
    github_dir = skill_dir / ".github"
    github_dir.mkdir(exist_ok=True)
    publish_json = github_dir / "publish.json"
    publish_json.write_text(json.dumps({
        "github_account": "grobomo",
        "visibility": "public",
        "reason": f"Generic Claude Code skill, no internal/customer data"
    }, indent=2) + "\n")

    # Create .gitignore if missing
    gitignore = skill_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("__pycache__/\n*.pyc\narchive/\nnode_modules/\nbuild/\ndist/\n")

    # Copy secret-scan.yml from disk-monitor template
    workflows_dir = github_dir / "workflows"
    workflows_dir.mkdir(exist_ok=True)
    scan_template = SKILLS_DIR / "disk-monitor" / ".github" / "workflows" / "secret-scan.yml"
    scan_dest = workflows_dir / "secret-scan.yml"
    if scan_template.exists() and not scan_dest.exists():
        import shutil
        shutil.copy2(str(scan_template), str(scan_dest))

    # Init git
    subprocess.run(["git", "init"], cwd=str(skill_dir), capture_output=True)
    subprocess.run(["git", "config", "user.name", "grobomo"], cwd=str(skill_dir), capture_output=True)
    subprocess.run(["git", "config", "user.email", "grobomo@users.noreply.github.com"], cwd=str(skill_dir), capture_output=True)
    subprocess.run(["git", "config", "credential.helper", "!gh auth git-credential"], cwd=str(skill_dir), capture_output=True)

    # Add all files
    subprocess.run(["git", "add", "-A"], cwd=str(skill_dir), capture_output=True)
    result = subprocess.run(
        ["git", "commit", "-m", f"Initial commit: {name} skill"],
        cwd=str(skill_dir), capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"  FAILED: git commit failed for {name}: {result.stderr}")
        return False

    # Create GitHub repo
    result = subprocess.run(
        ["gh", "repo", "create", f"grobomo/{repo_name}",
         "--public", "--description", desc,
         "--source", str(skill_dir), "--push"],
        capture_output=True, text=True, timeout=30
    )
    if result.returncode != 0:
        print(f"  FAILED: gh repo create failed for {name}: {result.stderr}")
        return False

    print(f"  MIGRATED: grobomo/{repo_name}")
    return True


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Batch-migrate skills to grobomo repos")
    parser.add_argument("--execute", action="store_true", help="Actually create repos (default: dry run)")
    parser.add_argument("--only", help="Migrate only this specific skill")
    args = parser.parse_args()

    # Must be on grobomo account for repo creation
    if args.execute:
        result = subprocess.run(["gh", "auth", "switch", "--user", "grobomo"], capture_output=True, text=True)
        if result.returncode != 0:
            print("Failed to switch to grobomo account", file=sys.stderr)
            sys.exit(1)

    existing_repos = get_existing_grobomo_repos()
    skill_dirs = get_skill_dirs()

    if args.only:
        skill_dirs = [d for d in skill_dirs if d.name == args.only]

    # Classify all skills
    plan = []
    for d in skill_dirs:
        action, reason = classify_skill(d, existing_repos)
        plan.append((d, action, reason))

    # Print plan
    print(f"\n{'='*60}")
    print(f"Skill Migration Plan -- {len(skill_dirs)} skills")
    print(f"{'='*60}\n")

    migrate_count = 0
    for d, action, reason in plan:
        icon = {
            "MIGRATE": ">>",
            "SKIP": "--",
            "SKIP_PII": "XX",
            "ALREADY_GIT": "OK",
            "REPO_EXISTS": "OK",
            "NO_SKILL_MD": "--",
        }.get(action, "??")
        print(f"  {icon} {d.name:<30} {action:<15} {reason}")
        if action == "MIGRATE":
            migrate_count += 1

    print(f"\n  {migrate_count} skills ready for migration\n")

    if migrate_count == 0:
        print("Nothing to migrate.")
        return

    if not args.execute:
        print("  DRY RUN -- add --execute to actually migrate\n")
        return

    # Execute migrations
    print(f"\n{'='*60}")
    print("Executing migrations...")
    print(f"{'='*60}\n")

    success = 0
    for d, action, reason in plan:
        if action != "MIGRATE":
            continue
        if migrate_skill(d, execute=True):
            success += 1

    print(f"\n  Migrated {success}/{migrate_count} skills\n")

    # Switch back to default account
    subprocess.run(["gh", "auth", "switch", "--user", "joel-ginsberg_tmemu"], capture_output=True)
    print("  Switched back to joel-ginsberg_tmemu")


if __name__ == "__main__":
    main()
