# development-department

A 9-agent development team for [Claude Code](https://claude.com/claude-code), plus a `team-lead` that
runs them in a loop until the work is built, tested, reviewed and verified. It runs on its own and
stops only when it needs something from you.

| # | Agent | Model | Owns | Preloaded skills | Edits code? |
|---|-------|-------|------|------------------|-------------|
| 1 | `feature-planner` | Opus (high) | Request → approved plan | superpowers: brainstorming, writing-plans | Plan files only |
| 2 | `frontend-ux` | Opus (high) | Presentation layer | frontend-design, superpowers: verification | UI code |
| 3 | `security-reviewer` | Opus (xhigh) | Exploitable vulnerabilities | superpowers: verification, differential-review | No |
| 4 | `code-reviewer` | Opus (high) | Correctness of a diff | superpowers: requesting-code-review, verification | No |
| 5 | `auth-payments` | Opus (xhigh) | Identity, access, money | superpowers: TDD, verification, stripe-best-practices | Auth/payment code |
| 6 | `feature-builder` | Sonnet | Application logic, one step | **ponytail**, superpowers: TDD, verification | App code |
| 7 | `test-writer` | Sonnet | Coverage beyond the first test | superpowers: TDD, verification | Test files only |
| 8 | `codebase-scout` | Haiku | Where things are | superpowers: verification | No |
| 9 | `boilerplate-renamer` | Haiku | Zero-logic changes | superpowers: verification | Mechanical only |
| – | `team-lead` | Opus (high) | Runs the other nine | superpowers: dispatching-parallel-agents, verification | Never |

Each agent preloads only the skills its role always needs (preloaded skills cost context from the first
turn). Any agent can load other installed skills on demand.

## Install

Needs Claude Code, Python 3 and git. Linux and macOS.

```bash
git clone https://github.com/rayenekebiti/development-department.git
cd development-department
./install.sh
```

The installer, at user scope (works in every project):

1. Copies the 10 agents to `~/.claude/agents/` and the 5 hook scripts to `~/.claude/hooks/team/`.
2. Adds the hook entries to `~/.claude/settings.json`. It keeps your existing settings and skips entries
   that are already there.
3. Sets Ponytail's `defaultMode` to `off` (see [Plugins](#plugins)).
4. Adds 4 plugin marketplaces and installs 18 plugins, plus the `webapp-testing` skill.

Use `./install.sh --no-plugins` to skip step 4. Any file it replaces is first copied to
`~/.claude/backups/development-department-<time>/`. It is safe to run again.

Then:

- Restart Claude Code.
- Sign in to the Context7 and Stripe MCP servers with `/mcp` in a `claude` session. Use a Stripe
  **test-mode** account. Until then the agents fall back to web docs and skip the Stripe tools.
- Optional: install the free scanners `security-reviewer` uses when they are present: OSV-Scanner,
  Gitleaks, Trivy, Bandit, gosec, eslint-plugin-security.

### Optional: code graph (CodeGraph)

[CodeGraph](https://github.com/colbymchenry/codegraph) (MIT) indexes a project into a local graph of
symbols, calls and dependencies. With it, `codebase-scout`, `feature-planner`, `code-reviewer`,
`security-reviewer` and `boilerplate-renamer` ask "who calls X" or "how does X reach Y" in one query,
instead of grepping, and catch callbacks and interface implementations that grep misses. Without a
`.codegraph/` folder in the project, they search as before.

Install it with its anonymous usage statistics turned off before it ever runs:

```bash
curl -fsSL https://raw.githubusercontent.com/colbymchenry/codegraph/main/install.sh | DO_NOT_TRACK=1 sh
~/.local/bin/codegraph telemetry off
DO_NOT_TRACK=1 ~/.local/bin/codegraph install --target=claude --location=global --yes
```

The last command adds the CodeGraph MCP server to Claude Code, a short CodeGraph section to
`~/.claude/CLAUDE.md`, an allow rule for its tools, and a prompt hook that attaches graph context to
your own messages in indexed projects (subagents query the MCP tool themselves).
`codegraph uninstall` removes all of it. Then, in each project:

```bash
codegraph init --local-only    # builds .codegraph/ and keeps it out of git
```

Re-running `./install.sh` also switches CodeGraph telemetry off if CodeGraph is installed.

To use the team in one project only, copy `agents/` into `<project>/.claude/agents/`. A project copy
overrides the user-level one.

## Use it

**Let the lead run everything:**

```bash
claude --agent team-lead
```

Then describe the feature. To make it a project's default, put `{ "agent": "team-lead" }` in that
project's `.claude/settings.json`.

**Or call agents yourself** from any session, in plain words or by name:

```
Use feature-planner to plan X, then run the plan with the team.
@codebase-scout where is the session cookie set?
@feature-builder implement step 3 of docs/plans/2026-11-26-invoices.md
```

## The loop

```
plan ──> asks you: approve the plan? ──> build ─> check ─> tests ─> reviews ─> fixes ─┐
            (an inline question: it waits            ▲                                  │
             for your click, then goes on)           └──────── STATUS: IN PROGRESS ◄────┘
                                                               (hook sends it back, no reply needed)

pauses:  STATUS: NEEDS YOU  -> lists exactly what you must do. You reply, it continues.
         STATUS: BLOCKED    -> 3 failed fixes on one issue. You steer, it continues.
done:    STATUS: VERIFIED   -> Verification block: check output, review verdicts, weakened tests.
```

- **Decisions** (approve the plan, pick an option) come as an inline question. Answering doesn't end
  the run. At the plan checkpoint the lead shows the plan's goal, a Mermaid diagram of the flow the
  feature changes, and each step with its owner.
- **Things only you can do** (sign in with `/mcp`, add an env var, approve a commit or deploy) end the
  turn with `STATUS: NEEDS YOU`, one line per item. Do them, reply, and it picks up where it stopped.
- **How it keeps going:** `team_loop.py` is a Stop hook that reads the STATUS line at the end of each
  turn. On `IN PROGRESS` it sends the lead back to work. On anything else, or no STATUS line, it lets
  the turn end, so sessions that don't print STATUS lines are not affected.
- **Safety stops:** it pauses after 40 automatic continues in a row (set `TEAM_LOOP_MAX` under `"env"`
  in settings), or when the same next step comes up 4 times in a row. Your next message resets both.
- **`team-lead` never commits, pushes or deploys** without your explicit OK.

**Optional, `/goal`:** goal mode adds a second, independent check that won't let the run end until your
condition holds. It uses the same `STATUS: VERIFIED` line:

```
/goal Every step of <plan path> is implemented AND team-lead's final Verification block shows, from runs after the last code change, `<test command>` exit 0 AND code-reviewer's verdict on the final diff is approve or approve with nits AND security-reviewer reports no critical or high findings AND no test was deleted, skipped or weakened AND the block ends with STATUS: VERIFIED. If the block says STATUS: BLOCKED or NEEDS YOU, or after 40 turns, stop and report.
```

## Roles

Each role owns one thing. Anything outside it goes to the named teammate.

**1. `feature-planner`: request → approved plan**
- **Owns:** acceptance criteria; a Mermaid flow diagram of what changes; ordered steps (one commit each) with exact files, signatures, test command and owner.
- **Not its job:** writing code; visual design (`frontend-ux`); security sign-off (`security-reviewer`).
- **Call when:** a new feature, a change across 3+ files, or any design choice. Skip it for a clear 1–2 file fix.
- **Delivers:** `docs/plans/<date>-<feature>.md`, or questions if the request is ambiguous. The plan's
  **Flow** section is one diagram (`flowchart`, `sequenceDiagram`, `stateDiagram-v2` or `erDiagram`,
  at most ~15 nodes) using real function, route and table names, with new parts marked `NEW` and
  changed ones highlighted. In a project with `.codegraph/`, its edges come from the graph's call
  paths. GitHub and most editors render it; if `mmdc` (mermaid-cli) is installed, the planner checks
  that it renders.
- **Done when:** every path exists or is marked NEW, and every step has an owner and a test.

**2. `frontend-ux`: presentation layer**
- **Owns:** components, pages, layout, styling, design tokens, UI state, form messages, responsiveness, accessibility (WCAG 2.2 AA).
- **Not its job:** API or business logic (`feature-builder`); tokens, sessions, payment calls (`auth-payments`).
- **Call when:** a step changes what the user sees or touches.
- **Delivers:** UI code, plus screenshots at 375 / 768 / 1440 px.
- **Done when:** loading, empty and error states exist; everything works by keyboard; the console is clean.

**3. `security-reviewer`: exploitable vulnerabilities (read-only)**
- **Owns:** access control/IDOR, injection, XSS, auth and session flaws, payment tampering, SSRF, leaked secrets, headers, vulnerable dependencies.
- **Not its job:** style or general bugs (`code-reviewer`); applying fixes (it returns fix snippets to the code's owner).
- **Call when:** a change touches input, auth, payments, files, SQL, secrets or dependencies; before a release.
- **Delivers:** a verdict, then findings: severity, `file:line`, the attacker's request and result, the fix.
- **Done when:** every finding has a concrete exploit, and unchecked areas are listed.

**4. `code-reviewer`: correctness of a diff (read-only)**
- **Owns:** logic bugs, edge cases, plan and acceptance-criteria match, test quality, silent failures, needless complexity, convention breaks.
- **Not its job:** security analysis (it flags those to `security-reviewer`); editing.
- **Call when:** a step or feature passes its tests, before a commit or PR.
- **Delivers:** approve / approve with nits / changes required, plus each finding with its failing scenario.
- **Done when:** tests, types and lint have run, and every finding can be reproduced.

**5. `auth-payments`: identity, access, money**
- **Owns:** signup/login, sessions and cookies, OAuth/OIDC, MFA, password reset, role and permission checks, row-level security, API keys, Stripe checkout, subscriptions, webhooks, refunds.
- **Not its job:** how login or checkout pages look (`frontend-ux`); other business logic (`feature-builder`).
- **Call when:** a step touches who the user is, what they may access, or money.
- **Delivers:** code, plus abuse-case tests (another user's id, replayed webhook, tampered amount, expired token) and the env var names it needs.
- **Done when:** the abuse-case tests pass, in test mode only.

**6. `feature-builder`: application logic for one plan step**
- **Owns:** APIs, services, data models, migrations, jobs, CLI commands, integrations. The smallest complete change (ponytail), test first.
- **Not its job:** UI (`frontend-ux`); auth or payments (`auth-payments`); pure renames (`boilerplate-renamer`); design decisions (`feature-planner`).
- **Call when:** a plan step is assigned to it, or for a clear 1–2 file fix.
- **Delivers:** changed files, plus test commands and their results.
- **Done when:** its new test failed before the change and passes after, and the full suite, types and lint pass.

**7. `test-writer`: coverage beyond the builder's first test**
- **Owns:** edge cases, error paths, permission cases, regression tests for reported bugs, E2E tests for critical user journeys, property tests.
- **Not its job:** production code (it reports bugs with a failing test instead); the builder's own TDD test.
- **Call when:** a feature is built, a bug is reported, or a module is under-tested.
- **Delivers:** test files, run results, and bugs found.
- **Done when:** each test fails if its behaviour breaks; nothing is skipped or flaky.

**8. `codebase-scout`: where things are (read-only)**
- **Owns:** definitions, usages, call sites, the files of a feature, the existing pattern to copy, config, route and env keys.
- **Not its job:** opinions, design, review, edits.
- **Call when:** any "where / which file / how is X wired" question, and before planning.
- **Delivers:** a 1–3 sentence answer, a `file:line` list grouped by role, and what it didn't find.
- **Done when:** it has opened and confirmed every location it lists.

**9. `boilerplate-renamer`: zero-logic changes**
- **Owns:** renames of symbols, files, routes and keys in every case form; moves with import fixes; scaffolds copied from an existing example.
- **Not its job:** anything that needs a decision. New logic goes to `feature-builder`. Renaming a public API, DB column or URL needs your OK.
- **Call when:** the change is mechanical and its result is fully specified.
- **Delivers:** files changed, any remaining old-name references, check results.
- **Done when:** grep finds no stray old name, and build, types and tests pass.

### Without team-lead: routing in CLAUDE.md

Subagents don't talk to each other; the main session passes one agent's report to the next. To have a
normal session route work on its own, add this to a project's `CLAUDE.md` (or `~/.claude/CLAUDE.md`):

```markdown
## Agent team
- New feature or non-trivial change: `feature-planner` first, then follow its plan's owners.
- Code search ("where is X"): `codebase-scout`. Renames/moves/scaffolding: `boilerplate-renamer`.
- Plan steps: `feature-builder`; UI: `frontend-ux`; login/roles/payments: `auth-payments`.
- After building: `test-writer` for gaps, then `code-reviewer` and `security-reviewer` in parallel.
- Run independent agents in parallel. Pass each agent the plan path and the previous agent's report.
```

## Plugins

| Used by | Plugin | Marketplace |
|---------|--------|-------------|
| all | `superpowers` | `anthropics/claude-plugins-official` |
| frontend-ux | `frontend-design` | official |
| frontend-ux, test-writer | `playwright` (browser MCP), `webapp-testing` skill | official, `anthropics/skills` |
| feature-builder, code-reviewer | `ponytail` | `DietrichGebert/ponytail` |
| security-reviewer | `claude-security`, `security-guidance` | official |
| security-reviewer | `static-analysis`, `audit-context-building`, `differential-review`, `insecure-defaults`, `supply-chain-risk-auditor`, `variant-analysis` | `trailofbits/skills` |
| test-writer | `property-based-testing` | `trailofbits/skills` |
| code-reviewer | `pr-review-toolkit` | official |
| auth-payments | `stripe` | official |
| planner, builders | `context7` (docs MCP) | official |
| everyone | `guard-pack`, `protect-tests` (safety hooks) | `karanb192/claude-code-hooks` |
| scout, planner, reviewers, renamer | CodeGraph (code graph MCP, optional) | `colbymchenry/codegraph` |

**Ponytail is set to off by default.** Otherwise the plugin turns its mode on in every session and
every agent. `feature-builder` still gets it because it preloads the skill. Type `/ponytail` in a
session to turn it on there.

`security-reviewer` is told not to use Semgrep; it uses the free scanners above when installed and lists
missing ones under "not checked".

## Hooks

**From plugins:** `guard-pack` blocks dangerous commands (`rm -rf ~`, `curl | sh`), reads of `.env` and
keys, agent edits to Claude settings, hooks or agent files, and any commit, push or `gh pr merge` on
`main`. So agents work on a branch and open a pull request, and **you** merge it. `protect-tests`
blocks deleting tests or adding skip markers instead of fixing code. `security-guidance` warns about
risky patterns on edits.

**Custom** (`hooks/`, Python 3 stdlib, no network, no AI calls):

| Hook | Event | Applies to | What it does |
|------|-------|-----------|--------------|
| `readonly_guard.py` | PreToolUse Bash, in the agent file | security-reviewer, code-reviewer, codebase-scout | Denies shell commands that write: file redirects, `sed -i`, `rm`/`mv`/`cp`, git writes, package installs, `--fix`/`--write`. Tests, linters and builds still run |
| `evidence_gate.py` | SubagentStop | feature-builder, test-writer, auth-payments, boilerplate-renamer, frontend-ux | If the final report shows no test, check or browser results, sends the agent back once to run them. Lets it stop if it says why it couldn't |
| `live_key_guard.py` | PreToolUse | every session | Blocks any tool call containing a Stripe live secret (`sk_live_`, `rk_live_`). Test keys and `pk_live_` pass |
| `format_if_configured.py` | PostToolUse Edit/Write | every session | Formats the edited file only with what the project already has: its own `node_modules/.bin/prettier`, ruff if configured, `gofmt`, `rustfmt`. Never downloads anything |
| `team_loop.py` | Stop + UserPromptSubmit | sessions that print STATUS lines | The auto-continue loop described above |

`settings/settings-snippet.json` has the settings entries, if you'd rather add them by hand.

## Uninstall

1. Delete the 10 agent files from `~/.claude/agents/` and the folder `~/.claude/hooks/team/`.
2. Remove the hook entries that point to `.claude/hooks/team/` from `~/.claude/settings.json`.
3. Optionally remove plugins with `claude plugin uninstall <name@marketplace>`.

## Caveats

- Preloaded `skills:` may not load when agents run as experimental agent-team teammates. They still
  load skills on demand through the Skill tool.
- `playwright` and `context7` run external MCP servers. Read third-party skill packs before installing them.
- The read-only guard stops accidental writes, not a determined bypass.

## License

MIT. See [LICENSE](LICENSE).

## Self-improvement (GEPA)

`improve/gepa_agent.py` tunes one agent's prompt with [GEPA](https://github.com/gepa-ai/gepa), scored on sample questions with known `file:line` answers (`improve/tasks/<agent>.json`, run against `improve/fixtures/`). The design follows hermes-agent-self-evolution: questions with known answers → GEPA → checks on each rewrite (size limit, kept headings, every sentence containing "never" kept word for word) → a pull request you review. A question's score is the F1 of the `file:line` citations in the answer, so both missed answers and wrong citations lower it. Model calls go through the `claude` CLI. The agent being tested only gets Read, Grep and Glob. Nothing is installed: each run writes `report.json`, `proposal.diff` and, if the prompt scored better, the new agent file to `improve/runs/<agent>-<time>/`.

```bash
python3 -m venv .venv && .venv/bin/pip install gepa
.venv/bin/python improve/gepa_agent.py codebase-scout --budget 18
# tests for the scorer and the checks (no model calls)
python3 -m unittest discover -s improve
# self-test: start from a deliberately weak prompt
.venv/bin/python improve/gepa_agent.py codebase-scout --budget 30 --seed-file improve/tasks/selftest-weak-scout.md
```
