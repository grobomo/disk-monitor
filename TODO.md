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

- [ ] T007: Pilot — extract disk-cleanup from claude-config monorepo
  - Create grobomo/disk-monitor repo
  - Convert skills/disk-monitor to git submodule in claude-config
  - Document the pattern for migrating other skills
  - This proves the submodule approach before batch migration

### Phase 4: Monorepo cleanup
- [ ] T008: Batch-migrate remaining skills to individual repos
  - Script to: create repo, push skill contents, convert to submodule
  - Skip PII skills (weekly-update, dynamics-api, etc.) — those stay gitignored
  - Skip archived/template dirs
  - Update .gitmodules for each migrated skill

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
