# Stage 3 - Backlink the vault with 10 parallel subagents

Run this **after** `export.py` (Stage 2) and `secret_scan.py` (Stage 2.5) have
finished. Paste the prompt below into Claude Code from inside the vault
directory. It spawns 10 subagents that each own a disjoint slice of projects,
then you run `consolidate.py` to build the hub pages.

## Why this design

- **Agents emit reports only.** They do **not** write to `topics/`, `tools/`
  or `entities/` directly. Ten agents writing to the same hub page is a race
  condition. Instead each agent writes one JSON report; `consolidate.py`
  builds every hub page in a single atomic pass.
- **Slices are balanced by session count**, not project count, so one agent
  does not get stuck with a 200-session project while another gets three
  tiny ones.

## Prompt to paste into Claude Code

> Backlink the Claude Code Command Center vault in the current directory.
>
> 1. List every `projects/<name>/sessions/*.md` file and count sessions per
>    project. Partition the projects into 10 slices balanced by total session
>    count (a project is never split across slices).
> 2. Spawn 10 subagents in parallel, one per slice. Each subagent, for every
>    session file in its slice:
>    - Reads the session markdown.
>    - Extracts 3-8 **topics** in kebab-case, the **tools/frameworks**
>      mentioned, and the **entities** (products, companies, people).
>    - Writes a one-sentence **summary**.
>    - Updates the session file's YAML frontmatter `topics:`, `tools:` and
>      `entities:` lists.
>    - Appends a `## Topics & Entities` section at the bottom of the session
>      file with `[[wikilinks]]` to each topic, tool and entity slug.
>    - Does **NOT** touch anything under `topics/`, `tools/` or `entities/`.
>    - Collects its results into `_build/reports/agent_N.json` (N = 1..10)
>      using the schema below.
> 3. After all 10 agents finish, report which agents succeeded or failed and
>    how many sessions each processed. Do not run consolidate.py yourself -
>    the user runs it after verifying the reports.

## Report schema (`_build/reports/agent_N.json`)

```json
{
  "agent": 1,
  "sessions": [
    {
      "session_file": "projects/vex/sessions/2026-05-01_abc12345.md",
      "project": "vex",
      "topics": ["electron-drm", "test-suite", "phase-4b"],
      "tools": ["castlabs-electron", "pytest"],
      "entities": ["castLabs", "Widevine"],
      "summary": "One sentence describing the session."
    }
  ]
}
```

## Final step (run yourself, after verifying the reports)

```sh
python consolidate.py --vault .
```

This reads all 10 reports and atomically writes `topics/<slug>.md`,
`tools/<slug>.md`, `entities/<slug>.md` and the `TOP-TOPICS.md` leaderboard.

## Cost note

Ten subagents means 10 concurrent Claude calls. On a Claude Max subscription
this is fine, but it burns the token allotment quickly. If a slice fails
because the daily limit was hit, re-run only that agent's slice later - the
reports are independent, so a partial re-run is safe.
