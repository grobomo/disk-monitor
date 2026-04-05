---

name: disk-monitor
description: Monitor disk usage, verify git tracking hygiene, categorize files for safe cleanup. Advisory by default — never deletes without explicit approval.
keywords:
  - disk
  - cleanup
  - storage
  - space
  - git
  - untracked
  - orphan
  - stale
  - cache
  - temp
  - large files
  - disk full
  - free space
  - disk usage
  - du
  - df
  - git status
  - git hygiene
  - monorepo
  - submodule
  - repo sprawl

---

# Disk Monitor Skill

Two jobs, one skill: **disk space management** and **git tracking hygiene**.

## When to trigger

- User mentions disk space, storage, cleanup, or free space
- Disk-space-guard hook fires a low-space alert
- User asks about untracked files, git sprawl, orphan repos, or repo organization
- User wants to know what's safe to delete

## Capabilities

### 1. Disk Scanner (`scan.py`)
- Scans user profile directory recursively
- Outputs JSON: path, size, last_modified, file_count, category
- Categories: AUTO-SAFE, REVIEW, NEVER-TOUCH

### 2. Git Hygiene Checker (`git-hygiene.py`)
- Finds directories with `.git/` that aren't tracked by a parent repo
- Detects large untracked files in repos
- Identifies skills/projects that should be submodules but aren't
- Reports repos with uncommitted changes, stale branches

### 3. Cleanup Executor (`clean.py`)
- Dry-run by default (`--execute` to actually delete)
- Takes `--approved` flag with specific item keys
- Logs every action to `cleanup-log.json`

### 4. Email Report (`report.py`)
- Sends categorized report via email-manager skill
- User reviews on mobile, replies with approval
- No deletions without email approval

## Hard Rules

1. **NO AUTO-DELETE** — even AUTO-SAFE requires explicit user permission (algorithm not yet trusted)
2. **NEVER-TOUCH**: user docs, project repos, credentials, enterprise software, VHDs, databases, WSL distros
3. **Dry-run default** — `--execute` flag required for any destructive action
4. **Log everything** — every scan and deletion logged to `cleanup-log.json`
5. **Email before delete** — user must review report before any cleanup executes

## Known-Safe Patterns (`patterns.json`)

Extensible database mapping path patterns to safety categories:
- Pattern: glob, min_age_days, regeneration_command
- User adds custom patterns over time
- Categories inherit from disk-space-safety.md rules

## Permission Model

| Category | Current Permission | Future Permission |
|----------|-------------------|-------------------|
| AUTO-SAFE | Suggest only | Auto-delete (when trusted) |
| REVIEW | Email + approval | Email + approval |
| NEVER-TOUCH | Manual only | Manual only |

Permission upgrades only happen with explicit user statement.
