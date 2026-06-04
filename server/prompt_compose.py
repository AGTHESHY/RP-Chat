from __future__ import annotations

import re

NSFW_MARKER = "{{NSFW}}"
NSFW_PART_SEP = "\n---NSFW_PART---\n"

_PRINCIPLE_PATTERN = re.compile(
    r"(\d+\. NSFW[^\n]*\n(?:[ \t]+[^\n]+\n)*?)(?=\n\s*\d+\. |\n\s*={5,}|\n\s*--- (?:NSFW|色情)|\Z)",
)
_SECTION_PATTERN = re.compile(
    r"(\s*--- (?:NSFW|色情)[^\n]* ---[\s\S]*?)(?=\n\s*={5,})",
)
_MARKER_CLEANUP = re.compile(r"\n*" + re.escape(NSFW_MARKER) + r"\n*")
_MULTI_NEWLINE = re.compile(r"\n{3,}")


def normalize_prompt_text(text: str) -> str:
    if not text:
        return ""
    return _MULTI_NEWLINE.sub("\n\n", text).strip()


def normalize_prompt_parts(content_sfw: str, content_nsfw: str) -> tuple[str, str]:
    if content_nsfw.strip():
        parts = [
            normalize_prompt_text(part)
            for part in content_nsfw.split(NSFW_PART_SEP)
            if part.strip()
        ]
        nsfw = NSFW_PART_SEP.join(parts)
    else:
        nsfw = ""
    return normalize_prompt_text(content_sfw), nsfw


def split_prompt_content(content: str) -> tuple[str, str]:
    parts: list[str] = []
    sfw = content

    match = _PRINCIPLE_PATTERN.search(sfw)
    if match:
        parts.append(match.group(1).strip())
        sfw = f"{sfw[:match.start()]}{NSFW_MARKER}\n{sfw[match.end():]}"

    match = _SECTION_PATTERN.search(sfw)
    if match:
        parts.append(match.group(1).strip())
        sfw = f"{sfw[:match.start()]}{NSFW_MARKER}\n{sfw[match.end():]}"

    return normalize_prompt_parts(sfw, NSFW_PART_SEP.join(parts))


def compose_prompt(content_sfw: str, content_nsfw: str, include_nsfw: bool = True) -> str:
    if not include_nsfw or not content_nsfw.strip():
        return normalize_prompt_text(_MARKER_CLEANUP.sub("\n", content_sfw))

    result = content_sfw
    for part in content_nsfw.split(NSFW_PART_SEP):
        part = part.strip()
        if not part:
            continue
        result = result.replace(NSFW_MARKER, part, 1)

    return normalize_prompt_text(_MARKER_CLEANUP.sub("\n", result))
