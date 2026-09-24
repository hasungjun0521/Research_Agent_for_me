# Skill Synthesis (Self-Evolution Protocol)

## Purpose
This skill is used when the agent (you) identifies a recurring mistake, receives a procedural correction from the user, or discovers a more efficient way to handle a task. It allows you to transform these insights into a permanent, structured operating procedure (SOP) called a "Skill" in this harness.

## Trigger Conditions
- You repeat the same lint, compile, or logic error 2+ times.
- The user provides explicit procedural feedback (e.g., "Always do X when Y").
- You find a workaround for a systemic issue that should be documented as the official path.

## Execution Steps

1. **Root Cause Analysis (RCA):**
   - Identify why the mistake occurred or why the new procedure is necessary.
   - Determine if the issue is a lack of procedural knowledge (SOP) or a simple typo. Proceed if it's an SOP issue.

2. **Define the New Skill:**
   - **Name:** Concise and kebab-case (e.g., `vllm-path-setup`).
   - **Purpose:** One sentence describing what it solves.
   - **Checklist:** 3-5 concrete, actionable steps. Avoid vague advice.

3. **Register Across the 7 Surfaces:**
   You MUST update/create the following 7 surfaces to harden the skill into the
   harness. The release gate (`workflow_audit`) checks every one of them, so a
   missing surface fails the gate.
   - **Surface 1: Runbook:** Create `prompts/skills/<new_skill_name>.md`.
   - **Surface 2: Agent Tool:** Create `.claude/skills/<new_skill_name_kebab>/SKILL.md`. Use the standard tool format with frontmatter `name:` (kebab, matching the directory), `description:`, and instructions.
   - **Surface 3: Runbook Listing:** Add the skill to `prompts/skills/README.md`.
   - **Surface 4: Usage Mapping:** Add a mapping rule to `prompts/shared/skill_usage.md` explaining when to use it.
   - **Surface 5: Skill Documentation:** Add a row to `docs/installed_agent_skills.md` (and, for a CLI-backed skill, the wraps column).
   - **Surface 6: Audit Registry:** Add the runbook `.md` filename to the skill list in `scripts/commands/release/workflow_audit.py` (the `for skill_name in (...)` tuple, kept alphabetical).
   - **Surface 7: README Mention:** Add the kebab skill name to the Agent Compatibility skill list in the root `README.md` (the `workflow_audit` `.claude/skills` check requires every skill dir to be named there).

4. **Validation:**
   - Run `python -m scripts.commands.projects.project_index refresh` so the new files appear in `project.yaml`'s generated inventory (otherwise `project_index check` and the release gate fail).
   - Run `python -m scripts.commands.release.workflow_audit` to confirm the skill is correctly wired across all surfaces.
   - Run `python -m scripts.commands.release.verify_harness --project template --skip-paper-build` for the full gate before claiming done.
   - Mention the new skill creation in your session summary.
