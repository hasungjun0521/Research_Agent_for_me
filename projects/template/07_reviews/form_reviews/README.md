# Form-Based Venue Reviews

Store paper or draft reviews generated from `review_forms/form_registry.json`.

Recommended command:

```bash
python -m scripts.commands.review.review_forms create-review --project {{PROJECT_NAME}} --form-id <form_id> --review-id <review_id> --paper 06_writing/draft.md --use-case internal_mock_review
```

Each review should record:

- form id, venue, year, track, and form path
- target paper or draft path
- score table using the venue's scale
- form answers with evidence
- required revisions and missing evidence
