from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from database import Base


class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    base_version: Mapped[str] = mapped_column(String(64), nullable=False)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="committed", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )


class Prompt(Base):
    __tablename__ = "prompts"
    __table_args__ = (
        UniqueConstraint("version", "prompt_type", "lang", name="uk_prompt_version_type_lang"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    prompt_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    lang: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    content_sfw: Mapped[str] = mapped_column(Text, nullable=False)
    content_nsfw: Mapped[str] = mapped_column(Text, nullable=False, default="")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class VersionDoc(Base):
    __tablename__ = "version_docs"

    version: Mapped[str] = mapped_column(String(64), primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class JailbreakPrompt(Base):
    __tablename__ = "jailbreak_prompts"
    __table_args__ = (
        UniqueConstraint("scheme_name", "version", name="uk_jailbreak_scheme_version"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    scheme_name: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    target_model: Mapped[str] = mapped_column(String(128), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="plain")
    modules_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    changelog: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PromptTestResult(Base):
    __tablename__ = "prompt_test_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    role_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    app_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    role_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    run_group_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    prompt_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    expected_result: Mapped[str] = mapped_column(Text, nullable=False)
    round_start: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    round_end: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    prompt_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    top_k: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class RpEvalResult(Base):
    __tablename__ = "rp_eval_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    role_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    app_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    role_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    round_start: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    round_end: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    has_compress: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    has_merge: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    compress_prompt_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    merge_prompt_version: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    eval_system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    eval_result: Mapped[str] = mapped_column(Text, nullable=False)
    raw_model_output: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    top_k: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    overall_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    overall_confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    eval_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="single")
    evaluated_models: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )


class ChatQaCase(Base):
    __tablename__ = "chat_qa_cases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    role_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    role_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    app_name: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    u_time: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
