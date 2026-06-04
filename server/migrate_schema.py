from __future__ import annotations

import re

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from database import engine
from models import PromptVersion
from prompt_compose import normalize_prompt_parts, split_prompt_content

_PROMPT_FILENAME_PARSE = re.compile(
    r"^(segment_compress|history_merge)_(v\d+)_nsfw(_en)?\.txt$",
    re.IGNORECASE,
)


def migrate_prompt_sfw_nsfw(db: Session) -> None:
    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("prompts")}

    if "content_sfw" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE prompts ADD COLUMN content_sfw LONGTEXT NULL"))
            conn.execute(text("ALTER TABLE prompts ADD COLUMN content_nsfw LONGTEXT NULL"))

    columns = {column["name"] for column in inspector.get_columns("prompts")}

    if "content" in columns:
        rows = db.execute(text("SELECT id, content FROM prompts")).mappings().all()
        for row in rows:
            sfw, nsfw = split_prompt_content(row["content"] or "")
            db.execute(
                text("UPDATE prompts SET content_sfw = :sfw, content_nsfw = :nsfw WHERE id = :id"),
                {"sfw": sfw, "nsfw": nsfw, "id": row["id"]},
            )
        db.commit()
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE prompts DROP COLUMN content"))
        columns.discard("content")

    db.execute(text("UPDATE prompts SET content_sfw = '' WHERE content_sfw IS NULL"))
    db.execute(text("UPDATE prompts SET content_nsfw = '' WHERE content_nsfw IS NULL"))
    db.commit()

    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE prompts MODIFY content_sfw LONGTEXT NOT NULL"))
        conn.execute(text("ALTER TABLE prompts MODIFY content_nsfw LONGTEXT NOT NULL"))


def migrate_prompt_drop_filename(db: Session) -> None:
    inspector = inspect(engine)
    if "prompts" not in inspector.get_table_names():
        return

    columns = {column["name"] for column in inspector.get_columns("prompts")}
    if "filename" not in columns:
        return

    if "prompt_type" not in columns:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE prompts ADD COLUMN prompt_type VARCHAR(64) NULL"))
            conn.execute(text("ALTER TABLE prompts ADD COLUMN lang VARCHAR(8) NULL"))

    rows = db.execute(text("SELECT id, filename FROM prompts")).mappings().all()
    for row in rows:
        fname = (row["filename"] or "").strip()
        match = _PROMPT_FILENAME_PARSE.match(fname)
        if match:
            prompt_type = match.group(1).lower()
            lang = "en" if match.group(3) else "zh"
        else:
            prompt_type = "segment_compress"
            lang = "zh"
        db.execute(
            text(
                "UPDATE prompts SET prompt_type = :prompt_type, lang = :lang WHERE id = :id"
            ),
            {"prompt_type": prompt_type, "lang": lang, "id": row["id"]},
        )
    db.commit()

    db.execute(
        text(
            "UPDATE prompts SET prompt_type = 'segment_compress' "
            "WHERE prompt_type IS NULL OR prompt_type = ''"
        )
    )
    db.execute(text("UPDATE prompts SET lang = 'zh' WHERE lang IS NULL OR lang = ''"))
    db.commit()

    unique_names = {c["name"] for c in inspector.get_unique_constraints("prompts")}
    index_names = {idx["name"] for idx in inspector.get_indexes("prompts")}

    with engine.begin() as conn:
        if "uk_version_filename" in unique_names or "uk_version_filename" in index_names:
            conn.execute(text("ALTER TABLE prompts DROP INDEX uk_version_filename"))
        conn.execute(text("ALTER TABLE prompts MODIFY prompt_type VARCHAR(64) NOT NULL"))
        conn.execute(text("ALTER TABLE prompts MODIFY lang VARCHAR(8) NOT NULL"))
        if "uk_prompt_version_type_lang" not in unique_names:
            conn.execute(
                text(
                    "ALTER TABLE prompts ADD CONSTRAINT uk_prompt_version_type_lang "
                    "UNIQUE (version, prompt_type, lang)"
                )
            )
        conn.execute(text("ALTER TABLE prompts DROP COLUMN filename"))


