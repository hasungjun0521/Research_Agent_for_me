# Venue Review Plan

Use this file to decide which venue/year form should be used for form-based paper review.

## Active Review Forms

| Review Target | Form ID | Venue | Year | Track | Draft Path | Output Path | Status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| main draft | venue_year_template |  |  |  | `06_writing/draft.md` | `07_reviews/form_reviews/` | planned |

## How To Create A Form-Based Review

List available forms:

```bash
python -m scripts.commands.review.review_forms list
```

Create a review file from a registered venue/year form:

```bash
python -m scripts.commands.review.review_forms create-review --project {{PROJECT_NAME}} --form-id <form_id> --review-id <review_id> --paper 06_writing/draft.md --use-case internal_mock_review
```

Validate registered forms before relying on the review:

```bash
python -m scripts.commands.review.review_forms validate --strict
```

## Review Discipline

- Use the exact venue/year form for the target venue.
- Choose the correct use case: `internal_mock_review` for your own draft, `official_review` for assigned confidential reviews, or `manual_worksheet` when LLM generation is not allowed.
- Fill every required field, including scores, confidence, questions, ethical concerns, and reproducibility checks when present.
- Tie scores and criticisms to project evidence.
- Record missing evidence explicitly in `state/open_questions.md` or `07_reviews/revision_plan.md`.
