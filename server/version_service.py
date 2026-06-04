from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import HTTPException
from sqlalchemy.orm import Session

from config import BASELINE_VERSIONS
from models import Prompt, PromptVersion, VersionDoc
from prompt_compose import compose_prompt, normalize_prompt_parts
from redis_client import delete_draft, get_draft, list_draft_versions, save_draft

PROMPT_TYPES = ("segment_compress", "history_merge")
LANGS = ("zh", "en")

_SUFFIX_PATTERN = re.compile(r"^[a-zA-Z0-9_]+$")
_VERSION_NAME_PATTERN = re.compile(r"^[a-zA-Z][a-zA-Z0-9_]*$")


def prompt_storage_key(prompt_type: str, lang: str) -> str:
    return f"{prompt_type}_{lang}"


def version_doc_filename(version: str) -> str:
    return f"CHANGELOG_{version}.md"


def is_baseline(version: str) -> bool:
    return version in BASELINE_VERSIONS


def validate_writable(version: str) -> None:
    if is_baseline(version):
        raise HTTPException(status_code=403, detail=f"Baseline version {version} is read-only")


def validate_version_name(version: str) -> str:
    name = version.strip()
    if not name or len(name) > 64:
        raise HTTPException(status_code=400, detail="version must be 1-64 characters")
    if not _VERSION_NAME_PATTERN.match(name):
        raise HTTPException(status_code=400, detail="version must match [a-zA-Z][a-zA-Z0-9_]*")
    if is_baseline(name):
        raise HTTPException(status_code=400, detail=f"Version name {name} is reserved for baseline")
    return name


def _resolve_copy_source(db: Session, source_version: str) -> None:
    if is_baseline(source_version):
        return
    if get_draft(source_version):
        return
    row = db.query(PromptVersion).filter(PromptVersion.version == source_version).first()
    if row and row.status == "committed":
        return
    raise HTTPException(status_code=404, detail=f"Copy source version not found: {source_version}")


def _load_source_prompt(db: Session, source_version: str, prompt_type: str, lang: str) -> dict[str, str]:
    if is_baseline(source_version):
        return _load_baseline_prompt(db, source_version, prompt_type, lang)

    draft = get_draft(source_version)
    if draft:
        key = prompt_storage_key(prompt_type, lang)
        part = draft.get("prompts", {}).get(key)
        if part:
            return part

    part = _load_mysql_prompt(db, source_version, prompt_type, lang)
    if part["content_sfw"] or part["content_nsfw"]:
        return part
    raise HTTPException(status_code=404, detail=f"Source prompt not found: {source_version}")


def _load_source_doc(db: Session, source_version: str) -> str:
    if is_baseline(source_version):
        return _load_baseline_doc(db, source_version)
    draft = get_draft(source_version)
    if draft:
        return draft.get("doc_content", "")
    row = db.query(VersionDoc).filter(VersionDoc.version == source_version).first()
    return row.content if row else ""


def build_version_name(base_version: str, suffix: str) -> str:
    if base_version not in BASELINE_VERSIONS:
        raise HTTPException(status_code=400, detail="base_version must be v1 or v2")
    if not _SUFFIX_PATTERN.match(suffix):
        raise HTTPException(status_code=400, detail="suffix must match [a-zA-Z0-9_]+")
    return validate_version_name(f"{base_version}_{suffix}")


def _empty_prompt_part() -> dict[str, str]:
    return {"content_sfw": "", "content_nsfw": ""}


def _normalize_part(part: dict[str, str]) -> dict[str, str]:
    sfw, nsfw = normalize_prompt_parts(part.get("content_sfw", ""), part.get("content_nsfw", ""))
    return {"content_sfw": sfw, "content_nsfw": nsfw}


def _prompt_part_from_row(row: Prompt) -> dict[str, str]:
    return {"content_sfw": row.content_sfw, "content_nsfw": row.content_nsfw}


def _get_prompt_row(
    db: Session, version: str, prompt_type: str, lang: str
) -> Optional[Prompt]:
    return (
        db.query(Prompt)
        .filter(
            Prompt.version == version,
            Prompt.prompt_type == prompt_type,
            Prompt.lang == lang,
        )
        .first()
    )


def _load_baseline_prompt(db: Session, base_version: str, prompt_type: str, lang: str) -> dict[str, str]:
    row = _get_prompt_row(db, base_version, prompt_type, lang)
    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"Baseline prompt not found: {base_version}/{prompt_type}/{lang}",
        )
    return _prompt_part_from_row(row)