def migrate_prompt_whitespace(db: Session) -> None:
    rows = db.execute(text("SELECT id, content_sfw, content_nsfw FROM prompts")).mappings().all()
    changed = False
    for row in rows:
        sfw, nsfw = normalize_prompt_parts(row["content_sfw"] or "", row["content_nsfw"] or "")
        if sfw != (row["content_sfw"] or "") or nsfw != (row["content_nsfw"] or ""):
            db.execute(
                text("UPDATE prompts SET content_sfw = :sfw, content_nsfw = :nsfw WHERE id = :id"),
                {"sfw": sfw, "nsfw": nsfw, "id": row["id"]},
            )
            changed = True
    if changed:
        db.commit()


def migrate_version_schema(db: Session) -> None:
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if "prompt_versions" not in tables:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE prompt_versions (
                        version VARCHAR(64) PRIMARY KEY,
                        base_version VARCHAR(64) NOT NULL,
                        is_baseline TINYINT(1) NOT NULL DEFAULT 0,
                        status VARCHAR(16) NOT NULL DEFAULT 'committed',
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
            )

    prompt_cols = {c["name"]: c for c in inspector.get_columns("prompts")}
    if prompt_cols.get("version", {}).get("type") and "64" not in str(prompt_cols["version"]["type"]):
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE prompts MODIFY version VARCHAR(64) NOT NULL"))

    doc_cols = {c["name"]: c for c in inspector.get_columns("version_docs")}
    if doc_cols.get("version", {}).get("type") and "64" not in str(doc_cols["version"]["type"]):
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE version_docs MODIFY version VARCHAR(64) NOT NULL"))

    for baseline in ("v1", "v2"):
        exists = db.query(PromptVersion).filter(PromptVersion.version == baseline).first()
        if not exists:
            db.add(
                PromptVersion(
                    version=baseline,
                    base_version=baseline,
                    is_baseline=True,
                    status="committed",
                )
            )
    db.commit()

    for row in db.query(PromptVersion).filter(PromptVersion.is_baseline.is_(False)).all():
        if row.status == "draft":
            continue
        exists = db.query(PromptVersion).filter(PromptVersion.version == row.version).first()
        if exists and exists.status != "committed":
            exists.status = "committed"

    db.commit()


def migrate_jailbreak_schema(db: Session) -> None:
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if "jailbreak_prompts" not in tables:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE jailbreak_prompts (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        scheme_name VARCHAR(64) NOT NULL,
                        version VARCHAR(16) NOT NULL,
                        target_model VARCHAR(128) NOT NULL,
                        content LONGTEXT NOT NULL,
                        content_mode VARCHAR(16) NOT NULL DEFAULT 'plain',
                        modules_json LONGTEXT NULL,
                        changelog TEXT NOT NULL,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        UNIQUE KEY uk_jailbreak_scheme_version (scheme_name, version),
                        INDEX idx_jailbreak_scheme (scheme_name)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
            )
    else:
        columns = {column["name"] for column in inspector.get_columns("jailbreak_prompts")}
        alters: list[str] = []
        if "content_mode" not in columns:
            alters.append(
                "ADD COLUMN content_mode VARCHAR(16) NOT NULL DEFAULT 'plain' AFTER content"
            )
        if "modules_json" not in columns:
            alters.append("ADD COLUMN modules_json LONGTEXT NULL AFTER content_mode")
        if alters:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE jailbreak_prompts {', '.join(alters)}"))


def migrate_chat_qa_schema(db: Session) -> None:
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if "chat_qa_cases" not in tables:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE chat_qa_cases (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id VARCHAR(32) NOT NULL,
                        role_id VARCHAR(32) NOT NULL,
                        role_name VARCHAR(128) NOT NULL,
                        app_name VARCHAR(128) NOT NULL DEFAULT '',
                        question LONGTEXT NOT NULL,
                        answer LONGTEXT NOT NULL,
                        status VARCHAR(32) NOT NULL DEFAULT '',
                        u_time DOUBLE NOT NULL DEFAULT 0,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        INDEX idx_chat_qa_user (user_id),
                        INDEX idx_chat_qa_role (role_id),
                        INDEX idx_chat_qa_role_name (role_name),
                        INDEX idx_chat_qa_u_time (u_time)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
            )
    else:
        columns = {column["name"] for column in inspector.get_columns("chat_qa_cases")}
        if "u_time" not in columns:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE chat_qa_cases ADD COLUMN u_time DOUBLE NOT NULL DEFAULT 0"
                    )
                )
                conn.execute(
                    text("CREATE INDEX idx_chat_qa_u_time ON chat_qa_cases (u_time)")
                )


