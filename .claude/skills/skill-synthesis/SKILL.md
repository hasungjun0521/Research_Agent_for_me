---
name: skill-synthesis
description: Allows the agent to autonomously synthesize and register new skills based on recurring mistakes or user corrections.
---

# Skill Synthesis

This skill empowers the agent to evolve by identifying procedural gaps and codifying them into new harness skills.

## Usage

When you identify a pattern of failure or receive a "always do X" instruction:
1. Follow the `prompts/skills/skill_synthesis.md` runbook.
2. Create the necessary files across all 7 registration surfaces (the release
   gate checks every one).
3. Run `project_index refresh`, then verify with `workflow_audit` and
   `verify_harness`.
