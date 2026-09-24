# Research Principles

## Reproducibility

Research claims should be traceable to files. Keep configs, logs, metrics, and analysis notes near the experiment record. A future agent should be able to answer what was run, why it was run, and what changed.

## Modest Claims

Make the narrowest claim supported by the evidence. A useful result does not automatically imply generality, causality, or novelty. Stronger claims require stronger evidence.

## Baseline Discipline

Every empirical claim needs a meaningful comparison. Baselines should be selected because reviewers would expect them, prior work uses them, or they isolate the contribution.

## Ablation Discipline

If the project claims that a component matters, an ablation should test that component. If ablation is impossible, the limitation should be explicit.

## Failure-Case Analysis

Failure cases are evidence, not clutter. Record where the method fails, which conditions trigger failures, and whether failures weaken the claim.

## Reviewer Mindset

Assume reviewers will ask:

- Is the problem important?
- Is the novelty real?
- Are baselines fair?
- Are metrics appropriate?
- Are results reproducible?
- Are claims narrower than the evidence?
- Are limitations explicit?

## File-State First

Use files and templates as the durable workflow interface. Automation should
only encode a workflow that a fresh agent can understand from project files.