def migrate_prompt_test_result_schema(db: Session) -> None:
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if "prompt_test_results" not in tables:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE prompt_test_results (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id VARCHAR(32) NOT NULL,
                        role_id VARCHAR(32) NOT NULL,
                        app_name VARCHAR(128) NOT NULL DEFAULT '',
                        role_name VARCHAR(128) NOT NULL DEFAULT '',
                        run_group_id INT NOT NULL DEFAULT 0,
                        prompt_type VARCHAR(64) NOT NULL,
                        expected_result LONGTEXT NOT NULL,
                        round_start INT NOT NULL DEFAULT 1,
                        round_end INT NOT NULL DEFAULT 10,
                        prompt_version VARCHAR(64) NOT NULL DEFAULT '',
                        model VARCHAR(128) NOT NULL DEFAULT '',
                        top_k INT NULL,
                        temperature DOUBLE NOT NULL DEFAULT 0,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        INDEX idx_prompt_test_user (user_id),
                        INDEX idx_prompt_test_role (role_id),
                        INDEX idx_prompt_test_type (prompt_type),
                        INDEX idx_prompt_test_run_group (user_id, role_id, app_name, run_group_id),
                        UNIQUE KEY uk_prompt_test_run_model_type (run_group_id, model, prompt_type)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
            )
    else:
        columns = {column["name"] for column in inspector.get_columns("prompt_test_results")}
        alters: list[str] = []
        if "prompt_version" not in columns:
            alters.append(
                "ADD COLUMN prompt_version VARCHAR(64) NOT NULL DEFAULT '' AFTER round_end"
            )
        if "model" not in columns:
            alters.append("ADD COLUMN model VARCHAR(128) NOT NULL DEFAULT '' AFTER prompt_version")
        if "top_k" not in columns:
            alters.append("ADD COLUMN top_k INT NULL AFTER model")
        if "temperature" not in columns:
            alters.append("ADD COLUMN temperature DOUBLE NOT NULL DEFAULT 0 AFTER top_k")
        if "run_group_id" not in columns:
            alters.append(
                "ADD COLUMN run_group_id INT NOT NULL DEFAULT 0 AFTER role_name"
            )
        if alters:
            with engine.begin() as conn:
                conn.execute(
                    text(f"ALTER TABLE prompt_test_results {', '.join(alters)}")
                )
        columns = {column["name"] for column in inspector.get_columns("prompt_test_results")}
        if "run_group_id" in columns:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "UPDATE prompt_test_results SET run_group_id = id "
                        "WHERE run_group_id = 0"
                    )
                )
        indexes = {idx["name"] for idx in inspector.get_indexes("prompt_test_results")}
        if "uk_prompt_test_result_conv_type" in indexes:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE prompt_test_results "
                        "DROP INDEX uk_prompt_test_result_conv_type"
                    )
                )
        indexes = {idx["name"] for idx in inspector.get_indexes("prompt_test_results")}
        if "idx_prompt_test_run_group" not in indexes:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "CREATE INDEX idx_prompt_test_run_group ON prompt_test_results "
                        "(user_id, role_id, app_name, run_group_id)"
                    )
                )

        indexes = {idx["name"] for idx in inspector.get_indexes("prompt_test_results")}
        if "uk_prompt_test_run_model_type" not in indexes:
            from prompt_test_result_service import regroup_prompt_test_run_groups

            regroup_prompt_test_run_groups(db)
            indexes = {idx["name"] for idx in inspector.get_indexes("prompt_test_results")}
        if "uk_prompt_test_run_model_type" not in indexes:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "CREATE UNIQUE INDEX uk_prompt_test_run_model_type "
                        "ON prompt_test_results (run_group_id, model, prompt_type)"
                    )
                )


