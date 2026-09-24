# Weekly Dev Deck — Design Spec

**Date:** 2026-06-12
**Status:** Implemented 2026-06-12. Two details superseded by the
implementation: the structured progress source is `state/progress_hooks.jsonl`
(written by `progress_checkpoint`; §5's `progress_log.jsonl` name was wrong),
and tests live in `scripts/tests/test_weekly_deck.py` (not §11's
`scripts/commands/reports/`). Result/trend rows are window-filtered via
`experiment_journal.csv` `updated_at` as §5 specifies.
**Topic:** A harness command that turns a project's last-week development progress
into a polished, **image-first / glanceable** PowerPoint deck, built on top of a
user-provided template.

---

## 1. Goal & scope

Generate one `.pptx` per project summarizing the **last 7 days** of progress, using
the lab's branded template (`config/ppt_template_local.pptx`, SNU/VIPLab "material"
theme). The deck must be understandable **at a glance**: dominated by charts,
stat tiles, and harvested result figures rather than walls of text.

**In scope:** per-project deck, template-based builder, auto data collection,
chart + KPI-tile + figure rendering, manual CLI.
**Out of scope (YAGNI):** scheduling/automation, multi-project digest, HTML output,
in-app editing. (Scheduling may be added later once the CLI is proven.)

## 2. Decisions (from brainstorming)

| Axis | Decision |
|------|----------|
| Dependency policy | **Optional** dependency. Core `pyproject` stays `dependencies=[]`; add `[project.optional-dependencies] deck`. Command lazy-imports and errors with an install hint if missing. |
| Scope | **Per-project** (`--project` required), matching existing report commands. |
| Automation | **Manual CLI first.** No cron/schedule in v1. |
| Base look | **Template-first.** Open `config/ppt_template_local.pptx`; fall back to a built-in theme builder if the template is absent. |
| Cover | Title = project (research) name; subtitle = date (week range by default, `--cover-date today` to use the single generation date). |

## 3. Visual & image guidance (primary design principle)

The deck's value is being **glanceable**. Every content slide follows these rules:

1. **Takeaway-first.** Each content slide leads with a one-line bold conclusion
   ("so what"), then the supporting visual fills the rest. The reader gets the
   point before reading any bullet.
