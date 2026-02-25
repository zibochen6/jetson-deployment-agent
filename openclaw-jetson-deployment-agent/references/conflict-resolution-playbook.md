# Conflict Resolution Playbook

## Purpose

Resolve deployment mismatches safely without destabilizing Jetson systems.

## Decision Ladder

1. Keep installed JetPack major series unchanged unless user explicitly approves reflash.
2. Adapt tutorial package versions to current series-compatible alternatives.
3. Prefer project-local changes (venv and package pins) before OS-level modifications.
4. If requirement is fundamentally unsupported on current series, mark as `blocked`.

## Common Conflict Patterns

| Conflict | Preferred action | Risk level |
| --- | --- | --- |
| Tutorial requires JetPack 6.x but device is 5.x | Offer JP5-compatible fallback or reflash option | High |
| Tutorial requires CUDA 12.x on JP5.x | Mark blocked; recommend series upgrade path | High |
| Python requirement is above current local interpreter | Create venv with supported interpreter in series range | Medium |
| PyTorch version not available for series | Pin nearest tested version for current series | Medium |
| Missing package manager in tutorial assumptions | Map to available manager (`apt`/`pip`) | Low |

## Rollback-Safe Practices

1. Keep every generated step with a `rollback_hint`.
2. Use non-destructive verification commands after each critical step.
3. Log skipped and failed steps separately from successful steps.
4. Do not delete existing environments by default.

## Required Reporting

For each adjustment, report:
1. Original requirement.
2. Applied alternative.
3. Why the change is needed for JP5.x or JP6.x compatibility.
4. Validation or verification command.