def migrate_rp_eval_schema(db: Session) -> None:
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if "rp_eval_results" not in tables:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE rp_eval_results (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        user_id VARCHAR(32) NOT NULL,
                        role_id VARCHAR(32) NOT NULL,
                        app_name VARCHAR(128) NOT NULL DEFAULT '',
                        role_name VARCHAR(128) NOT NULL DEFAULT '',
                        round_start INT NOT NULL DEFAULT 1,
                        round_end INT NOT NULL DEFAULT 10,
                        has_compress TINYINT(1) NOT NULL DEFAULT 0,
                        has_merge TINYINT(1) NOT NULL DEFAULT 0,
                        compress_prompt_version VARCHAR(64) NOT NULL DEFAULT '',
                        merge_prompt_version VARCHAR(64) NOT NULL DEFAULT '',
                        eval_system_prompt LONGTEXT NOT NULL,
                        eval_result LONGTEXT NOT NULL,
                        raw_model_output LONGTEXT NOT NULL,
                        model VARCHAR(128) NOT NULL DEFAULT '',
                        top_k INT NULL,
                        temperature DOUBLE NOT NULL DEFAULT 0,
                        overall_score INT NOT NULL DEFAULT 0,
                        overall_confidence DOUBLE NOT NULL DEFAULT 0,
                        eval_mode VARCHAR(32) NOT NULL DEFAULT 'single',
                        evaluated_models LONGTEXT NOT NULL DEFAULT '[]',
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_rp_eval_conv (user_id, role_id, app_name),
                        INDEX idx_rp_eval_created (created_at)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
            )
    else:
        columns = {column["name"] for column in inspector.get_columns("rp_eval_results")}
        alters: list[str] = []
        if "compress_prompt_version" not in columns:
            alters.append(
                "ADD COLUMN compress_prompt_version VARCHAR(64) NOT NULL DEFAULT '' "
                "AFTER has_merge"
            )
        if "merge_prompt_version" not in columns:
            alters.append(
                "ADD COLUMN merge_prompt_version VARCHAR(64) NOT NULL DEFAULT '' "
                "AFTER compress_prompt_version"
            )
        if "eval_mode" not in columns:
            alters.append(
                "ADD COLUMN eval_mode VARCHAR(32) NOT NULL DEFAULT 'single' "
                "AFTER overall_confidence"
            )
        if "evaluated_models" not in columns:
            alters.append(
                "ADD COLUMN evaluated_models LONGTEXT NOT NULL "
                "DEFAULT '[]' AFTER eval_mode"
            )
        if alters:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE rp_eval_results {', '.join(alters)}"))


def migrate_brain_schema(db: Session) -> None:
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    if "brain_analysis_results" not in tables:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    CREATE TABLE brain_analysis_results (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        rp_eval_id INT NOT NULL,
                        user_id VARCHAR(32) NOT NULL,
                        role_id VARCHAR(32) NOT NULL,
                        app_name VARCHAR(128) NOT NULL DEFAULT '',
                        role_name VARCHAR(128) NOT NULL DEFAULT '',
                        round_start INT NOT NULL DEFAULT 1,
                        round_end INT NOT NULL DEFAULT 10,
                        compress_prompt_version VARCHAR(64) NOT NULL DEFAULT '',
                        merge_prompt_version VARCHAR(64) NOT NULL DEFAULT '',
                        overall VARCHAR(16) NOT NULL DEFAULT 'hold',
                        brain_system_prompt LONGTEXT NOT NULL,
                        brain_result LONGTEXT NOT NULL,
                        raw_model_output LONGTEXT NOT NULL,
                        model VARCHAR(128) NOT NULL DEFAULT '',
                        top_k INT NULL,
                        temperature DOUBLE NOT NULL DEFAULT 0,
                        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                        INDEX idx_brain_conv (user_id, role_id, app_name),
                        INDEX idx_brain_rp_eval (rp_eval_id),
                        INDEX idx_brain_created (created_at)
                    ) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci
                    """
                )
            )