2. **Numbers become graphics.** KPIs render as a **stat-tile strip image** (big
   number + label + ▲/▼ delta in green/red + optional mini sparkline of the
   metric's weekly trend), not as a text line.
3. **Chart suite, data-driven.** Auto-select the charts the data supports:
   - metric-over-time line (baseline vs ours) — primary trend;
   - per-experiment **delta bars** (horizontal, green/red by sign) — "what moved this week";
   - baseline-vs-ours grouped bars per dataset/metric (when present).
4. **Figure harvesting.** Scan `05_results/figures/`, `03_experiments/*/results/*.{png,jpg,jpeg}`
   and other project image artifacts **modified within the week window**; place the
   most recent `--max-figures` (default 4) on an "이번 주 산출물" slide with a
   one-line caption each. This surfaces qualitative results (attention maps, sample
   outputs, diagrams) automatically.
5. **Status color chips.** Experiments / next-actions get consistent color chips
   (done = green, in-progress = amber, blocked = red).
6. **Density limits.** ≤ 5 bullets per slide, ≤ ~12 words per bullet, **one dominant
   visual per slide**, and ≥ ~50% of each content slide's area is visual.
7. **Palette match.** Derive the chart accent palette from the template (navy
   `#161D2F`-ish + orange) so embedded matplotlib visuals match the template rather
   than clash.
8. **Captions are conclusions.** Each image caption states the takeaway, not a
   description of the axes.
9. **Graceful degradation.** If the week has no figures/metrics, fall back to a
   concise text slide and explicitly flag "이번 주 시각 산출물 없음" rather than
   shipping an empty-looking slide.

## 4. Architecture / modules

Three focused modules under `scripts/commands/reports/`:

- **`weekly_deck.py`** — CLI (argparse) + orchestration + `collect_week_data()`
  (data gathering, no rendering). Follows the existing report-command pattern:
  `--project` required, `paths.project_root()`, `HarnessError`, `main() -> int`.
- **`weekly_deck_charts.py`** — matplotlib visual renderers (`render_kpi_strip`,
  `render_trend_chart`, `render_delta_bars`, `render_grouped_bars`), figure
  harvesting (`harvest_week_figures`), Korean-font registration, and the
  template-derived palette. Pure functions: data in → PNG path out.
- **`weekly_deck_builder.py`** — pptx assembly: open template, fill placeholders,
  add content slides from the `TITLE_ONLY_1` layout, embed images,
  `strip_bracket_decorations()`, and the built-in theme fallback builder.

Rationale: data, rendering, and pptx assembly each have one responsibility and can
be tested independently.

## 5. Data collection (`collect_week_data`)

**Window:** `[--since, --until]`; default `--until = today`, `--since = until - 7d`
(`--weeks N` widens it).

| Output field | Source |
|---|---|
| `kpis` (experiments run, best Δ, commits, blockers resolved) | count of `state/sessions/progress_log.jsonl` records in window; max `delta` from `05_results/experiment_results.csv`; `git log` count for the `projects/<name>/` subtree; `kind`/blocker transitions in the log |
| `highlights` | window `progress_log.jsonl` records with `kind ∈ {result, experiment_result, direction}` (`summary` field) |
| `trend` / `delta` series | `experiment_results.csv` (`metric`,`value`,`delta`) keyed by `experiment_journal.csv` `updated_at` for time ordering |
| `next_actions` | `state/next_actions.md` |
| `figures` | image artifacts under figure dirs modified in window (see §3.4) |

Parsing prefers the structured `progress_log.jsonl` (fields: `timestamp`, `kind`,
`summary`, `agent`, optional `exp_id`) over the markdown mirror. Missing/empty
sources degrade to placeholders, never crash.

## 6. Slide composition (template-based)

Order (cover from template `TITLE`; content from `TITLE_ONLY_1`, added as needed):

1. **Cover** — title = project name, subtitle = date; bracket decorations stripped.
2. **이번 주 요약** — KPI stat-tile strip image (full width) + ≤3 takeaway bullets.
3. **실험 결과 추이** — trend line chart (baseline vs ours), takeaway caption.
4. **이번 주 변화 (Δ)** — per-experiment delta bars (only if ≥1 experiment in window).
5. **이번 주 산출물** — harvested figures grid (only if figures found).
6. **다음 주 액션** — next-actions bullets with status chips.

Slides 4–5 are conditional on data; the deck never renders an empty slide.
Chart/KPI/figure images are written to a `_build/` scratch dir then embedded.

## 7. CLI

```
python -m scripts.commands.reports.weekly_deck build --project <name> \
  [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--weeks 1] \
  [--metric COL] [--template PATH] [--out PATH] \
  [--max-figures 4] [--cover-date week|today] [--dry-run]
```

`--dry-run` prints collected `WeekData` summary + intended output path; writes nothing.
`--metric` selects the chart's metric column; when omitted it auto-detects the most
frequent `metric` value in `experiment_results.csv`.
Template resolution order: `--template` > `workspace_profile.local.json:weekly_deck.template`
> default `config/ppt_template_local.pptx` > built-in fallback theme.

## 8. Output placement

```
projects/<name>/05_results/weekly_decks/weekly_<YYYYMMDD>.pptx
projects/<name>/05_results/weekly_decks/_build/*.png          # intermediate visuals
```

**Not** `09_report/` (reserved for final artifacts). `--out` overrides the path.

## 9. Optional dependency & error handling

- `pyproject.toml`: `[project.optional-dependencies] deck = ["python-pptx>=1.0", "matplotlib>=3.7"]`.
  Core `dependencies` stays `[]`.
- Lazy-import `pptx`/`matplotlib`; if missing, raise `HarnessError` suggesting
  `pip install python-pptx matplotlib` (or `pip install -e .[deck]`).
- Korean font: register `Noto Sans CJK KR` from the system font file; fall back to
  the default font with a warning if unavailable.
- LibreOffice (`soffice`) is **not** required at runtime; it is only a dev aid for
  PNG previews and is not a dependency.

## 10. Registration checklist

- New command files under `scripts/commands/reports/`.
- `pyproject.toml` optional-deps `deck` extra.
- Reference in `AGENTS.md` + `CLAUDE.md` operating rules and a `README.md` runbook
  ("ask Claude to build the weekly deck").
- Optional `prompts/skills/weekly_deck.md` runbook.
- **Develop and validate against the `template` project only**; real projects stay
  untouched.
- `.gitignore` already excludes `config/ppt_template_local.pptx` and `config/*.local.pptx`.

## 11. Testing

`scripts/commands/reports/test_weekly_deck.py` (pytest; `pytest.importorskip("pptx")`
and `matplotlib`):

- `collect_week_data` on a synthetic tmp project (seeded `progress_log.jsonl` +
  `experiment_results.csv` + `next_actions.md`) returns expected KPIs and window
  filtering.
- `strip_bracket_decorations` removes `[   ]` layout shapes.
- `harvest_week_figures` selects only in-window images, capped at `--max-figures`.
- `build_deck` produces a non-empty `.pptx` with the expected conditional slide count.
- Empty-week path degrades to placeholders without raising.

## 12. Gate sequence

`py_compile` → `ruff` → `workflow_audit` → `smoke_test` →
`validate_project --project template --strict` → `verify_harness --project template --skip-paper-build`.

## 13. Open / deferred

- Cover-date default is the week range; `--cover-date today` available.
- Scheduling, multi-project digest, HTML export deferred to a later iteration.
