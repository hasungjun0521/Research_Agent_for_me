# Private GitHub Publish Checklist

Use this checklist to publish the harness without real research projects.

## What Is Included

- Optional dashboard support code under `dashboard/`
- Harness scripts under `scripts/`
- Agent and shared prompts under `prompts/`
- Workflow definitions under `workflows/`
- The reusable starter project under `projects/template/`
- Repository metadata and docs

## What Is Excluded

`.gitignore` excludes real project folders by default:

```gitignore
projects/*
!projects/template/
!projects/template/**
```

This means folders such as `projects/<private_project>/` are private local research state and should not be committed to the harness repository.

## Pre-Publish Checks

From the repository root:

```bash
python -m py_compile $(find scripts -name '*.py' | sort)
python -m scripts.commands.projects.validate_project --project template --strict
python -m scripts.commands.release.smoke_test
python -m scripts.commands.release.privacy_audit
python -m scripts.commands.release.check_publishable
git check-ignore -v projects/<private_project>/state/agent_status.json
git status --short --ignored
```

Confirm that real project folders appear as ignored and `projects/template/`
remains visible. `scripts/commands/release/privacy_audit.py` scans publishable files for local
path markers, ignored private project names, and external reference workspace
names; `scripts/commands/release/check_publishable.py` runs that same privacy scan as part of the
publishable file-set gate.

## Create A Private GitHub Repository

With GitHub CLI:

```bash
git init
git add .
git commit -m "Initial research agent harness"
gh repo create <owner>/<repo> --private --source=. --remote=origin --push
```

Without GitHub CLI:

```bash
git init
git add .
git commit -m "Initial research agent harness"
git branch -M main
git remote add origin git@github.com:<owner>/<repo>.git
git push -u origin main
```

Before pushing, run:

```bash
git ls-files | grep '^projects/' | sort
```

The only project files listed should be under `projects/template/`.

## CI

The repository includes `.github/workflows/ci.yml`. It runs:

- Python script compilation
- template project validation
- harness smoke test, including file-state continuation and completion gates
- optional dashboard JavaScript syntax check
- publishable file-set check
