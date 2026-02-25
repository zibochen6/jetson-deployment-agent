# Tutorial Parsing Rules

## Goal

Extract normalized deployment requirements from tutorial links (Wikipedia-like pages and generic docs).

## Input Sources

1. HTTP/HTTPS pages (HTML content).
2. Local markdown or text files.
3. Local HTML fixtures.

## Extraction Heuristics

1. Convert source into plain text while removing script/style blocks.
2. Split into meaningful lines and retain bullet-like requirement lines.
3. Detect hardware constraints using keywords:
- `Jetson`, `camera`, `USB`, `CSI`, `RAM`, `memory`, `storage`, `disk`
4. Detect software constraints using keywords:
- `JetPack`, `L4T`, `CUDA`, `Python`, `TensorRT`, `PyTorch`, `ONNX Runtime`, `Ubuntu`
5. Detect version constraints with operators:
- `>=`, `<=`, `==`, `>`, `<`, `~=`

## Output Normalization

Always output:
- `source_url`
- `hardware_requirements` (list of strings)
- `software_requirements` (list of strings)
- `version_constraints` (list of objects with `component`, `operator`, `version`, `evidence`)
- `notes` (list of parser notes and assumptions)
- `confidence` (0.0 to 1.0)

## Confidence Guidance

1. Increase confidence when multiple explicit version statements are found.
2. Lower confidence when only vague phrases are present (for example, "latest dependencies").
3. Mark confidence below `0.50` as requiring human confirmation.

## Domain Guarding

When `--allow-domains` is provided:
1. Enforce host allowlist before fetching.
2. Reject non-allowlisted domains with explicit error messages.

