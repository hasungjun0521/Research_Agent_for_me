# Experiment Completion

Use this when an experiment outcome is known and the project needs one durable
completion record instead of scattered manual edits.

Preferred workflow:

1. Record the observed result, status, dataset/split, method, baseline, evidence,
   and why the run was needed.
2. Explain why performance improved, regressed, or stayed flat. If the cause is
   uncertain, record the strongest hypothesis and what would falsify it.
3. Use the experiment completion CLI so the working result CSV, journal,
   analysis note, run_state, artifact registry, data roots, agent status, and
   event log move together.
4. Add final-export only when the row is stable enough for `09_report/results/`.

Use this command surface for the closeout:

```bash
python -m scripts.commands.experiments.experiment_complete --project <project> --exp-id <exp_id> --status succeeded --summary "<observed result>" --result-analysis "<why performance improved, regressed, or stayed flat>" --evidence <project-relative-evidence-path> --artifact metrics:metrics=<project-relative-metrics-path> --data-root <dataset_id>=<root_or_uri>
```

For failed or blocked runs, keep the same closeout pattern and set the real
status. Do not skip analysis: explain the likely failure cause, what evidence
supports that explanation, and what follow-up would distinguish competing
hypotheses. Use pending analysis only when the next action explicitly names the
analysis owner and file to update.

Required durable outputs:

- `05_results/experiment_results.csv`
- `05_results/experiment_journal.md`
- `05_results/experiment_journal.csv`
- `03_experiments/<exp_id>/analysis.md`
- `03_experiments/<exp_id>/run_state.json`
- `03_experiments/artifact_registry.csv` when output/evidence paths exist
- `03_experiments/data_roots.md` when new data roots or splits are used
