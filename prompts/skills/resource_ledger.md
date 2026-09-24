# Resource Ledger

Use this skill when a research pass consumes meaningful tokens, API calls, wall
time, GPU time, storage, or external compute budget.

## Procedure

```bash
python -m scripts.commands.reports.resource_ledger init --project <project>
python -m scripts.commands.reports.resource_ledger record --project <project> --id <entry_id> --kind gpu_hours --amount <number> --unit gpu_hour --exp-id <exp_id> --note "<what ran>"
python -m scripts.commands.reports.resource_ledger summary --project <project> --write-report
```

## Guardrails

- Prefer approximate entries over silent untracked cost.
- Use stable units such as `token`, `usd`, `gpu_hour`, `minute`, or `gb`.
- Link entries to `command_id` or `exp_id` when possible.
