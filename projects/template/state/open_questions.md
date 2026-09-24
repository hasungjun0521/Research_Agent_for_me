# Open Questions

## Scientific Questions

| Question | Why It Matters | Owner Agent | Evidence Needed | Status |
| --- | --- | --- | --- | --- |
| What is the precise research question? | Determines literature and experiment scope. | motivation_planner | Updated brief. | open |
| What constraints did the user give for data, compute, deadline, target venue, or deliverable? | Prevents the agent from planning an unrealistic research loop. | motivation_planner | User-provided setup or brief. | open |

## Experimental Questions

| Question | Why It Matters | Owner Agent | Evidence Needed | Status |
| --- | --- | --- | --- | --- |
| What is the minimum viable experiment? | Prevents premature large-scale implementation. | experiment_designer | Hypothesis, baseline, metric. | open |
| Are GPU/server rules configured in `config/workspace_profile.local.json`? | Expensive runs need scheduler limits and queue checks before launch. | code_agent | Workspace profile and GPU scheduler plan. | open |

## Literature Questions

| Question | Why It Matters | Owner Agent | Evidence Needed | Status |
| --- | --- | --- | --- | --- |
| Which prior work defines the strongest baseline? | Baseline choice affects validity. | literature_reviewer | Paper notes and matrix. | open |

## Implementation Questions

| Question | Why It Matters | Owner Agent | Evidence Needed | Status |
| --- | --- | --- | --- | --- |
| What code is needed for exp_001? | Implementation should follow experiment design. | code_agent | Experiment config. | open |

## Writing Questions

| Question | Why It Matters | Owner Agent | Evidence Needed | Status |
| --- | --- | --- | --- | --- |
| What claims can the abstract make? | Prevents overclaiming. | writing_agent | Result interpretation. | blocked |
