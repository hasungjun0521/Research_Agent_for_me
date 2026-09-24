# Workspace Profile

Use this skill when adapting the harness to a new user, lab, server, language,
or GPU cluster.

## Files

- Public template: `config/workspace_profile.example.json`
- Local override: `config/workspace_profile.local.json`

The local override is ignored by git. Keep private machine names, language
preferences, and lab GPU rules there instead of hard-coding them in prompts or
other workspace status tooling.

## Procedure

```bash
python -m scripts.commands.release.workspace_profile init-local
python -m scripts.commands.release.workspace_profile show --json
python -m scripts.commands.release.workspace_profile validate
```

Then edit only `config/workspace_profile.local.json` for:

- `display.summary_language`
- `display.top_summary_labels`
- `agent_output.preferred_language`
- `agent_runners.default_profile`
- `agent_runners.profiles`
- `gpu.max_user_gpus`
- `gpu.auto_order`
- `gpu.profiles`
- `gpu.commands`

Runner profiles are optional local commands for non-interactive agent execution.
They let `agent_orchestrator dispatch`, `agent_orchestrator parallel`, and
`agent_orchestrator run-prepared` use `--runner-profile <name>` instead of
embedding machine-specific commands in prompts or tracked files.

```json
{
  "agent_runners": {
    "default_profile": "codex_exec",
    "profiles": {
      "codex_exec": {
        "description": "Run prepared prompts through a non-interactive local runner.",
        "command": ["your-agent-cli", "--prompt-file", "{prompt_file}", "--project", "{project}"]
      }
    }
  }
}
```

## Guardrails

- Do not put secrets or credentials in the profile.
- Do not put interactive Claude/Codex TUI commands in runner profiles.
- Do not edit project `state/*.json` just to change a user preference.
- If GPU profile names change, run `python -m scripts.commands.release.workflow_audit` and a GPU
  scheduler dry run before launching jobs.