def _load_baseline_doc(db: Session, base_version: str) -> str:
    row = db.query(VersionDoc).filter(VersionDoc.version == base_version).first()
    if not row:
        return ""
    return row.content


def _load_mysql_prompt(db: Session, version: str, prompt_type: str, lang: str) -> dict[str, str]:
    row = _get_prompt_row(db, version, prompt_type, lang)
    if not row:
        return _empty_prompt_part()
    return _prompt_part_from_row(row)


def list_versions(db: Session) -> dict[str, Any]:
    baselines = ["v1", "v2"]
    custom_rows = (
        db.query(PromptVersion)
        .filter(PromptVersion.is_baseline.is_(False), PromptVersion.status == "committed")
        .order_by(PromptVersion.created_at.desc())
        .all()
    )
    custom = [
        {
            "version": row.version,
            "base_version": row.base_version,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in custom_rows
    ]
    draft_versions = list_draft_versions()
    drafts = []
    for version in draft_versions:
        draft = get_draft(version)
        if draft:
            drafts.append(
                {
                    "version": version,
                    "base_version": draft.get("base_version", ""),
                    "status": "draft",
                }
            )
    return {"baselines": baselines, "custom": custom, "drafts": drafts}


def get_version_meta(db: Session, version: str) -> dict[str, Any]:
    if is_baseline(version):
        return {
            "version": version,
            "base_version": version,
            "is_baseline": True,
            "status": "committed",
            "is_draft": False,
        }

    draft = get_draft(version)
    if draft:
        return {
            "version": version,
            "base_version": draft.get("base_version", ""),
            "is_baseline": False,
            "status": "draft",
            "is_draft": True,
            "has_en": bool(draft.get("prompts", {}).get("segment_compress_en")),
        }

    row = db.query(PromptVersion).filter(PromptVersion.version == version).first()
    if not row:
        raise HTTPException(status_code=404, detail="Version not found")

    has_en = _get_prompt_row(db, version, "segment_compress", "en") is not None
    return {
        "version": row.version,
        "base_version": row.base_version,
        "is_baseline": row.is_baseline,
        "status": row.status,
        "is_draft": False,
        "has_en": has_en,
    }


def create_version_draft(
    db: Session,
    version: str,
    base_version: Optional[str] = None,
) -> dict[str, Any]:
    version = validate_version_name(version)
    source = (base_version or "").strip() or None

    if source and source == version:
        raise HTTPException(status_code=400, detail="base_version cannot equal version")

    if db.query(PromptVersion).filter(PromptVersion.version == version).first():
        raise HTTPException(status_code=409, detail=f"Version {version} already committed")

    if get_draft(version):
        raise HTTPException(status_code=409, detail=f"Draft {version} already exists")

    prompts: dict[str, dict[str, str]] = {}
    if source:
        _resolve_copy_source(db, source)
        for prompt_type in PROMPT_TYPES:
            prompts[prompt_storage_key(prompt_type, "zh")] = _load_source_prompt(
                db, source, prompt_type, "zh"
            )
        doc_content = _load_source_doc(db, source)
        doc_content = doc_content.replace(source, version) if doc_content else f"# {version}\n\n"
    else:
        for prompt_type in PROMPT_TYPES:
            prompts[prompt_storage_key(prompt_type, "zh")] = _empty_prompt_part()
        doc_content = f"# {version}\n\n"

    draft = {
        "version": version,
        "base_version": source or "",
        "doc_content": doc_content,
        "prompts": prompts,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_draft(version, draft)
    return get_version_meta(db, version)


def get_prompt_content(
    db: Session,
    version: str,
    prompt_type: str,
    lang: str,
    include_nsfw: bool = True,
) -> dict[str, Any]:
    if prompt_type not in PROMPT_TYPES:
        raise HTTPException(status_code=400, detail="Invalid prompt type")
    if lang not in LANGS:
        raise HTTPException(status_code=400, detail="Invalid lang")

    key = prompt_storage_key(prompt_type, lang)

    if is_baseline(version):
        part = _normalize_part(_load_baseline_prompt(db, version, prompt_type, lang))
    else:
        draft = get_draft(version)
        if draft:
            part = _normalize_part(draft.get("prompts", {}).get(key) or _empty_prompt_part())
        else:
            part = _normalize_part(_load_mysql_prompt(db, version, prompt_type, lang))

    return {
        "version": version,
        "prompt_type": prompt_type,
        "lang": lang,
        "content_sfw": part["content_sfw"],
        "content_nsfw": part["content_nsfw"],
        "content": compose_prompt(part["content_sfw"], part["content_nsfw"], include_nsfw),
        "readonly": is_baseline(version),
    }


def get_doc_content(db: Session, version: str) -> dict[str, Any]:
    if is_baseline(version):
        row = db.query(VersionDoc).filter(VersionDoc.version == version).first()
        if not row:
            raise HTTPException(status_code=404, detail="Doc not found")
        return {
            "version": version,
            "filename": version_doc_filename(version),
            "content": row.content,
            "readonly": True,
        }

    draft = get_draft(version)
    if draft:
        return {
            "version": version,
            "filename": version_doc_filename(version),
            "content": draft.get("doc_content", ""),
            "readonly": False,
        }

    row = db.query(VersionDoc).filter(VersionDoc.version == version).first()
    if not row:
        raise HTTPException(status_code=404, detail="Doc not found")
    return {
        "version": version,
        "filename": version_doc_filename(version),
        "content": row.content,
        "readonly": False,
    }


def update_draft(
    db: Session,
    version: str,
    *,
    prompt_type: Optional[str] = None,
    lang: Optional[str] = None,
    content_sfw: Optional[str] = None,
    content_nsfw: Optional[str] = None,
    doc_content: Optional[str] = None,
) -> dict[str, Any]:
    validate_writable(version)

    draft = get_draft(version)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found in Redis")

    if prompt_type and lang:
        key = prompt_storage_key(prompt_type, lang)
        prompts = draft.setdefault("prompts", {})
        part = dict(prompts.get(key) or _empty_prompt_part())
        if content_sfw is not None:
            part["content_sfw"] = content_sfw
        if content_nsfw is not None:
            part["content_nsfw"] = content_nsfw
        prompts[key] = _normalize_part(part)

    if doc_content is not None:
        draft["doc_content"] = doc_content

    draft["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_draft(version, draft)
    return {"ok": True, "version": version, "updated_at": draft["updated_at"]}


def commit_version(db: Session, version: str) -> dict[str, Any]:
    validate_writable(version)

    draft = get_draft(version)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found in Redis")

    base_version = draft.get("base_version", "")
    prompts_data: dict[str, dict[str, str]] = draft.get("prompts", {})

    for prompt_type in PROMPT_TYPES:
        for lang in LANGS:
            key = prompt_storage_key(prompt_type, lang)
            part = prompts_data.get(key)
            if not part:
                continue
            normalized = _normalize_part(part)
            row = _get_prompt_row(db, version, prompt_type, lang)
            if row:
                row.content_sfw = normalized["content_sfw"]
                row.content_nsfw = normalized["content_nsfw"]
            else:
                db.add(
                    Prompt(
                        version=version,
                        prompt_type=prompt_type,
                        lang=lang,
                        content_sfw=normalized["content_sfw"],
                        content_nsfw=normalized["content_nsfw"],
                    )
                )

    doc_row = db.query(VersionDoc).filter(VersionDoc.version == version).first()
    doc_content = draft.get("doc_content", "")
    if doc_row:
        doc_row.content = doc_content
    else:
        db.add(VersionDoc(version=version, content=doc_content))

    meta = db.query(PromptVersion).filter(PromptVersion.version == version).first()
    if meta:
        meta.status = "committed"
        meta.base_version = base_version
    else:
        db.add(
            PromptVersion(
                version=version,
                base_version=base_version,
                is_baseline=False,
                status="committed",
            )
        )

    db.commit()
    delete_draft(version)
    return {"ok": True, "version": version, "status": "committed"}


def discard_draft(version: str) -> dict[str, Any]:
    validate_writable(version)
    if not get_draft(version):
        raise HTTPException(status_code=404, detail="Draft not found")
    delete_draft(version)
    return {"ok": True, "version": version}


def _all_custom_version_nodes(db: Session) -> dict[str, str]:
    """version -> base_version for committed custom versions and Redis drafts."""
    nodes: dict[str, str] = {}
    rows = db.query(PromptVersion).filter(PromptVersion.is_baseline.is_(False)).all()
    for row in rows:
        nodes[row.version] = row.base_version or ""
    for version in list_draft_versions():
        draft = get_draft(version)
        if draft:
            nodes[version] = draft.get("base_version", "")
    return nodes


def collect_version_subtree(nodes: dict[str, str], root: str) -> list[str]:
    """Return root and all descendants in post-order (children before parent)."""
    children_by_parent: dict[str, list[str]] = {}
    for version, base in nodes.items():
        if base:
            children_by_parent.setdefault(base, []).append(version)

    ordered: list[str] = []
    seen: set[str] = set()

    def walk(version: str) -> None:
        if version in seen:
            return
        seen.add(version)
        for child in children_by_parent.get(version, []):
            walk(child)
        ordered.append(version)

    walk(root)
    return ordered


def _delete_version_data(db: Session, version: str) -> None:
    delete_draft(version)
    db.query(Prompt).filter(Prompt.version == version).delete()
    db.query(VersionDoc).filter(VersionDoc.version == version).delete()
    db.query(PromptVersion).filter(PromptVersion.version == version).delete()


def delete_version_tree(db: Session, version: str) -> dict[str, Any]:
    if is_baseline(version):
        raise HTTPException(status_code=403, detail=f"Baseline version {version} cannot be deleted")

    nodes = _all_custom_version_nodes(db)
    draft = get_draft(version)
    row = db.query(PromptVersion).filter(PromptVersion.version == version).first()
    if version not in nodes and not draft and not row:
        raise HTTPException(status_code=404, detail="Version not found")

    to_delete = collect_version_subtree(nodes, version)
    for item in to_delete:
        _delete_version_data(db, item)
    db.commit()
    return {"ok": True, "deleted": to_delete}


def normalize_base_url(url: str) -> str:
    trimmed = url.strip().rstrip("/")
    if not trimmed:
        return trimmed
    lower = trimmed.lower()
    if lower.endswith("/v1/chat/completions"):
        return trimmed
    if lower.endswith("/v1/chat/completion"):
        return f"{trimmed[:-len('/completion')]}/completions"
    if lower.endswith("/v1/chat"):
        return f"{trimmed}/completions"
    if lower.endswith("/v1"):
        return f"{trimmed}/chat/completions"
    return f"{trimmed}/v1/chat/completions"


async def translate_draft(
    db: Session,
    version: str,
    *,
    base_url: str,
    api_key: str,
    model: str,
    temperature: float = 0.3,
) -> dict[str, Any]:
    validate_writable(version)

    draft = get_draft(version)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft not found in Redis")

    base_url = normalize_base_url(base_url)
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    translated_keys: list[str] = []
    for prompt_type in PROMPT_TYPES:
        zh_key = prompt_storage_key(prompt_type, "zh")
        zh_part = draft.get("prompts", {}).get(zh_key)
        if not zh_part:
            continue

        en_sfw = await _translate_text(
            base_url, headers, model, temperature, zh_part["content_sfw"], "content_sfw"
        )
        en_nsfw = await _translate_text(
            base_url, headers, model, temperature, zh_part["content_nsfw"], "content_nsfw"
        )
        en_key = prompt_storage_key(prompt_type, "en")
        draft.setdefault("prompts", {})[en_key] = {
            "content_sfw": en_sfw,
            "content_nsfw": en_nsfw,
        }
        translated_keys.append(en_key)

    draft["updated_at"] = datetime.now(timezone.utc).isoformat()
    save_draft(version, draft)
    return {"ok": True, "version": version, "translated": translated_keys}


async def _translate_text(
    base_url: str,
    headers: dict[str, str],
    model: str,
    temperature: float,
    text: str,
    field_name: str,
) -> str:
    if not text.strip():
        return ""

    system = (
        "You are a professional translator for RP Chat system prompts. "
        "Translate Chinese to English. Preserve exactly: {{NSFW}} placeholders, "
        "---NSFW_PART--- separators, JSON examples, markdown structure, and line breaks. "
        "Output ONLY the translated text, no explanation."
    )
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": f"Translate this {field_name}:\n\n{text}",
            },
        ],
        "stream": False,
        "temperature": temperature,
        "max_completion_tokens": 8192,
    }

    async with httpx.AsyncClient(timeout=180.0) as client:
        resp = await client.post(base_url, json=payload, headers=headers)

    if resp.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Translation API failed ({field_name}): {resp.text[:500]}",
        )

    data = resp.json()
    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return content.strip()
