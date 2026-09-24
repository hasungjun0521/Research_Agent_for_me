# Reviewer Risk Matrix

Use this skill when research readiness says the reviewer attack matrix is
missing concrete reviewer risks.

## Target File

Update:

```text
07_reviews/reviewer_attack_matrix.md
```

## Procedure

1. Read the current claim table, main experiment result table, robustness table,
   and paper/summary text that makes the claim.
2. List likely reviewer objections as concrete attacks, not generic concerns.
3. For each attack, record the current weakness, available evidence path, and
   response plan.
4. Convert unresolved high-impact attacks into command-queue work when they
   need experiments, analysis, or writing changes.
5. Refresh closeout:

```bash
python -m scripts.commands.projects.project_closeout --project <project> --write-report
```

Dashboard refresh is not part of this default skill. Use
`prompts/skills/dashboard_refresh.md` only when dashboard mode is explicitly
enabled.

## Quality Bar

Each row should let a future agent answer: what would a reviewer object to,
what evidence currently answers it, what remains weak, and which command should
fix it.
