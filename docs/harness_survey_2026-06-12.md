# External Research-Harness Survey & Adoption Roadmap (2026-06-12)

Survey of research-agent harnesses and adjacent tooling, run as 6 parallel
web-research passes plus a 5-way internal audit of this workspace. This file
records what was adopted immediately and the ranked backlog of ideas worth
adopting next. Everything proposed here is file-based, dependency-free, and
mapped onto existing folders/commands — no framework adoption.

## Categories Surveyed

| Category | Representative systems |
| --- | --- |
| End-to-end AI scientists | Sakana AI Scientist v1/v2 (BFTS experiment tree), Agent Laboratory + AgentRxiv, HKUDS AI-Researcher, AllenAI CodeScientist, Google AI co-scientist (Elo tournament), FutureHouse Robin / Edison Kosmos (world model, statement-level traceability) |
| ML experiment automation | AIDE (solution tree), Microsoft RD-Agent (hypothesis loop), MLE-bench agents (pass@k), Curie (rigor verification), DS-Agent (case-based reasoning), Weco (metric contract), MLE-STAR (ablation-driven refinement) |
| Coding-agent harness patterns | SWE-agent (ACI ergonomics), OpenHands microagents, GitHub spec-kit (constitution, cross-artifact analyze), beads (dependency-aware agent issue tracker), Ralph loops ("signs"), Claude Code superpowers/best practices |
| Multi-agent orchestration | Anthropic multi-agent research system (task contracts, effort tiers), LangGraph (durable execution), AutoGen/AG2, MetaGPT (publish-subscribe, executable feedback), OpenAI Agents SDK |
| Reproducibility tooling | Hydra (config snapshots), W&B sweeps, MLflow, DVC (content-hash lockfiles), Sacred (env capture), Guild AI (run diff), showyourwork (figure provenance) |
| Literature workflows | PaperQA2 (evidence contexts), OpenScholar, STORM (perspective outlines), Elicit (extraction schemas), scite (citation stances), Undermind (discovery-curve saturation), gpt-researcher |

## Adopted In This Pass (2026-06-12)

- `log_digest` command — bounded head/tail/failure-pattern digest of huge
  SLURM/training logs (from Weco's log-truncation contract and AIDE's
  summarization operator).
- `literature-review` skill + `prompts/skills/literature_review.md` runbook —
  durable search-round log (`01_literature/search_log.csv`), per-paper stance
  notes with verbatim quotes/locators, novelty cross-check against
  contribution candidates, saturation stopping rule (from PaperQA2, Undermind,
  Elicit, deep-research verification patterns).
- `claim-evidence`, `baseline-intake`, `weekly-deck` agent skills — existing
  CLI families exposed as discoverable lifecycle entry points.
- Registration hardening (internal audit): reverse-direction command-registry
  test, `.claude/skills` consistency checks in `workflow_audit`, full
  34-runbook registration tuple, `state_doctor --write-report` doc fix,
  fsync-before-replace in atomic state writes.
- Weekly dev deck feature integration completed (registry, tests in
  `scripts/tests/`, runbook/skill registration, docs).
