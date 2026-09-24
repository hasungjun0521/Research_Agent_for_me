# State Doctor

Use when a project is hard to resume, state files look contradictory, or a fresh
agent cannot tell what is stale.

State doctor is a consistency diagnosis for the file-state system. It answers:
"Can a new agent trust this project state?" Use project health instead when the
state is readable but the research needs priority/blocker triage.

## When To Use

- Command queue and agent status disagree.
- Result files exist but experiment analysis or journal rows are missing.
- GPU jobs are queued/running without command, expected output, or check procedure.
- A project has not been touched for a while and needs a repair list.

## Agent Workflow

1. Generate a state doctor report for the project.
2. Inspect the highest-severity issue first.
3. If the existing report is a starter file, do not trust it as evidence;
   replace it with a fresh diagnosis.
4. Preview repair before writing when the user asks for safe missing starter
   files to be repaired. Then repair only safe missing starter artifacts
   automatically. Safe repairs include missing health/state reports, brief
   intake wizard, experiment plan, data-root ledger, artifact registry,
   experiment DAG skeleton, working result table, experiment journal, progress
   checkpoint log, progress log, claim board, claim graph skeleton, terminology
   glossary, baseline comparison starter, code-structure plan, and agent quality
   audit starter. For missing core continuation files and state JSON, repair
   from `projects/template/` rather than inventing a new schema.
   Repair must not invent research content, datasets, metrics, baselines,
   results, or conclusions.
   When repair restores `state/command_queue.json` or `state/next_actions.md`,
   the human-readable next-actions mirror should be synced from the structured
   command queue.
   Template-backed JSON repairs should be validated before writing; if a
   starter is malformed, report the repair error instead of creating the file.
   After any repair or repair preview, report the repair mode, repaired or
   planned files, and repair errors in the final handoff so the next agent can
   tell whether the state is clean or only partially repaired.
5. If the user wants routing, preview suggested command entries first, then
   enqueue them rather than hand-editing `state/command_queue.json`.
   Doctor-derived commands use a `doctor_` id prefix for traceability.
6. Use harness CLIs for structured JSON state; do not hand-edit command queue or status JSON.
7. Save any repair or blocker with a progress checkpoint.
8. After repair or state diagnosis, refresh project health so the next action
   is routed from the latest state doctor report.

## Output

- `state/state_doctor.md`
