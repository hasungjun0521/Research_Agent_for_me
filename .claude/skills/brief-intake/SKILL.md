---
name: brief-intake
description: Turn a rough/vague research idea into durable project state at the START of a new project. Use when the user says "I want to research X" or describes a new idea where the research question, motivation, contribution, dataset, metric, or baseline is still missing or only partly answered. Captures known fields into 00_brief/ and parks unknowns in open_questions instead of guessing. Wraps scripts.commands.projects.brief_intake. (For resuming an EXISTING project, use project-resume instead.)
---

# Brief Intake

Entrypoint for starting a new project from a rough idea. Convert what's known
into durable brief files; park what's unknown as open questions rather than
guessing missing research setup. Source: `prompts/skills/brief_intake.md`.

## When to use

- A new project starts from a vague idea.
- Research question, motivation, contribution, dataset, metric, or baseline is
  missing or only partly specified.
- The user has answered some but not all setup questions.

## Workflow

1. Run the intake wizard with whatever fields are known:
   ```bash
   python -m scripts.commands.projects.brief_intake --project <name>
   ```
2. Capture only known fields. Put unknowns in `state/open_questions.md` instead
   of inventing answers.
3. Let it update `00_brief/` and `02_planning/intake_summary.md`.
4. Once the brief has enough detail, route director triage / next actions.
5. If the pass is long, persist with the `progress-checkpoint` skill.

## Outputs

- `00_brief/research_question.md`, `00_brief/motivation.md`,
  `00_brief/contribution_candidates.md`, `00_brief/constraints.md`
- `02_planning/intake_summary.md`
- `state/open_questions.md`

## Guardrails

- Do not guess datasets, metrics, baselines, or contributions — park them as
  open questions.
- Keep brief work inside `projects/<name>/`.
