# Venue Review Forms

This folder stores reusable review forms by venue and year. Use it when a paper or draft must be reviewed according to a specific conference, workshop, or journal form.

## Layout

- `form_registry.json`: structured index of available forms.
- `venues/<venue>/<year>/<track>/review_form.md`: exact form text or a faithful local template.
- `venues/<venue>/<year>/<track>/rubric.md`: score anchors, policy notes, and reviewer instructions.

Keep real venue forms in this repository only when the repository access level is appropriate for those forms. If a form is confidential or copyrighted, store a private summary of fields and score anchors instead of copying full text.

## Commands

List registered forms:

```bash
python -m scripts.commands.review.review_forms list
```

Create a new venue/year form skeleton:

```bash
python -m scripts.commands.review.review_forms scaffold --id <venue>_<year>_<track> --venue <venue> --year <year> --track <track>
```

Register an existing form:

```bash
python -m scripts.commands.review.review_forms add --id <form_id> --venue <venue> --year <year> --track <track> --form-path review_forms/venues/<venue>/<year>/<track>/review_form.md --rubric-path review_forms/venues/<venue>/<year>/<track>/rubric.md
```

Create a project review from a form:

```bash
python -m scripts.commands.review.review_forms create-review --project <project> --form-id <form_id> --review-id <review_id> --paper 06_writing/draft.md --use-case internal_mock_review
```

Validate forms:

```bash
python -m scripts.commands.review.review_forms validate --strict
```

## Rules

- Preserve the exact venue/year field names and score scales when possible.
- Do not mix forms across years unless the venue reused the same form and the registry notes that decision.
- Do not treat a generated review as final until every required field in the selected form is answered.
- Every score should cite evidence from the draft, experiments, literature, or baseline registry.
- For `official_review` use, respect `llm_review_generation_allowed` and `llm_policy` in `form_registry.json`. If official-review LLM generation is forbidden, use only a manual worksheet.

## Registered Forms

- `eccv_2026_main`
- `cvpr_2026_main`
- `iclr_2026_main`
- `venue_year_template`
