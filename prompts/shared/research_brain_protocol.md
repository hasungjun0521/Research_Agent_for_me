# Research Brain Protocol

Use this protocol to reuse project-local lessons without loading large prior
sessions. It generalizes the external Brain Index pattern into this repository's
existing `state/pattern_memory.json` workflow.

## Retrieval Rule

Before a director or lead-style pass makes a non-trivial routing decision:

1. Search `state/pattern_memory.json` with `scripts/commands/review/pattern_memory.py search`.
2. Match on anchor-like trigger terms first, then supporting terms.
3. Read only the matching pattern rows and their evidence files.
4. Treat patterns as guidance, not proof. Evidence still controls claim status.

Example:

```bash
python -m scripts.commands.review.pattern_memory search --project <project> --query "baseline smoke"
```

## Pattern Shape

Patterns should be small and durable:

- `id`: stable identifier.
- `title`: human-readable name.
- `tags`: categories such as `baseline`, `gpu`, `statistics`, `review`,
  `dashboard`, `paper`, or `artifact`.
- `triggers`: anchor-like phrases that should activate the pattern.
- `recommendation`: the action to take when the trigger matches.
- `evidence_files`: project-relative files that justify the pattern.
- `status`: `candidate`, `active`, or `deprecated`.

Use the CLI instead of hand-editing JSON:

```bash
python -m scripts.commands.review.pattern_memory add --project <project> \
  --id baseline_smoke_first \
  --title "Smoke baseline before full runs" \
  --tag baseline \
  --trigger "before reproducing a cloned baseline" \
  --recommendation "Run baseline_sandbox.py and a tiny smoke command before scheduler launch." \
  --evidence 08_baselines/code_structure_plan.md
```

## Good Research Brain Entries

Good entries capture reusable workflow lessons, for example:

- A baseline repository needs a specific sandbox check before execution.
- A dataset split has a known leakage risk.
- A metric is invalid for a specific claim type.
- Reviewers often attack a particular missing ablation.
- A GPU job class needs a smaller smoke run before full scheduling.

Do not store private credentials, raw reviewer identities, unpublished third
party data, or large logs in pattern memory. Store pointers to project files
instead.

## Interaction With Evidence

Pattern memory can influence routing and prioritization. It cannot make a
research claim supported. Claims still need claim-evidence rows, result tables,
robustness checks, and paper-claim linting.
