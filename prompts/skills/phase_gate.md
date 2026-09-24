# Phase Gate

Use this skill when deciding whether a research project can move from one phase
to the next.

## Procedure

```bash
python -m scripts.commands.research.phase_gate init --project <project>
python -m scripts.commands.research.phase_gate audit --project <project> --write-report
python -m scripts.commands.research.phase_gate set --project <project> --phase <phase> --status done --evidence <path> --note "<reason>"
```

## Guardrails

- Do not mark a phase `done` without evidence.
- Use `waived` only when the reason is explicit and acceptable for the project.
- Re-run the audit before handoff or before paper-claim strengthening.
