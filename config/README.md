# Workspace Profile

`workspace_profile.example.json` is the public template for machine-local
preferences. Copy it to `workspace_profile.local.json` and edit that local file
for a specific user, lab, GPU cluster, or preferred agent/report language.

`workspace_profile.local.json` is ignored by git. Do not put secrets in either
file.

The public example keeps GPU execution disabled and uses a conservative GPU
cap. Enable GPU execution and set the real cap, profiles, and scheduler
commands only in `workspace_profile.local.json`.

Agent usage-limit checks are also local opt-in. If your agent CLI provides an
official non-interactive JSON status command, put its argv list in
`agent_limits.status_command` inside `workspace_profile.local.json`. The harness
does not drive an interactive Codex or Claude TUI to type `status`.

External agent runner profiles are local opt-in. Put non-interactive runner
commands under `agent_runners.profiles.<name>.command` in
`workspace_profile.local.json`, then set `agent_runners.default_profile` or pass
the profile name to the orchestrator. Runner command arrays can use
`{prompt_file}`, `{project}`, `{command_id}`, and `{agent}` placeholders.

Example local shape:

```json
{
  "agent_runners": {
    "default_profile": "codex_exec",
    "profiles": {
      "codex_exec": {
        "description": "Run a prepared prompt through a non-interactive agent command.",
        "command": ["your-agent-cli", "--prompt-file", "{prompt_file}", "--project", "{project}"]
      },
      "claude_print": {
        "description": "Example placeholder for a non-interactive Claude-compatible runner.",
        "command": ["your-claude-compatible-cli", "--file", "{prompt_file}"]
      }
    }
  }
}
```

Do not configure an interactive TUI command as a runner profile. The runner must
return control to the harness and write useful progress to project files.

```bash
python -m scripts.commands.release.workspace_profile init-local
python -m scripts.commands.release.workspace_profile show --json
python -m scripts.commands.review.progress_checkpoint check-limits --project <project> --agent <agent> --summary "<session summary>"
```
