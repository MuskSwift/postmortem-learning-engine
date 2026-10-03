"""Command line for the closed-incident learning slice."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

from postmortem_learning_engine.generate import GenerationError, generate
from postmortem_learning_engine.validate import REQUIRED_HEADINGS, validate_or_errors

_ANSI_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_OPENING_FENCE_RE = re.compile(r"^```[^`]*$")


class UsageError(Exception):
    """Invalid invocation. The message starts with 'error:'."""


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            continue


def slugify_incident(incident: str) -> str:
    """Build a filesystem slug from the first non-empty incident line."""

    first = ""
    for line in incident.splitlines():
        stripped = line.strip()
        if stripped:
            first = stripped
            break
    first = re.sub(r"^#+\s*", "", first)
    first = first.lower()
    first = re.sub(r"\s+", "-", first)
    first = re.sub(r"[^\w\-]", "", first)
    first = first.strip("-")
    if len(first) > 48:
        first = first[:48].strip("-")
    if not first:
        first = hashlib.sha256(incident.encode("utf-8")).hexdigest()[:12]
    return first


def _is_opening_fence(line: str) -> bool:
    return _OPENING_FENCE_RE.match(line.strip()) is not None


def _strip_wrapping_fences(text: str) -> str:
    lines = text.splitlines()
    while (
        len(lines) >= 2
        and _is_opening_fence(lines[0])
        and lines[-1].strip() == "```"
    ):
        lines = lines[1:-1]
    return "\n".join(lines)


def _drop_before_required_h2(text: str) -> str:
    lines = text.splitlines()
    required = set(REQUIRED_HEADINGS)
    for index, line in enumerate(lines):
        if line.lstrip(" \t") in required:
            return "\n".join(lines[index:])
    return "\n".join(lines)


def _drop_odd_trailing_fence(text: str) -> str:
    lines = text.splitlines()
    if not lines:
        return ""
    fence_count = sum(
        1 for line in lines if line.lstrip(" \t").startswith("```")
    )
    if fence_count % 2 == 1 and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines)


def normalize_model_output(raw: str) -> str:
    """Strip ANSI and fences, then start the file at the first required H2."""

    text = raw.replace("\ufeff", "")
    text = _ANSI_RE.sub("", text)
    text = _strip_wrapping_fences(text)
    text = _drop_before_required_h2(text)
    text = _drop_odd_trailing_fence(text)
    if not text.endswith("\n"):
        text += "\n"
    return text


def _read_utf8_sig(path: str, label: str) -> str:
    file_path = Path(path)
    if not file_path.is_file():
        raise UsageError(f"error: {label} file not found: {path}")
    try:
        return file_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UsageError(f"error: bad utf-8 in {label} file: {path}") from exc
    except OSError as exc:
        raise UsageError(f"error: cannot read {label} file: {path}") from exc


def _join_parts(inline: str | None, file_text: str | None) -> str | None:
    if inline is None and file_text is None:
        return None
    if inline is not None and file_text is not None:
        return inline.rstrip("\r\n") + "\n\n" + file_text.lstrip("\r\n")
    if inline is not None:
        return inline
    return file_text


def _discard(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        return


_EXCERPT_LINE_LIMIT = 40
_EXCERPT_CHAR_LIMIT = 2000
_FAILURE_MARKER = "--- rejected excerpt (not a valid slice) ---"


def _failure_excerpt_path(out_path: Path) -> Path:
    return out_path.with_suffix(".fail.txt")


def _rejected_excerpt(text: str) -> str:
    """First 40 lines of rejected text, then at most 2000 characters."""

    excerpt = "\n".join(text.splitlines()[:_EXCERPT_LINE_LIMIT])
    if len(excerpt) > _EXCERPT_CHAR_LIMIT:
        return excerpt[:_EXCERPT_CHAR_LIMIT]
    return excerpt


def _write_failure_excerpt(out_path: Path, errors: list[str], text: str) -> None:
    """Write a short gitignored excerpt. This file is not a valid slice."""

    payload = "\n".join(
        ["validation failed", *errors, "", _FAILURE_MARKER]
    )
    payload += "\n" + _rejected_excerpt(text)
    try:
        _failure_excerpt_path(out_path).write_text(payload, encoding="utf-8")
    except OSError:
        return


def _discard_failure_excerpt(out_path: Path) -> None:
    try:
        _failure_excerpt_path(out_path).unlink(missing_ok=True)
    except OSError:
        return


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="postmortem-learning-engine",
        description=(
            "Write a learning slice for a closed incident: one timeline, "
            "impact that already happened, falsifiable hypotheses, detection "
            "gaps, checkable intentions, and explicit non-goals."
        ),
    )
    parser.add_argument(
        "--incident",
        "--text",
        "--materials",
        default=None,
        help="Inline closed-incident text. Joined with --incident-file when both are set.",
    )
    parser.add_argument(
        "--incident-file",
        "--text-file",
        "--materials-file",
        default=None,
        help="UTF-8 text file of the closed incident (BOM allowed).",
    )
    parser.add_argument(
        "--constraints",
        default=None,
        help="Optional inline constraints. Empty text is allowed.",
    )
    parser.add_argument(
        "--constraints-file",
        default=None,
        help="Optional UTF-8 constraints file. Empty text is allowed.",
    )
    parser.add_argument(
        "--out",
        default=None,
        help="Output markdown path. Default: ./out/<slug>-postmortem-learning.md",
    )
    return parser


def _load_incident_and_constraints(args: argparse.Namespace) -> tuple[str, str]:
    incident_file_text = None
    constraints_file_text = None
    if args.incident_file is not None:
        incident_file_text = _read_utf8_sig(args.incident_file, "incident")
    if args.constraints_file is not None:
        constraints_file_text = _read_utf8_sig(args.constraints_file, "constraints")
    if args.incident is None and incident_file_text is None:
        raise UsageError(
            "error: missing incident; pass --incident or --incident-file"
        )
    incident = _join_parts(args.incident, incident_file_text)
    if incident is None or not incident.strip():
        raise UsageError(
            "error: missing incident text; provide non-empty closed-incident text"
        )
    if args.constraints is None and constraints_file_text is None:
        constraints = ""
    else:
        constraints = _join_parts(args.constraints, constraints_file_text) or ""
    return incident, constraints


def _publish(out_path: Path, text: str) -> int:
    """Write the slice, then delete it again if validation fails."""

    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(text, encoding="utf-8")
    except OSError as exc:
        _discard(out_path)
        print(f"could not write output: {exc}", file=sys.stderr)
        return 1
    errors = validate_or_errors(text)
    if errors:
        _discard(out_path)
        for err in errors:
            print(err, file=sys.stderr)
        _write_failure_excerpt(out_path, errors, text)
        return 1
    _discard_failure_excerpt(out_path)
    print(str(out_path))
    return 0


def _main(argv: list[str] | None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    incident, constraints = _load_incident_and_constraints(args)
    if args.out:
        out_path = Path(args.out)
    else:
        slug = slugify_incident(incident)
        out_path = Path("out") / f"{slug}-postmortem-learning.md"
    try:
        raw = generate(incident, constraints)
    except GenerationError as exc:
        # No output file has been published yet, so a previous file at --out
        # is left as it was.
        print(str(exc), file=sys.stderr)
        return 1
    text = normalize_model_output(raw)
    try:
        return _publish(out_path, text)
    except GenerationError as exc:
        _discard(out_path)
        print(str(exc), file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    try:
        return _main(argv)
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130
    except UsageError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except SystemExit as exc:
        code = exc.code
        if code is None or code == 0:
            return 0
        if isinstance(code, int):
            return code
        print(str(code), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
