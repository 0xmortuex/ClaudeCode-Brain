# Claude Code Command Center - toolkit

Turns your local Claude Code session history into a searchable, backlinked
Obsidian vault. Based on *Claude Code Command Center* by Alex Freedman.

This repository holds the **tooling**, not the vault. Claude Code stores its
session transcripts as JSONL files under `~/.claude/projects/` on the machine
you run it on. That data never leaves your machine - you run these scripts
locally and the generated `vault/` is `.gitignore`d.

> **Why a toolkit and not a finished vault?** This repo was built in a cloud
> (web) Claude Code session, which runs in an ephemeral container with no
> access to your local `~/.claude/projects/`. The scripts are cross-platform
> (`Path.home()` resolves the right location on Windows/macOS/Linux), so you
> clone this repo on your own machine and run the stages there.

## Requirements

- Python 3.9+ (no third-party packages)
- Claude Code installed locally, with existing session history
- Claude Code CLI for the Stage 3 backlink run

## Stages

Run them in order; each is verifiable before the next.

### Stage 1 - Discovery

Report how much history you have before exporting anything.

```sh
python export.py --discover
```

Reports JSONL file count, project folders, total size, oldest/newest file.
If the corpus exceeds 5 GB it prints a warning - review before Stage 3.

### Stage 2 - Export to a markdown vault

```sh
python export.py --out vault
```

Walks `~/.claude/projects/`, parses every `.jsonl`, and writes one markdown
file per session. Sessions are grouped by their `cwd` field so worktrees of
the same project collapse together. Tool results are capped at 4000 chars and
tool calls are wrapped in collapsible `<details>` blocks. Produces:

```
vault/
├── README.md            project index
├── TOP-TOPICS.md         placeholder until Stage 3
├── projects/<name>/
│   ├── _project.md       rollup with a sortable session table
│   ├── sessions/YYYY-MM-DD_*.md
│   └── subagents/*.md    linked back to their parent session
├── topics/   tools/   entities/   (empty until Stage 3)
└── _build/reports/       (filled by Stage 3 agents)
```

### Stage 2.5 - Secret scan (do not skip)

```sh
python secret_scan.py --vault vault
```

Scans every markdown file for API keys, tokens, JWTs and PEM private keys,
replaces each with `<REDACTED:type>`, and writes `SECRETS-REDACTED.md` with
per-file counts (never the secrets themselves). Use `--dry-run` to preview.
Stop and review if it finds more than 50 matches.

### Stage 3 - Backlink with 10 parallel subagents

See [`STAGE3_BACKLINK.md`](STAGE3_BACKLINK.md) for the prompt to paste into
Claude Code. The agents extract topics, tools and entities per session and
emit JSON reports; they never write hub pages directly. Then:

```sh
python consolidate.py --vault vault
```

reads the 10 reports and atomically generates the `topics/`, `tools/` and
`entities/` hub pages plus the `TOP-TOPICS.md` leaderboard.

### Stage 4 - Install the skill (only after you have verified the vault)

Not done automatically - you decide when Claude should auto-consult the vault.
When ready, create `~/.claude/skills/claude-code-brain/SKILL.md` pointing at
your vault path. A starting template:

```markdown
---
name: claude-code-brain
description: >
  Searchable archive of past Claude Code sessions. Use when the user refers
  to earlier work, asks "how did we do X before", or starts a project that
  has prior history in the vault.
---

# Claude Code Brain

The vault at `<your vault path>` indexes every past Claude Code session.

- `README.md` lists all projects.
- `TOP-TOPICS.md` ranks topics by frequency.
- `projects/<name>/_project.md` summarizes a project's sessions.
- `topics/`, `tools/`, `entities/` are hub pages linking related sessions.

When starting work on a known project, read its `_project.md` first to
recover prior context instead of asking the user to re-explain it.
```

## Safety

- `vault/` and `_build/` are git-ignored - your history is never committed.
- Always run Stage 2.5 before sharing or syncing the vault anywhere.