- Second adoption batch (same day): `seed_variance` (Tier 1 #3), `env_capture`
  (Tier 3 #11), `run_diff` (Tier 3 #13), bib hygiene checks (Tier 6 #27),
  `project_resume --list` (active-project surface), and the ACI-inspired lean
  dispatched-prompt style (worker prompts ~2k tokens instead of ~17k; first
  slice of the output-ergonomics backlog item).

## Ranked Adoption Backlog

Priority is value-for-a-single-SLURM-researcher per unit effort. Each item
names its inspiration and landing zone.

### Tier 1 — result integrity (highest trust value)

1. **Statement-to-evidence grounding audit** (Kosmos; medium). ✅ adopted 2026-06-12 (in `paper_claim_linter`). Extend
   `paper_claim_linter`/`claim_evidence_board` so every report statement maps
   to a result row, artifact, or bib entry; unmatched statements become
   findings. The single strongest defense against agent-overclaimed results.
2. **Preregistration drift verification** (Curie; medium). ✅ adopted 2026-06-12 (`preregistration_helper drift`). Extend
   `preregistration_helper audit` to machine-compare the preregistration
   (metric, split, seeds, planned arms) against `run_state.json` and result
   rows; silent drift becomes a finding.
3. **Cross-seed variance audit** (CodeScientist replication; small). ✅ adopted 2026-06-12 (`seed_variance`). A
   `seed_variance` check over multi-seed rows in `experiment_results.csv`
   flagging claims supported by a single lucky seed; feeds `claim_graph`.
4. **Val/test split provenance lint** (AIRA-dojo; small). Add a `split` field
   to result rows; `paper_claim_linter` rejects val-only numbers in
   reader-facing claims and reports the generalization gap.

### Tier 2 — experiment-loop ergonomics

5. **Metric contract + log metric extraction** (Weco; small). Planner records
   metric name/goal/parse-regex per family; a `result_ingest parse-log`
   subcommand lifts metrics from job logs into the CSV (composes with
   `log_digest`).
6. **Experiment lineage tree** (AIDE; medium). `parent_experiment_id` +
   `edge_kind (draft|debug|improve)` on plan nodes and journal rows, plus a
   rendered tree view; makes "which branch is dead" explicit after 15+ runs.
7. **Debug-depth budget** (AIDE; small). Track consecutive debug attempts per
   branch in the journal; `experiment_diagnosis` warns "abandon this branch"
   past a configurable depth.
8. **Per-family GPU-hour budget envelope** (MLE-bench, CodeScientist; medium).
   Budgets in the plan JSON; `gpu_scheduler` plan diagnostics exclude
   over-budget jobs; `resource_ledger` reports burn-down.
9. **Best-solution snapshot** (AIDE; small). On a new family-best result,
   `experiment_complete` snapshots the exact script/config + git commit, so
   the eventual `09_report/src` export is trivial.
10. **Multi-attempt select-best (pass@k)** (MLE-bench; medium). Planner flag
    expanding one main node into N seeded sibling runs with a select-best
    closeout; the seed spread doubles as robustness evidence.

### Tier 3 — reproducibility plumbing

11. **Environment auto-capture** (Sacred/MLflow; small). ✅ adopted 2026-06-12 (`env_capture`). Fill the existing
    `reproducibility_manifest.json` fields (commit, dirty flag, deps,
    hardware) automatically at `run_state start` / `gpu_scheduler dispatch`.
12. **Per-run config snapshot + overrides record** (Hydra; small). Copy the
    resolved config into `results/<run>/config_snapshot.yaml` at launch;
    multi-seed runs stop overwriting each other's evidence.
13. **Run diff** (Guild AI; small). ✅ adopted 2026-06-12 (`run_diff`). Side-by-side config/manifest/metric diff
    of two exp ids — answers "why did performance change" mechanically.
14. **Sweep spec + expansion** (W&B/Hydra; medium). Declarative `sweep.yaml`
    (grid/random, bounds, max_runs) expanded into planner DAG nodes and
    scheduler queue entries.
15. **Stage fingerprint lockfile** (DVC; medium). Content hashes of declared
    inputs/outputs at `experiment_complete`; staleness check exposes results
    whose code/data changed after the fact.
16. **Figure provenance manifest** (showyourwork; medium). Map each
    `09_report` figure/table to generating script + input results; lint on
    release so regenerated results can't leave stale figures.

### Tier 4 — orchestration robustness

17. **Four-field task contract** (Anthropic; small). `objective`,
    `output_format`, `tool_guidance`, `boundaries` on queue entries; rendered
    into worker prompts; warn-only for legacy entries.
18. **Stale-dispatch lease + reap** (LangGraph durability; medium).
    `dispatched_at`/`attempts` fields plus an orchestrator `reap` subcommand
    so dead workers stop leaving commands `in progress` forever.
19. **Partial-batch finish-parallel** (LangGraph pending-writes; medium).
    Per-command `--result <id>=done|failed` instead of all-or-nothing close.
20. **Dependency-result digest injection** (Agents SDK; small). Prepared
    prompts embed each done dependency's status/notes/output paths.

### Tier 5 — durable state & memory

21. **Hypothesis ledger with verdicts** (RD-Agent; medium).
    `03_experiments/hypotheses.json`: statement → linked experiments →
    supported/refuted/inconclusive verdict; the in-loop science record the
    claim graph later consumes.
22. **Project constitution** (spec-kit; small). `00_brief/constitution.md`
    with immutable invariants (split freeze, no dev-set tuning, seed policy);
    rendered into dispatched prompts; linter warns on conflicts.
23. **Memory compaction pass** (beads; small). ✅ adopted 2026-06-12 (`memory_compact`). Summarize stale
    `agent_memory.md`/journal entries into a digest, archive verbatim text to
    `state/sessions/` — keeps always-read files small.
24. **Boundary handoff** (small). Generalize `progress_checkpoint
    limit-handoff` into a typed `handoff` usable at any session boundary.

### Tier 6 — literature depth

25. **Literature evidence ledger** (PaperQA2/scite; medium).
    `01_literature/evidence_ledger.csv` with verbatim quote + locator +
    stance per claim; `claim_graph` gains literature stance edges and a
    contradiction gate (ContraCrow pattern).
26. **Novelty audit command** (Undermind; medium). Cross-reference
    contribution candidates against the related-work matrix; contributions
    without a closest-prior-art row fail strict mode.
27. **Bib hygiene checks** (small). ✅ adopted 2026-06-12 (in `source_credibility_audit`). Extend `source_credibility_audit` with
    duplicate keys, placeholder entries, preprint-superseded detection.

## Internal Consolidation Backlog (from the audit, no external inspiration needed)

- **`project_doctor` single command**: state_doctor → project_health →
  hygiene in the right order with reports written by default; today's ritual
  is three commands, three write flags, and a memorized ordering rule.
- **Command tiering**: 69 registered commands for one researcher. Introduce a
  legacy tier (ralph_loop, research_loop, project_intake,
  preregistration_helper, review_to_revision candidates) and verb-style
  consolidation (`claims board|graph|lint`, `experiment state|checkpoint|
  ingest|complete|diagnose`).
- **Single normative rule list**: AGENTS.md as the one rule source; CLAUDE.md
  reduced to Claude-specific deltas; HANDOFF/README prompts reduced to
  pointers. Same ~10 rules currently restated in 5-7 places that drift.
- **`state.py` StateDoc refactor**: nine near-identical ~60-line state-doc
  families → one generic load/write/mutate helper defined by data.
- **Unit tests for the riskiest logic**: gpu_scheduler plan/exclusion,
  agent_orchestrator batch-safety filters, state_doctor repair decisions.
- **Active-project surface** ✅ adopted 2026-06-12: `project_resume --list` (last-touched, headline,
  next action per project); nothing today records which project is active.
- **ACI output ergonomics** (SWE-agent): shared formatter capping long CLI
  output with explicit "rerun with --full" notes and suggested-next-command
  hints on the high-traffic commands.
- **Neutral placeholders** in `config/workspace_profile.example.json` and
  `DEFAULT_PROFILE` (real partition/node names belong only in the local
  profile).
- **HANDOFF.md refresh discipline**: rewrite validation status after each
  release; collapse audit-slice history into the changelog.

## Method Note

Run as 11 parallel agents (6 surveyors with web access, 5 read-only internal
auditors including a full gate-baseline run) on 2026-06-12. Survey raw output
is session-local; this file is the durable synthesis. Re-run the survey when
planning the next major version rather than trusting this snapshot blindly.
