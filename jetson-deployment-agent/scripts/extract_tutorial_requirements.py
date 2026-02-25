#!/usr/bin/env python3
"""Parse tutorial content into normalized Jetson deployment requirements JSON."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen


class PlainTextHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._ignore_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() in {"script", "style"}:
            self._ignore_depth += 1
        if tag.lower() in {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr"}:
            self._parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style"} and self._ignore_depth > 0:
            self._ignore_depth -= 1
        if tag.lower() in {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "br", "tr"}:
            self._parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._ignore_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        return "".join(self._parts)


@dataclass(frozen=True)
class Constraint:
    component: str
    operator: str
    version: str
    evidence: str


COMPONENT_ALIASES = {
    "onnx runtime": "onnxruntime",
    "onnxruntime": "onnxruntime",
    "tensorrt": "tensorrt",
    "pytorch": "pytorch",
    "jetpack": "jetpack",
    "l4t": "l4t",
    "cuda": "cuda",
    "python": "python",
    "ubuntu": "ubuntu",
}

HARDWARE_KEYWORDS = (
    "jetson",
    "camera",
    "usb",
    "csi",
    "ram",
    "memory",
    "disk",
    "storage",
    "gpu",
)

SOFTWARE_KEYWORDS = (
    "jetpack",
    "l4t",
    "cuda",
    "python",
    "pytorch",
    "tensorrt",
    "onnx",
    "ubuntu",
)

CONSTRAINT_RE = re.compile(
    r"(?i)\b(jetpack|l4t|cuda|python|ubuntu|pytorch|tensorrt|onnx\s*runtime|onnxruntime)\b"
    r"(?:\s*(>=|<=|==|~=|>|<))?"
    r"(?:\s*(?:version|v)?)?"
    r"\s*([0-9]+(?:\.[0-9]+){0,2}|[0-9]+\.x)"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Extract requirements from tutorial content.")
    parser.add_argument("--url", required=True, help="Tutorial URL or local path.")
    parser.add_argument("--output", required=True, help="Output JSON file path.")
    parser.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="HTTP timeout seconds (default: 20).",
    )
    parser.add_argument(
        "--allow-domains",
        default="",
        help="Comma-separated domain allowlist for HTTP URLs.",
    )
    return parser.parse_args()


def normalize_domain_list(raw: str) -> list[str]:
    return [d.strip().lower() for d in raw.split(",") if d.strip()]


def is_allowed_domain(hostname: str, allow_domains: list[str]) -> bool:
    if not allow_domains:
        return True
    host = hostname.lower()
    for candidate in allow_domains:
        if host == candidate or host.endswith("." + candidate):
            return True
    return False


def resolve_file_uri(parsed_path: str) -> Path:
    decoded = unquote(parsed_path)
    if re.match(r"^/[A-Za-z]:/", decoded):
        decoded = decoded[1:]
    return Path(decoded)


def load_source(url: str, timeout: int, allow_domains: list[str]) -> tuple[str, str, bool]:
    source = url.strip()
    parsed = urlparse(source)

    if Path(source).exists():
        path = Path(source).resolve()
        return path.read_text(encoding="utf-8", errors="replace"), path.as_uri(), path.suffix.lower() in {".html", ".htm"}

    if parsed.scheme == "file":
        path = resolve_file_uri(parsed.path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return path.read_text(encoding="utf-8", errors="replace"), path.as_uri(), path.suffix.lower() in {".html", ".htm"}

    if parsed.scheme in {"http", "https"}:
        hostname = parsed.hostname or ""
        if not is_allowed_domain(hostname, allow_domains):
            raise ValueError(f"Domain not in allowlist: {hostname}")
        request = Request(source, headers={"User-Agent": "jetson-deployment-agent/1.0"})
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            content_type = response.headers.get("Content-Type", "")
        text = raw.decode("utf-8", errors="replace")
        is_html = "html" in content_type.lower() or "<html" in text.lower()
        return text, source, is_html

    raise ValueError(f"Unsupported URL or path: {source}")


def to_plain_text(content: str, is_html: bool) -> str:
    if not is_html:
        return content
    parser = PlainTextHTMLParser()
    parser.feed(content)
    return parser.text()


def normalize_lines(text: str) -> list[str]:
    lines: list[str] = []
    for line in text.splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip()
        if cleaned:
            lines.append(cleaned)
    return lines


def extract_hardware(lines: Iterable[str]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for line in lines:
        lowered = line.lower()
        if any(keyword in lowered for keyword in HARDWARE_KEYWORDS):
            if line not in seen:
                seen.add(line)
                items.append(line)
    return items


def extract_software(lines: Iterable[str]) -> list[str]:
    items: list[str] = []
    seen: set[str] = set()
    for line in lines:
        lowered = line.lower()
        if any(keyword in lowered for keyword in SOFTWARE_KEYWORDS):
            if line not in seen:
                seen.add(line)
                items.append(line)
    return items


def canonical_component(raw_component: str) -> str:
    normalized = re.sub(r"\s+", " ", raw_component.lower()).strip()
    return COMPONENT_ALIASES.get(normalized, normalized)


def extract_constraints(lines: Iterable[str]) -> list[Constraint]:
    constraints: list[Constraint] = []
    seen: set[tuple[str, str, str, str]] = set()
    for line in lines:
        for match in CONSTRAINT_RE.finditer(line):
            component = canonical_component(match.group(1))
            operator = match.group(2) or "=="
            version = match.group(3)
            key = (component, operator, version, line)
            if key in seen:
                continue
            seen.add(key)
            constraints.append(
                Constraint(
                    component=component,
                    operator=operator,
                    version=version,
                    evidence=line,
                )
            )
    constraints.sort(key=lambda c: (c.component, c.version, c.operator, c.evidence))
    return constraints


def compute_confidence(
    hardware_count: int,
    software_count: int,
    constraint_count: int,
) -> float:
    score = 0.20
    score += min(constraint_count, 6) * 0.10
    score += min(hardware_count, 4) * 0.05
    score += min(software_count, 4) * 0.05
    return round(min(score, 0.99), 2)


def main() -> int:
    args = parse_args()
    allow_domains = normalize_domain_list(args.allow_domains)

    try:
        content, source_url, is_html = load_source(args.url, args.timeout, allow_domains)
    except Exception as exc:
        print(f"[extract-tutorial-requirements][ERROR] {exc}", file=sys.stderr)
        return 1

    text = to_plain_text(content, is_html)
    lines = normalize_lines(text)
    hardware = extract_hardware(lines)
    software = extract_software(lines)
    constraints = extract_constraints(lines)

    notes: list[str] = []
    if not constraints:
        notes.append("No explicit version constraints were found.")
    if not hardware:
        notes.append("No explicit hardware requirements were found.")
    if not software:
        notes.append("No explicit software requirements were found.")

    confidence = compute_confidence(len(hardware), len(software), len(constraints))
    if confidence < 0.50:
        notes.append("Low confidence extraction. Request user confirmation before execution.")

    payload = {
        "source_url": source_url,
        "hardware_requirements": hardware,
        "software_requirements": software,
        "version_constraints": [
            {
                "component": c.component,
                "operator": c.operator,
                "version": c.version,
                "evidence": c.evidence,
            }
            for c in constraints
        ],
        "notes": notes,
        "confidence": confidence,
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
