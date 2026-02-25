#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  execute_guided_plan.sh --plan <deploy-plan.json> --log-file <execution-log.json> --approvals-file <approvals.json>

The script executes only approved medium/high-risk steps.
EOF
}

die() {
  echo "[execute-guided-plan][ERROR] $*" >&2
  exit 1
}

PLAN=""
LOG_FILE=""
APPROVALS_FILE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --plan)
      PLAN="${2:-}"
      shift 2
      ;;
    --log-file)
      LOG_FILE="${2:-}"
      shift 2
      ;;
    --approvals-file)
      APPROVALS_FILE="${2:-}"
      shift 2
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      die "Unknown argument: $1"
      ;;
  esac
done

if [[ -z "$PLAN" || -z "$LOG_FILE" || -z "$APPROVALS_FILE" ]]; then
  usage
  die "Missing required arguments."
fi

python3 - "$PLAN" "$LOG_FILE" "$APPROVALS_FILE" <<'PY'
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_approvals(path):
    if not path.exists():
        return {
            "approve_all_low": True,
            "approve_all_medium": False,
            "approve_all_high": False,
            "approved_step_ids": [],
        }

    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return {
            "approve_all_low": True,
            "approve_all_medium": False,
            "approve_all_high": False,
            "approved_step_ids": [],
        }

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        ids = [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]
        return {
            "approve_all_low": True,
            "approve_all_medium": False,
            "approve_all_high": False,
            "approved_step_ids": ids,
        }

    if isinstance(data, list):
        return {
            "approve_all_low": True,
            "approve_all_medium": False,
            "approve_all_high": False,
            "approved_step_ids": [str(x) for x in data],
        }

    if isinstance(data, dict):
        return {
            "approve_all_low": bool(data.get("approve_all_low", True)),
            "approve_all_medium": bool(data.get("approve_all_medium", False)),
            "approve_all_high": bool(data.get("approve_all_high", False)),
            "approved_step_ids": [str(x) for x in data.get("approved_step_ids", [])],
        }

    return {
        "approve_all_low": True,
        "approve_all_medium": False,
        "approve_all_high": False,
        "approved_step_ids": [],
    }


def should_run_step(step, approvals):
    step_id = str(step.get("id", ""))
    risk = str(step.get("risk_level", "medium")).lower()
    approved_ids = set(approvals.get("approved_step_ids", []))

    if risk == "low":
        if approvals.get("approve_all_low", True):
            return True, "auto-approved-low"
        return step_id in approved_ids, "explicit-low"

    if risk == "medium":
        if approvals.get("approve_all_medium", False):
            return True, "approve-all-medium"
        if step_id in approved_ids:
            return True, "explicit-medium"
        return False, "missing-medium-approval"

    if risk == "high":
        if approvals.get("approve_all_high", False):
            return True, "approve-all-high"
        if step_id in approved_ids:
            return True, "explicit-high"
        return False, "missing-high-approval"

    if step_id in approved_ids:
        return True, "explicit-unknown-risk"
    return False, "unrecognized-risk-needs-approval"


def run_shell(command):
    shell_executable = "/bin/bash" if Path("/bin/bash").exists() else None
    return subprocess.run(
        command,
        shell=True,
        executable=shell_executable,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    plan_path = Path(sys.argv[1])
    log_path = Path(sys.argv[2])
    approvals_path = Path(sys.argv[3])

    plan = load_json(plan_path)
    approvals = load_approvals(approvals_path)
    steps = plan.get("steps", [])
    if not isinstance(steps, list):
        raise ValueError("Plan field 'steps' must be a list.")

    results = []
    approval_log = []

    executed = 0
    skipped = 0
    failed = 0

    for step in steps:
        step_id = str(step.get("id", ""))
        command = str(step.get("command", ""))
        verify_command = str(step.get("verify_command", "")).strip()
        requires_sudo = bool(step.get("requires_sudo", False))
        risk_level = str(step.get("risk_level", "medium")).lower()

        approved, reason = should_run_step(step, approvals)
        approval_log.append(
            {
                "step_id": step_id,
                "risk_level": risk_level,
                "requires_sudo": requires_sudo,
                "approved": approved,
                "decision_reason": reason,
            }
        )

        if not approved:
            skipped += 1
            results.append(
                {
                    "step_id": step_id,
                    "status": "skipped",
                    "reason": reason,
                    "command": command,
                }
            )
            continue

        started_at = datetime.now(timezone.utc).isoformat()
        run_result = run_shell(command)
        executed += 1

        entry = {
            "step_id": step_id,
            "status": "success" if run_result.returncode == 0 else "failed",
            "started_at": started_at,
            "ended_at": datetime.now(timezone.utc).isoformat(),
            "command": command,
            "return_code": run_result.returncode,
            "stdout": run_result.stdout,
            "stderr": run_result.stderr,
        }

        if run_result.returncode != 0:
            failed += 1
            results.append(entry)
            continue

        if verify_command:
            verify_result = run_shell(verify_command)
            entry["verify_command"] = verify_command
            entry["verify_return_code"] = verify_result.returncode
            entry["verify_stdout"] = verify_result.stdout
            entry["verify_stderr"] = verify_result.stderr
            if verify_result.returncode != 0:
                entry["status"] = "failed"
                failed += 1

        results.append(entry)

    summary = {
        "mode": plan.get("mode", "guided"),
        "overall_status": plan.get("overall_status", "unknown"),
        "executed_steps": executed,
        "skipped_steps": skipped,
        "failed_steps": failed,
        "total_steps": len(steps),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    payload = {
        "summary": summary,
        "approval_log": approval_log,
        "results": results,
    }

    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(summary, indent=2))
    return 1 if failed > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
PY
