---
name: openclaw-jetson-deployment-agent
description: Analyze and automate NVIDIA Jetson deployment from tutorial or wiki links with JetPack 5.x and 6.x compatibility checks, dependency mapping, adjusted command generation, and guided execution safety gates. Use when OpenClaw users need Jetson hardware or software validation, conflict resolution, and reproducible deployment steps.
metadata: {"openclaw":{"userInvocable":true,"os":["linux","darwin","win32"],"requires":{"anyBins":["python3","python"]},"homepage":"https://openclaw.ai/docs/skills"}}
---

# OpenClaw Jetson Deployment Agent

## Overview

Use this skill to turn an external deployment tutorial into a Jetson-safe, version-aware deployment workflow.
Prioritize equal support for JetPack 5.x and 6.x, with explicit conflict reporting, alternatives, and guided execution gates.
Use `{baseDir}` when referencing files in this skill so commands work from any OpenClaw working directory.

## Runtime Prerequisites

1. Require Python (`python3` or `python`) for analysis scripts.
2. Require shell execution support for `.sh` scripts.
3. On Windows without native `bash`, run shell steps with `wsl bash`.

## Workflow Decision Tree

1. Receive tutorial URL and target Jetson access details.
2. Parse requirements from the tutorial.
3. Collect device facts from local or remote Jetson.
4. Compare tutorial requirements against JetPack matrix.
5. Branch by status:
- `ready`: generate and optionally execute guided plan.
- `needs-adjustments`: generate adjusted commands and alternatives.
- `blocked`: stop execution, report blockers and required platform changes.
6. Execute only approved steps for medium/high risk actions.
7. Emit final change log and verification results.

## Input Contract

Require the following inputs before execution:
- Tutorial source: URL or local tutorial file.
- Jetson target: local mode or SSH tuple (`host`, `user`, optional `port`, optional `identity`).
- Output locations for facts, requirements, analysis, and plan JSON files.
- Safety options: `allow-sudo` and guided approvals file.

Use these bundled resources:
- `{baseDir}/scripts/collect_jetson_facts.sh`
- `{baseDir}/scripts/extract_tutorial_requirements.py`
- `{baseDir}/scripts/analyze_compatibility.py`
- `{baseDir}/scripts/generate_deploy_plan.py`
- `{baseDir}/scripts/execute_guided_plan.sh`
- `{baseDir}/references/jetpack_compatibility_matrix.json`
- `{baseDir}/references/jetpack-compatibility-matrix.md`
- `{baseDir}/references/dependency-mapping-rules.md`
- `{baseDir}/references/tutorial-parsing-rules.md`
- `{baseDir}/references/conflict-resolution-playbook.md`

## Step 1: Parse Tutorial Requirements

1. Run:
```bash
python3 "{baseDir}/scripts/extract_tutorial_requirements.py" \
  --url "<tutorial-url-or-file>" \
  --output "<requirements.json>" \
  --timeout 20
```
If only `python` exists:
```bash
python "{baseDir}/scripts/extract_tutorial_requirements.py" \
  --url "<tutorial-url-or-file>" \
  --output "<requirements.json>" \
  --timeout 20
```
2. If domain restrictions are needed, pass `--allow-domains "wikipedia.org,docs.nvidia.com"`.
3. Confirm output includes:
- `source_url`
- `hardware_requirements`
- `software_requirements`
- `version_constraints`
- `notes`
- `confidence`
4. If confidence is below `0.50`, treat extraction as uncertain and request user confirmation.

## Step 2: Collect Jetson Facts

1. Local collection:
```bash
bash "{baseDir}/scripts/collect_jetson_facts.sh" --local --output "<facts.json>"
```
2. Remote collection:
```bash
bash "{baseDir}/scripts/collect_jetson_facts.sh" \
  --host "<ip-or-host>" \
  --user "<ssh-user>" \
  --port 22 \
  --output "<facts.json>"
```
If Windows requires WSL:
```bash
wsl bash "{baseDir}/scripts/collect_jetson_facts.sh" --local --output "<facts.json>"
```
3. Confirm output includes:
- `device`
- `os`
- `jetpack`
- `l4t`
- `cuda`
- `python`
- `memory`
- `storage`
- `package_managers`

## Step 3: Compatibility Analysis (JP5.x + JP6.x)

1. Run:
```bash
python3 "{baseDir}/scripts/analyze_compatibility.py" \
  --facts "<facts.json>" \
  --requirements "<requirements.json>" \
  --matrix "{baseDir}/references/jetpack_compatibility_matrix.json" \
  --output "<analysis.json>"
```
2. Read status and branch:
- `overall_status=ready`: continue.
- `overall_status=needs-adjustments`: continue with alternatives.
- `overall_status=blocked`: stop execution and escalate with blockers.
3. Keep detailed lists in the report:
- `issues`
- `alternatives`
- `blocked_items`
- `ready_items`

## Step 4: Generate Adjusted Commands

1. Generate plan:
```bash
python3 "{baseDir}/scripts/generate_deploy_plan.py" \
  --analysis "<analysis.json>" \
  --allow-sudo yes \
  --mode guided \
  --output "<deploy-plan.json>"
```
2. Use `--allow-sudo no` when user disallows privileged actions.
3. Enforce plan schema per step:
- `id`
- `command`
- `requires_sudo`
- `risk_level`
- `rollback_hint`
- `verify_command`
4. If analysis is blocked, generate plan with only explanatory/manual steps.

## Step 5: Guided Execution and Verification

1. Execute plan:
```bash
bash "{baseDir}/scripts/execute_guided_plan.sh" \
  --plan "<deploy-plan.json>" \
  --approvals-file "<approvals.json>" \
  --log-file "<execution-log.json>"
```
2. Require explicit approval for high-risk steps.
3. Skip unapproved critical steps and report them.
4. Run per-step `verify_command` when primary command succeeds.
5. Summarize executed, skipped, failed, and verified counts.

## Safety Rules and Non-Overwrite Policy

1. Ask for confirmation before:
- Reflash/reimage recommendations.
- Commands that modify system package state.
- Any step marked `risk_level=high`.
2. Avoid overwriting existing system config files unless user explicitly requests it.
3. Keep a change log of every adjusted or substituted command.
4. Prefer reversible operations:
- Virtual environments over global pip installs.
- Package pinning over major upgrades.
5. Never silently escalate privileges; honor `allow-sudo`.

## Output Format and Change Log

Return:
1. Compatibility summary:
- target Jetson facts
- tutorial requirements
- compatibility status
2. Action artifacts:
- `requirements.json`
- `facts.json`
- `analysis.json`
- `deploy-plan.json`
- `execution-log.json` (if executed)
3. Change log:
- original requirement
- applied adjustment
- rationale
- rollback hint
