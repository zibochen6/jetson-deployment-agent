# Dependency Mapping Rules

## Objective

Map tutorial dependencies to Jetson-safe package channels with consistent conflict handling.

## Channel Selection Priority

1. `apt`: Base OS libraries, CUDA-adjacent runtime packages, system tools.
2. `pip` in `venv`: Python application dependencies and framework wheels.
3. `conda`: Use only when user environment already depends on conda.

## Mapping Table

| Requirement type | Preferred channel | Reason |
| --- | --- | --- |
| `build-essential`, `cmake`, `git`, `ffmpeg` | `apt` | System packages should remain OS-managed. |
| Python runtime libraries (`fastapi`, `numpy`) | `pip` in venv | Keeps project dependencies isolated. |
| CUDA toolkit package references | `apt` (series-aware) | Must stay aligned to JetPack image. |
| TensorRT Python bindings | series-aware package source | Must match installed TensorRT family. |
| Tutorial uses conda explicitly | existing conda env | Avoid mixed package ownership unless required. |

## Conflict Resolution Priority

1. Preserve JetPack-aligned system libraries.
2. Adjust Python package versions to match JetPack matrix.
3. Replace tutorial package names with Jetson-equivalent package names.
4. Defer unsupported major requirements as blockers with alternatives.

## Non-Overwrite Rules

1. Do not overwrite existing shell startup files by default.
2. Append PATH updates only if not already present.
3. Do not remove user-installed packages unless explicitly requested.

## Sudo Policy

1. Mark `apt` and system-file operations as `requires_sudo=true`.
2. Keep pip installs in venv as `requires_sudo=false`.
3. If `allow-sudo=no`, convert privileged actions to manual prerequisites.

