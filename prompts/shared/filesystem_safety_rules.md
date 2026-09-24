# Filesystem Safety Rules

These rules are non-negotiable for every agent, script-assisted workflow, and manual continuation prompt.

## Active Folder Boundary

- For research work, the active folder is the current project root: `projects/<name>/`.
- For harness maintenance, the active folder is the repository root, and only files explicitly required by the user request are in scope.
- Never delete, move, overwrite, or clean up any directory outside the active folder.
- Never modify sibling projects, parent directories, home directories, shared datasets, external code trees, or system paths unless the user explicitly changes the active folder in a new request.

## Destructive Command Ban

Do not run destructive directory commands against paths outside the active folder. This includes:

- `rm -rf`, `rmdir`, `find ... -delete`
- `git clean -fd`, `git clean -fdx`
- `rsync --delete`
- `shutil.rmtree`, `Path.rmdir`, recursive delete scripts
- moving a directory away from its original path as a substitute for deletion

If cleanup is required, prefer deleting only known generated files inside the active project folder. If a directory deletion is truly necessary inside the active folder, first list the exact target path and confirm it is under the active folder.

## Path Checks Before Risky Operations

Before any command that could remove or overwrite files:

1. Check the current working directory.
2. Resolve the target path.
3. Confirm the resolved target starts with the active folder path.
4. If the target is outside the active folder, stop and ask the user instead of running the command.

## Experiment Cleanup

For server experiments, cleanup means:

- synchronize SLURM outcomes with `scripts/commands/experiments/gpu_monitor.py`,
- stop only jobs you own when cancellation is explicitly needed,
- update `run_state.json` and `agent_status.json`.

It does not mean deleting external datasets, checkpoints, cloned repositories, or folders outside the active project.
