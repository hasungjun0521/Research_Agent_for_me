# Installed Agent Skills

Two skill sources feed Codex (and Claude Code) in this workspace:

1. **Upstream general-purpose skills** from
   `https://github.com/addyosmani/agent-skills`, installed in `~/.codex/skills/`.
2. **Workspace-local harness skills** that live in this repo under
   `.claude/skills/` and are installed into repository-local `.agents/skills/`
   by `automation_setup` so Codex can discover them too.

Claude Code reads `.claude/skills/` directly. Codex and Gemini CLI need the
workspace-local skills linked into their own skills home first — run
`tools/install_codex_skills.sh` (→ `~/.codex/skills/`) or
`tools/install_gemini_skills.sh` (→ `~/.gemini/skills/`). Both installers only
touch destinations they own and never clobber an unrelated real skill dir.

## Installed Skill Set

- `using-agent-skills`
- `idea-refine`
- `spec-driven-development`
- `planning-and-task-breakdown`
- `incremental-implementation`
- `test-driven-development`
- `debugging-and-error-recovery`
- `code-review-and-quality`
- `code-simplification`
- `context-engineering`
- `source-driven-development`
- `doubt-driven-development`
- `frontend-ui-engineering`
- `browser-testing-with-devtools`
- `api-and-interface-design`
- `security-and-hardening`
- `performance-optimization`
- `ci-cd-and-automation`
- `git-workflow-and-versioning`
- `documentation-and-adrs`
- `deprecation-and-migration`
- `shipping-and-launch`

## Workspace-Local Skills

These skills wrap this repo's harness CLIs as auto-discoverable runbooks. The
canonical files are tracked in the repo at `.claude/skills/<name>/SKILL.md`
(read directly by Claude Code). The same `SKILL.md` format works for Codex, so
setup copies them into `.agents/skills/` without changing global settings.

| Skill | Lifecycle entrypoint | Wraps |
| --- | --- | --- |
| `brief-intake` | Start a new project from a rough idea | `projects.brief_intake` |
| `project-resume` | Resume / triage an existing project | `projects.project_resume`, `state_doctor`, `project_health` |
| `literature-review` | Durable literature pass: search rounds, paper notes, novelty checks | `reports.source_credibility_audit`, `01_literature/` conventions |
| `experiment-run` | Plan (smoke-first DAG) and close out experiments | `experiments.experiment_planner`, `experiment_complete` |
| `gpu-dispatch` | Queue/dispatch independent GPU jobs in a bounded batch | `experiments.gpu_scheduler`, `run_state` |
| `agent-orchestration` | Dispatch independent command-queue work as multi-agent passes | `agents.agent_orchestrator`, `review.command_queue` |
| `skill-synthesis` | Autonomously create new skills from mistakes or corrections | Self-evolution via the 7-surfaces protocol |
| `baseline-intake` | Register/clone/inspect baselines and align code structure | `baselines.baseline_library`, `baseline_intake`, `repo_discovery`, `baseline_sandbox`, `baseline_compare` |
| `claim-evidence` | Connect paper claims to result evidence before strengthening claims | `reports.claim_graph`, `claim_evidence_board`, `paper_claim_linter`, `data_metric_audit` |
| `progress-checkpoint` | Persist durable mid-pass progress / limit handoff | `review.progress_checkpoint` |
| `weekly-deck` | Build an image-first weekly progress deck (PowerPoint) | `reports.weekly_deck` |
| `release-closeout` | Finalize for handoff / publication / harness release | `projects.project_closeout`, `validate_project`, `release.privacy_audit`, `reports.artifact_packager` |
| `project-hygiene` | Tidy project folder structure (09_report bloat, lock debris, drift) | `projects.project_hygiene` |

These complement (do not replace) the project-local runbooks in
`prompts/skills/`; each skill points back to its source runbook there.

### Installing the workspace-local skills

Recommended from the repo root:

```sh
python -m scripts.commands.release.automation_setup --dry-run
python -m scripts.commands.release.automation_setup
```

Optional legacy global installation:

```bash
tools/install_codex_skills.sh            # symlink into ~/.codex/skills (default)
tools/install_codex_skills.sh --copy     # copy instead (if symlinks are undesirable)
tools/install_gemini_skills.sh           # symlink into ~/.gemini/skills (Gemini CLI)
tools/install_gemini_skills.sh --copy    # copy instead
```

Each installer only touches destinations it owns (symlinks to this checkout, or copies marked
with `.workspace-managed`); it never clobbers an unrelated real skill directory.
Restart the agent after running so it re-scans the skills home. The `~/.codex/`
and `~/.gemini/` links are machine-local and not tracked in git — re-run the
installer on a fresh agent home or after moving the repo.

## Harness Mapping

The role mapping lives in:

`prompts/shared/skill_usage.md`

Agents should use that file to pick only the skills relevant to the current pass. Do not load every skill for every task.

## Updating Skills

To install or reinstall one skill from upstream, remove the target skill directory under `~/.codex/skills/` and run:

```bash
python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py --repo addyosmani/agent-skills --path skills/<skill-name>
```

Restart Codex after installing or updating skills.

To install the full recommended set on a fresh Codex home:

```bash
for skill in using-agent-skills idea-refine spec-driven-development planning-and-task-breakdown incremental-implementation test-driven-development debugging-and-error-recovery code-review-and-quality code-simplification context-engineering source-driven-development doubt-driven-development frontend-ui-engineering browser-testing-with-devtools api-and-interface-design security-and-hardening performance-optimization ci-cd-and-automation git-workflow-and-versioning documentation-and-adrs deprecation-and-migration shipping-and-launch; do
  python ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py --repo addyosmani/agent-skills --path "skills/$skill"
done
```

## First Agent Pass Order

1. Read `README.md`, `AGENTS.md`, and `prompts/shared/skill_usage.md`.
2. Select the smallest applicable skill set for the task.
3. Read `prompts/shared/research_context.md` and `prompts/shared/output_contracts.md`.
4. Read the relevant role prompt under `prompts/agents/`.
5. Use `scripts/commands/projects/project_resume.py` to summarize the target
   project's file state before choosing work.
6. Read the project state files named by that role prompt when more detail is
   needed.
7. Update status through `scripts/commands/agents/agent_status.py`, command
   ownership through `scripts/commands/review/command_queue.py`, loop recap
   through `scripts/commands/review/loop_summary.py`, and durable mid-pass
   checkpoints through `scripts/commands/review/progress_checkpoint.py`.
