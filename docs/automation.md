# Research automation

Research Agent Workspace is a Python, file-based research workflow harness. It
is not an LLM implementation or a LangChain/AutoGen application. Codex or Claude
Code supplies reasoning and tool use; this repository supplies role instructions,
durable state, dependency-aware dispatch, experiment bookkeeping, evidence checks,
and report workflows. The core uses Python's standard library.

## Install from a checkout

Install Python 3.10+, Git, and either authenticated Codex CLI or Claude Code.
Keep this checkout: templates, prompts and workflows are runtime inputs. A plain
wheel installation without these assets is not supported.

From the repository root, on Windows, macOS or Linux:

```sh
python -m scripts.commands.release.automation_setup --dry-run
python -m scripts.commands.release.automation_setup --provider codex
```

Use `--provider claude` for a new Claude-first setup. Setup preserves an existing
default provider, custom runner commands, settings and hooks. It writes only
repository-local settings; it does not change your global agent configuration.
Restart your agent session to discover newly installed skills and hooks.

Setup connects:

- Both official CLIs to bounded prompt-file runner adapters in the ignored local
  workspace profile. Prompts are sent through stdin, including on Windows.
- The 13 canonical `.claude/skills` entrypoints to Codex's repository-local
  `.agents/skills` discovery directory. Conflicting local skill edits cause setup
  to stop, so reconcile them with the canonical source before updating.
- Claude `SessionStart` to research context and project discovery, and `Stop` to
  a one-time handoff/checkpoint reminder. These hooks do not run experiments.
  Child runner sessions suppress the hooks to avoid recursive reminders.

The profile, hook settings and generated Codex skill copies are gitignored.
The setup CLI is the portable installation surface; a marketplace plugin is not
required. Older Bash installers are optional legacy global installation paths.

An editable Python installation is optional:

```sh
python -m pip install -e .
```

Use `python -m pip install -e ".[deck]"` only for weekly PowerPoint rendering.
Configure GPU/SLURM rules, dataset access, local tool permissions, language and
resource limits in `config/workspace_profile.local.json` and your agent's local
settings. Setup does not provision datasets, accounts or GPU infrastructure.

## Start and run research

```sh
python -m scripts.commands.research.research_autopilot init --project my_study --idea "Describe the question, known data, constraints and desired evidence"
python -m scripts.commands.research.research_autopilot plan --project my_study
python -m scripts.commands.research.research_autopilot run --project my_study --provider codex --max-steps 3 --timeout 1800 --max-seconds 3600
```

Use `--provider claude` to run the same queue with Claude. The selected CLI must
already be installed and authenticated. A `run` invokes the actual agent and
uses that account's resources. `plan` and setup `--dry-run` never invoke an LLM.

`init` copies the project template, captures the idea through brief intake, and
configures director planning after the initial brief task. The director must
queue concrete work and subsequent review/director steps with dependencies.
Workers use existing harness commands for literature, baseline inspection,
experiment plans, smoke runs, GPU scheduling, result ingestion and analysis,
claim graphs, writing, review and final exports. Research decisions remain
agent tasks; workflow YAML describes the lifecycle rather than executable code.

The supervisor refreshes project resume, state doctor and project health in order
before execution, retaining their logs. It executes only ready open commands
with approved vote gates. It
stops if another session owns an in-progress command. It runs one queue command
at a time; independent GPU jobs can still be dispatched together through the
GPU scheduler. Explicit multi-agent parallel groups use `agent_orchestrator`.

Each command must explicitly finish through the orchestrator and leave changed,
concrete expected output files beyond coordination state and handoff notes. Process exit 0 and pre-existing files alone are
not completion. Directory-only outputs need concrete evidence file paths before
unattended execution. The evidence check confirms file progress; it does not
prove a scientific claim or independently judge research quality. Director and
reviewer work, phase gates and claim checks remain necessary.

The default Codex adapter uses `exec --sandbox workspace-write`; the Claude
adapter uses `-p --permission-mode acceptEdits`. Existing local permissions still
apply. A denied tool, missing data or unapproved decision is a blocker, not an
instruction to bypass permissions. For customized orchestration, the local
runner profile can pass repeated `--extra-arg` options to `agent_runner`.
The bounded autopilot uses its explicit provider and built-in adapter; custom
runner profiles are used through `agent_orchestrator`.

## Resume and inspect

Every invocation writes prompts, CLI output and `run.json` to
`projects/<name>/state/sessions/autopilot_<id>/`. Existing project state and the
command queue remain authoritative. There is no hidden conversation dependency.

```sh
python -m scripts.commands.projects.project_resume --project my_study
python -m scripts.commands.projects.project_doctor --project my_study
python -m scripts.commands.research.research_autopilot plan --project my_study
```

Then run another bounded batch. A step/time limit is a continuation boundary.
`queue_drained` means there are no remaining queue entries to execute, **not** that
the research is publishable. `needs_attention` returns exit 2; read the run log
and blocker before changing the task. Interrupted commands stay visible for
review. Do not reset an active command merely to make the next run start.

The supervisor owns `state/sessions/autopilot.lock` while running. After a hard
crash, inspect its PID and confirm that process and its child CLI have stopped
before removing that single file. State-file `.json.lock`/`.csv.lock` sidecars
are permanent coordination files; do not remove them during work.

## Automated validation and distribution

GitHub Actions runs the existing full harness checks plus Windows/Linux setup,
runner, dispatch and lock regressions on Python 3.10 and 3.12. These tests use
local fake runners and do not require API credentials or paid model calls.

Before pushing, run:

```sh
python -m pytest scripts/tests -q
python -m ruff check scripts
python -m scripts.commands.projects.project_index refresh
python -m scripts.commands.release.release_check --project template --version v8.0.0 --skip-paper-build --strict-template-state
```

Private projects, local settings, credentials, datasets and model outputs must
stay outside the publishable file set. `check_publishable` and `privacy_audit`
check the public harness. Live scientific end-to-end validation additionally
requires an actual research question, accessible data, compute and agent login.

## Official integration references

- [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)
- [Codex local skill discovery](https://learn.chatgpt.com/docs/build-skills)
- [Claude programmatic execution](https://code.claude.com/docs/en/headless)
- [Claude hook reference](https://code.claude.com/docs/en/hooks)
