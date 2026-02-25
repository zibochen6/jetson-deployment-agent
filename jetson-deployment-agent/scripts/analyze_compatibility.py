#!/usr/bin/env python3
"""Compare tutorial requirements against Jetson facts and a JP5/JP6 matrix."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze Jetson compatibility.")
    parser.add_argument("--facts", required=True, help="Path to facts JSON.")
    parser.add_argument("--requirements", required=True, help="Path to requirements JSON.")
    parser.add_argument("--matrix", required=True, help="Path to matrix JSON.")
    parser.add_argument("--output", required=True, help="Path to output analysis JSON.")
    return parser.parse_args()


def load_json(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def version_tuple(version: str) -> tuple[int, ...]:
    nums = [int(x) for x in re.findall(r"\d+", version)]
    return tuple(nums) if nums else (0,)


def compare_versions(left: str, right: str) -> int:
    a = list(version_tuple(left))
    b = list(version_tuple(right))
    size = max(len(a), len(b))
    a.extend([0] * (size - len(a)))
    b.extend([0] * (size - len(b)))
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def satisfies(installed: str, operator: str, required: str) -> bool:
    cmp_value = compare_versions(installed, required)
    if operator == "==":
        return cmp_value == 0
    if operator == ">=":
        return cmp_value >= 0
    if operator == "<=":
        return cmp_value <= 0
    if operator == ">":
        return cmp_value > 0
    if operator == "<":
        return cmp_value < 0
    if operator == "~=":
        return cmp_value >= 0
    return False


def infer_jetpack_series(facts: dict[str, Any]) -> str:
    series = str(facts.get("jetpack", {}).get("series", "")).strip()
    if series in {"5.x", "6.x"}:
        return series

    jp_version = str(facts.get("jetpack", {}).get("installed_version", ""))
    if jp_version.startswith("5"):
        return "5.x"
    if jp_version.startswith("6"):
        return "6.x"

    l4t_release = str(facts.get("l4t", {}).get("release", ""))
    if l4t_release.startswith("R35"):
        return "5.x"
    if l4t_release.startswith("R36"):
        return "6.x"
    return "unknown"


def major_to_series(version: str) -> str:
    if version.lower().endswith(".x"):
        major = version.split(".", 1)[0]
    else:
        major = version.split(".", 1)[0]
    if major == "5":
        return "5.x"
    if major == "6":
        return "6.x"
    return "unknown"


def find_ubuntu_version(facts: dict[str, Any]) -> str:
    pretty = str(facts.get("os", {}).get("pretty_name", ""))
    match = re.search(r"\b(\d{2}\.\d{2})\b", pretty)
    return match.group(1) if match else "unknown"


def get_installed_component_version(component: str, facts: dict[str, Any]) -> str:
    if component == "jetpack":
        return str(facts.get("jetpack", {}).get("installed_version", "unknown"))
    if component == "cuda":
        return str(facts.get("cuda", {}).get("version", "unknown"))
    if component == "python":
        return str(facts.get("python", {}).get("version", "unknown"))
    if component == "ubuntu":
        return find_ubuntu_version(facts)
    if component == "tensorrt":
        value = str(facts.get("tensorrt", {}).get("version", "unknown"))
        return value
    return "unknown"


def pick_supported_version(matrix: dict[str, Any], component: str, series: str) -> str:
    supported = matrix.get("component_support", {}).get(component, {}).get(series, [])
    if not supported:
        return ""
    return str(supported[-1])


def detect_required_models(hardware_requirements: list[str]) -> list[str]:
    known_models = [
        "jetson nano",
        "jetson xavier nx",
        "jetson agx xavier",
        "jetson orin nano",
        "jetson orin nx",
        "jetson agx orin",
        "jetson tx2",
    ]
    found: list[str] = []
    for line in hardware_requirements:
        lowered = line.lower()
        for model in known_models:
            if model in lowered and model not in found:
                found.append(model)
    return found


def component_range(matrix: dict[str, Any], series: str, component: str) -> tuple[str, str]:
    series_info = matrix.get("jetpack_series", {}).get(series, {})
    entry = series_info.get(component, {})
    return str(entry.get("min", "")), str(entry.get("max", ""))


def normalize_component(raw: str) -> str:
    lowered = raw.lower().replace(" ", "")
    if lowered in {"onnxruntime", "onnxruntime"}:
        return "onnxruntime"
    return lowered


def add_issue(issues: list[dict[str, Any]], **kwargs: Any) -> None:
    issues.append(kwargs)


def add_blocker(blocked: list[dict[str, Any]], **kwargs: Any) -> None:
    blocked.append(kwargs)


def unique_strings(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result


def make_action(
    action_id: str,
    summary: str,
    command: str,
    requires_sudo: bool,
    risk_level: str,
    rollback_hint: str,
    verify_command: str,
) -> dict[str, Any]:
    return {
        "id": action_id,
        "summary": summary,
        "command": command,
        "requires_sudo": requires_sudo,
        "risk_level": risk_level,
        "rollback_hint": rollback_hint,
        "verify_command": verify_command,
    }


def main() -> int:
    args = parse_args()
    facts = load_json(args.facts)
    requirements = load_json(args.requirements)
    matrix = load_json(args.matrix)

    facts_series = infer_jetpack_series(facts)
    facts_model = str(facts.get("device", {}).get("model", "unknown"))

    issues: list[dict[str, Any]] = []
    blocked_items: list[dict[str, Any]] = []
    ready_items: list[dict[str, Any]] = []
    alternatives: list[str] = []
    recommended_actions: list[dict[str, Any]] = []
    action_index = 1

    required_models = detect_required_models(requirements.get("hardware_requirements", []))
    if required_models:
        model_ok = any(model in facts_model.lower() for model in required_models)
        if not model_ok:
            add_blocker(
                blocked_items,
                component="hardware",
                message=f"Tutorial targets {required_models}, but device is '{facts_model}'.",
                required=required_models,
                installed=facts_model,
            )
            alternatives.append("Use a tutorial that targets the current Jetson model, or switch hardware.")
        else:
            ready_items.append(
                {
                    "component": "hardware",
                    "required": required_models,
                    "installed": facts_model,
                }
            )

    constraints = requirements.get("version_constraints", [])
    for raw_constraint in constraints:
        component = normalize_component(str(raw_constraint.get("component", "")))
        operator = str(raw_constraint.get("operator", "=="))
        required_version = str(raw_constraint.get("version", ""))
        evidence = str(raw_constraint.get("evidence", ""))
        installed_version = get_installed_component_version(component, facts)

        if component == "l4t":
            ready_items.append(
                {
                    "component": "l4t",
                    "required": f"{operator} {required_version}",
                    "installed": str(facts.get("l4t", {}).get("release", "unknown")),
                }
            )
            continue

        if component == "jetpack":
            required_series = major_to_series(required_version)
            facts_major = major_to_series(installed_version)

            if operator in {"==", ">="} and required_series != "unknown":
                if operator == "==" and facts_major != required_series:
                    add_blocker(
                        blocked_items,
                        component="jetpack",
                        message=f"JetPack major mismatch: requires {required_series}, found {facts_major}.",
                        required=f"{operator} {required_version}",
                        installed=installed_version,
                        evidence=evidence,
                    )
                    alternatives.append(matrix.get("alternatives", {}).get("jetpack_major_mismatch", "Use a compatible tutorial or reflash to matching major."))
                    recommended_actions.append(
                        make_action(
                            action_id=f"action-{action_index:03d}",
                            summary="Handle JetPack major mismatch manually.",
                            command="echo \"Manual action required: major JetPack mismatch detected. Review fallback or reflash path.\"",
                            requires_sudo=False,
                            risk_level="high",
                            rollback_hint="No state changed by this placeholder action.",
                            verify_command="echo \"Verify major compatibility decision is documented.\"",
                        )
                    )
                    action_index += 1
                    continue
                if operator == ">=" and compare_versions(facts_major.split(".")[0], required_series.split(".")[0]) < 0:
                    add_blocker(
                        blocked_items,
                        component="jetpack",
                        message=f"JetPack major too low: requires {required_series} or newer, found {facts_major}.",
                        required=f"{operator} {required_version}",
                        installed=installed_version,
                        evidence=evidence,
                    )
                    alternatives.append(matrix.get("alternatives", {}).get("jetpack_major_mismatch", "Use a compatible tutorial or reflash to matching major."))
                    recommended_actions.append(
                        make_action(
                            action_id=f"action-{action_index:03d}",
                            summary="Escalate JetPack major upgrade decision.",
                            command="echo \"Manual decision required: tutorial needs newer JetPack major.\"",
                            requires_sudo=False,
                            risk_level="high",
                            rollback_hint="No state changed by this placeholder action.",
                            verify_command="echo \"Verify upgrade or fallback decision is approved.\"",
                        )
                    )
                    action_index += 1
                    continue

            ready_items.append(
                {
                    "component": "jetpack",
                    "required": f"{operator} {required_version}",
                    "installed": installed_version,
                }
            )
            continue

        if component in {"cuda", "python", "ubuntu"}:
            if installed_version == "unknown":
                add_issue(
                    issues,
                    component=component,
                    severity="medium",
                    message=f"Installed {component} version is unknown; manual verification required.",
                    required=f"{operator} {required_version}",
                    installed=installed_version,
                    evidence=evidence,
                )
                alternatives.append(f"Collect {component} facts again and re-run compatibility analysis.")
                continue

            min_v, max_v = component_range(matrix, facts_series, component)
            if max_v and compare_versions(required_version, max_v) > 0 and operator in {"==", ">=", ">"}:
                add_blocker(
                    blocked_items,
                    component=component,
                    message=f"{component} requirement {operator} {required_version} exceeds {facts_series} range (max {max_v}).",
                    required=f"{operator} {required_version}",
                    installed=installed_version,
                    evidence=evidence,
                )
                alternatives.append(f"Use a {component} version within {facts_series} supported range ({min_v} to {max_v}).")
                recommended_actions.append(
                    make_action(
                        action_id=f"action-{action_index:03d}",
                        summary=f"Resolve unsupported {component} requirement.",
                        command=f"echo \"Manual action required: adjust {component} requirement to {facts_series} supported range.\"",
                        requires_sudo=True,
                        risk_level="high",
                        rollback_hint="No state changed by this placeholder action.",
                        verify_command=f"echo \"Verify {component} requirement now fits {facts_series} range.\"",
                    )
                )
                action_index += 1
                continue

            if satisfies(installed_version, operator, required_version):
                ready_items.append(
                    {
                        "component": component,
                        "required": f"{operator} {required_version}",
                        "installed": installed_version,
                    }
                )
            else:
                suggestion = ""
                requires_sudo = False
                risk_level = "medium"
                rollback_hint = "Remove or recreate the virtual environment if needed."
                verify_command = f"python3 - <<'PY'\nprint('verify {component} manually')\nPY"
                command = f"echo \"Adjust {component} to satisfy {operator} {required_version}\""

                if component == "python":
                    suggestion = "Use a project virtual environment and install compatible wheels."
                    command = "python3 -m venv .venv && . .venv/bin/activate && python3 -m pip install --upgrade pip"
                    verify_command = "python3 --version"
                if component == "cuda":
                    suggestion = f"Stay inside {facts_series} CUDA range and use JetPack-aligned CUDA packages."
                    command = "echo \"Adjust CUDA requirement to JetPack-compatible version; avoid cross-major upgrades.\""
                    risk_level = "high"
                    requires_sudo = True
                if component == "ubuntu":
                    suggestion = "Do not force unsupported Ubuntu version changes inside an existing JetPack image."
                    command = "echo \"Manual action required: Ubuntu baseline mismatch with tutorial.\""
                    risk_level = "high"
                    requires_sudo = True

                add_issue(
                    issues,
                    component=component,
                    severity=risk_level,
                    message=f"{component} does not satisfy requirement {operator} {required_version}.",
                    required=f"{operator} {required_version}",
                    installed=installed_version,
                    suggestion=suggestion,
                    evidence=evidence,
                )
                alternatives.append(suggestion or f"Adjust {component} requirement to match installed JetPack series.")
                recommended_actions.append(
                    make_action(
                        action_id=f"action-{action_index:03d}",
                        summary=f"Adjust {component} compatibility.",
                        command=command,
                        requires_sudo=requires_sudo,
                        risk_level=risk_level,
                        rollback_hint=rollback_hint,
                        verify_command=verify_command,
                    )
                )
                action_index += 1
            continue

        if component in {"pytorch", "onnxruntime"}:
            supported = matrix.get("component_support", {}).get(component, {}).get(facts_series, [])
            if not supported:
                add_issue(
                    issues,
                    component=component,
                    severity="medium",
                    message=f"No support map found for {component} on {facts_series}.",
                    required=f"{operator} {required_version}",
                    installed="unknown",
                    evidence=evidence,
                )
                alternatives.append(f"Manually validate {component} package availability for {facts_series}.")
                continue

            required_prefix = ".".join(required_version.split(".")[:2]) if "." in required_version else required_version
            supported_ok = any(required_prefix == s or required_version.startswith(s) for s in supported)

            if supported_ok:
                ready_items.append(
                    {
                        "component": component,
                        "required": f"{operator} {required_version}",
                        "installed": f"compatible with {facts_series}",
                    }
                )
            else:
                alternative = pick_supported_version(matrix, component, facts_series)
                suggestion = (
                    f"Pin {component} to {alternative} for {facts_series}."
                    if alternative
                    else f"Pin {component} to a tested version for {facts_series}."
                )
                add_issue(
                    issues,
                    component=component,
                    severity="medium",
                    message=f"{component} version {required_version} is not in tested list for {facts_series}.",
                    required=f"{operator} {required_version}",
                    installed=f"supported list: {supported}",
                    suggestion=suggestion,
                    evidence=evidence,
                )
                alternatives.append(suggestion)
                install_cmd = (
                    f"python3 -m pip install {component}=={alternative}"
                    if alternative
                    else f"echo \"Select a tested {component} version for {facts_series}.\""
                )
                recommended_actions.append(
                    make_action(
                        action_id=f"action-{action_index:03d}",
                        summary=f"Pin {component} to a {facts_series} compatible version.",
                        command=install_cmd,
                        requires_sudo=False,
                        risk_level="medium",
                        rollback_hint=f"Reinstall previous {component} version if regression is observed.",
                        verify_command=f"python3 - <<'PY'\nimport importlib\nm=importlib.import_module('{component}')\nprint(getattr(m, '__version__', 'unknown'))\nPY",
                    )
                )
                action_index += 1
            continue

        if component == "tensorrt":
            required_major = required_version.split(".", 1)[0]
            expected_major = str(matrix.get("jetpack_series", {}).get(facts_series, {}).get("tensorrt_major", ""))
            if expected_major and required_major != expected_major:
                add_blocker(
                    blocked_items,
                    component="tensorrt",
                    message=f"TensorRT major {required_major} is incompatible with {facts_series} expected major {expected_major}.",
                    required=f"{operator} {required_version}",
                    installed=f"expected major {expected_major}",
                    evidence=evidence,
                )
                alternatives.append(f"Use TensorRT major {expected_major} for {facts_series}.")
                recommended_actions.append(
                    make_action(
                        action_id=f"action-{action_index:03d}",
                        summary="Resolve TensorRT major mismatch.",
                        command=f"echo \"Use TensorRT major {expected_major} to match {facts_series}.\"",
                        requires_sudo=True,
                        risk_level="high",
                        rollback_hint="No state changed by this placeholder action.",
                        verify_command="echo \"Verify TensorRT major compatibility.\"",
                    )
                )
                action_index += 1
            else:
                ready_items.append(
                    {
                        "component": "tensorrt",
                        "required": f"{operator} {required_version}",
                        "installed": f"compatible major for {facts_series}",
                    }
                )
            continue

        add_issue(
            issues,
            component=component,
            severity="low",
            message=f"Unknown component '{component}'. Manual review required.",
            required=f"{operator} {required_version}",
            installed="unknown",
            evidence=evidence,
        )
        alternatives.append(f"Manually map unknown component '{component}' to Jetson-compatible packages.")

    alternatives = unique_strings([x for x in alternatives if x])

    if blocked_items:
        overall_status = "blocked"
    elif issues:
        overall_status = "needs-adjustments"
    else:
        overall_status = "ready"

    payload = {
        "overall_status": overall_status,
        "facts_series": facts_series,
        "issues": issues,
        "alternatives": alternatives,
        "blocked_items": blocked_items,
        "ready_items": ready_items,
        "recommended_actions": recommended_actions,
    }

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
