# JetPack Compatibility Matrix (JP5.x and JP6.x)

## Scope

Use this matrix to evaluate whether tutorial requirements can run on the current Jetson base image.
Treat this as decision guidance for this skill, not as a replacement for vendor release notes.

## Compatibility Table

| Area | JetPack 5.x (L4T R35.x) | JetPack 6.x (L4T R36.x) | Planning Rule |
| --- | --- | --- | --- |
| Ubuntu baseline | 20.04 | 22.04 | Do not apply Ubuntu 22.04-only packages to JP5.x. |
| CUDA family | 11.x | 12.x | Treat CUDA 12-only requirements as blocked on JP5.x. |
| Python baseline | 3.8 to 3.10 | 3.10 to 3.12 | Prefer venv and target range inside the series range. |
| TensorRT family | 8.x | 10.x | Use series-specific TensorRT packages. |
| Typical PyTorch wheel track | 2.0 to 2.1 | 2.3 to 2.5 | Downgrade or upgrade model stack by series. |
| ONNX Runtime track | 1.16 to 1.17 | 1.18 to 1.20 | Pin to per-series tested versions. |

## Decision Rules

1. Read JetPack series from facts (`5.x` or `6.x`) before selecting package versions.
2. Keep CUDA and TensorRT aligned with JetPack series.
3. If tutorial requires a major stack from the other series, mark as `blocked` unless a documented fallback exists.
4. Prefer compatibility adjustments in user space (venv and package pinning) before system-level changes.

## High-Risk Indicators

- Tutorial requires JetPack major version different from installed major version.
- Tutorial requires CUDA 12.x on JP5.x or CUDA 11.x-specific binaries on JP6.x.
- Tutorial assumes Ubuntu release features not present in current JetPack series.

