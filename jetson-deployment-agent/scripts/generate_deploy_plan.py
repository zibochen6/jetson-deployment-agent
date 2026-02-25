#!/usr/bin/env python3
"""Generate an executable deployment plan from compatibility analysis."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Jetson deployment plan JSON.")
    parser.add_argument("--analysis", required=True, help="Path to analysis JSON.")
    parser.add_argument(
        "--allow-sudo",
        required=True,
        choices=["yes", "no"],
        help="Whether privileged steps are allowed.",
    )
    parser.add_argument(
        "--mode",
        required=True,
        choices=["plan", "guided"],
        help="Plan-only output or guided execution plan.",
    )
    parser.add_argument("--output", required=True, help="Output plan JSON path.")
    return parser.parse_args()


def load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build_preflight_step(step_id: str) -> dict[str, Any]:
    return {
        "id": step_id,
        "command": "echo \"Review available disk, memory, and network connectivity before deployment.\"",
        "requires_sudo": False,
        "risk_level": "low",
        "rollback_hint": "No rollback needed for preflight review.",
        "verify_command": "echo \"Preflight checklist reviewed.\"",
    }


def ensure_step_shape(step: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(step.get("id", "")),
        "command": str(step.get("command", "echo \"No command provided\"")),
        "requires_sudo": bool(step.get("requires_sudo", False)),
        "risk_level": str(step.get("risk_level", "medium")),
        "rollback_hint": str(step.get("rollback_hint", "Document rollback before execution.")),
        "verify_command": str(step.get("verify_command", "echo \"No verify command provided\"")),
    }


def main() -> int:
    args = parse_args()
    analysis = load_json(args.analysis)

    steps: list[dict[str, Any]] = []
    manual_prerequisites: list[dict[str, Any]] = []

    step_counter = 1
    steps.append(build_preflight_step(f"step-{step_counter:03d}"))
    step_counter += 1

    actions = analysis.get("recommended_actions", [])
    if not isinstance(actions, list):
        actions = []

    if not actions:
        status = analysis.get("overall_status", "unknown")
        if status == "blocked":
            actions = [
                {
                    "id": "action-blocked",
                    "summary": "Deployment is blocked by compatibility checks.",
                    "command": "echo \"Deployment blocked. Review analysis alternatives and blockers.\"",
                    "requires_sudo": False,
                    "risk_level": "high",
                    "rollback_hint": "No system changes have been made.",
                    "verify_command": "echo \"Blockers acknowledged.\"",
                }
            ]
        else:
            actions = [
                {
                    "id": "action-ready",
                    "summary": "No compatibility actions are required.",
                    "command": "echo \"Compatibility check passed. Continue with project-specific install commands.\"",
                    "requires_sudo": False,
                    "risk_level": "low",
                    "rollback_hint": "No rollback needed.",
                    "verify_command": "echo \"Compatibility-ready state confirmed.\"",
                }
            ]

    for raw_action in actions:
        action = ensure_step_shape(raw_action)
        action["id"] = f"step-{step_counter:03d}"
        step_counter += 1

        if args.allow_sudo == "no" and action["requires_sudo"]:
            manual_prerequisites.append(
                {
                    "id": action["id"],
                    "original_command": action["command"],
                    "reason": "allow-sudo=no",
                }
            )
            action["command"] = f"echo \"Manual sudo prerequisite: {action['command']}\""
            action["requires_sudo"] = False
            action["risk_level"] = "high"
            action["rollback_hint"] = "No command executed because sudo is disabled."
            action["verify_command"] = "echo \"Manual prerequisite recorded.\""

        if args.mode == "guided" and action["risk_level"] in {"medium", "high"}:
            action["approval_required"] = True
        else:
            action["approval_required"] = False

        steps.append(action)

    payload = {
        "mode": args.mode,
        "allow_sudo": args.allow_sudo,
        "overall_status": analysis.get("overall_status", "unknown"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "steps": steps,
        "manual_prerequisites": manual_prerequisites,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
