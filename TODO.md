# Disk Monitor — TODO

## Context
Combined skill for disk space management and git tracking hygiene.
Knows what's on disk, what's tracked in git, what's safe to delete, and what needs attention.
Never deletes without explicit approval. Advisory by default.

## Tasks

### Phase 1: Foundation
- [x] T001: Create patterns.json — known-safe patterns database
  - 30 patterns seeded from disk-space-safety.md rules
  - Glob-to-regex matching with ** support

- [x] T002: Create scan.py — PowerShell-based directory size scanner
  - Tested: 55 dirs from skills/, categories working
  - Uses temp .ps1 file for reliable PowerShell execution

- [x] T003: Create git-hygiene.py — git tracking analyzer
  - Tested: found 44 repos, 31 with issues (NO_REMOTE, UNCOMMITTED, STALE, etc.)
  - PowerShell-based .git directory finder with skip list

### Phase 2: Actions
- [x] T004: Create clean.py — execute user-approved deletions
  - Dry-run default, --execute flag, NEVER-TOUCH always blocked
  - Logs to cleanup-log.json

- [x] T005: Create report.py — email formatted report via email-manager
  - Combines scan + git data, categorized output
  - --email flag sends via email-manager, otherwise prints to stdout

### Phase 3: Integration
- [x] T006: Integrate with disk-space-guard hooks
  - Updated both hooks to reference disk-monitor scan.py
  - Alert messages now guide Claude to run the scan before suggesting deletions

- [x] T007: Pilot — extract disk-monitor to standalone repo
  - Created grobomo/disk-monitor (public)
  - Git init + push from ~/.claude/skills/disk-monitor/
  - Submodule conversion deferred to T008 (needs claude-config monorepo changes)

### Phase 4: Monorepo cleanup
- [x] T008: Batch-migrate remaining skills to individual repos
  - migrate-skills.py: classifies, creates repos, pushes with secret-scan CI
  - 28 skills migrated to grobomo/ (public)
  - 16 PII skills skipped (weekly-update, dynamics-api, v1-*, etc.)
  - 4 non-skill dirs skipped (archive, templates, disk-cleanup, skill-marketplace)
  - Each repo gets .github/publish.json, .gitignore, secret-scan.yml

### Phase 5: Polish and real-world use
- [x] T009: Add --top N flag to scan.py for quick "what's eating my disk" answers
- [x] T010: Run full home scan, save to last-scan.json, generate first real email report
  - Fixed PS script perf: streaming ForEach-Object instead of Sort-Object (was timing out)
  - Fixed .NET EnumerateFiles approach (swallowed all errors, reported 0 bytes)
  - 10 entries, 902 GB total across user home
  - Added 9 new patterns for top-level dirs (Downloads, OneDrive, VirtualBox, etc.)
  - Fixed report.py to use msgraph-lib/Graph API for email instead of nonexistent send.py
  - First real report emailed successfully
- [x] T011: Schedule periodic scan via claude-scheduler (weekly)
  - Created run-weekly.py orchestrator (scan + git-hygiene + report + email)
  - Registered as "disk-monitor" task (weekly interval)
- [x] T012: Add patterns for common Windows bloat (Windows.old, WinSxS backup, Installer cache)
  - Added 9 new patterns: Windows.old, WinSxS, Installer, Update cache, crash dumps, NuGet, Chrome/Edge cache, thumbnails

## Session handoff (2026-04-05)
- All 8 original tasks COMPLETE
- 28 skills migrated to grobomo/ public repos with secret-scan CI
- 16 PII skills remain local-only (correct behavior)
- scan.py and git-hygiene.py both tested and working
- Hooks updated to reference disk-monitor scan on disk alerts
- Next: T009-T012 for production polish

## Permission model (CURRENT: no auto-delete)
- Even AUTO-SAFE files require explicit permission — algorithm not yet trusted
- REVIEW and NEVER-TOUCH always require email approval
- Permission upgrades only with explicit user statement

## Design decisions
- PowerShell for disk scanning (native Windows, no extra deps)
- Python for logic (consistent with other skills)
- Git hygiene uses subprocess calls to git CLI
- Patterns database is JSON, not code — user-editable
- Docker Desktop removed — builds use EC2 spot instances
- LANDESK/Shavlik PatchData (101 GB) = NEVER-TOUCH
