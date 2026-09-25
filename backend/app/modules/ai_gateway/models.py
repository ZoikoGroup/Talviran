"""ai_gateway schema (AI-001) - the single controlled path to model
providers (§4.2: "no direct application-to-model-provider path"). A0
("Gateway foundation", §34 - exit criterion: "direct-provider access
impossible"): the provider/model registry, plus a real, audited call
record.

Deliberately NOT modelled yet, because nothing in this slice writes or
reads them (same discipline as every other module's "don't add a column
nothing uses"): ai_prompt_template, ai_output_schema, ai_toolset,
ai_eval_suite, ai_eval_run (§27) - these belong to A3 (routing) and A4
(evaluation), neither of which exists yet. ai_model_execution carries
evidence_bundle_id (A1, evidence_path.py); ai_validation_result (A2,
validation.py) is now real - prompt_template_id, toolset_version and
policy_version still wait on those later slices' subsystems.

Kill switches reuse governance.KillSwitch (policy/models.py, already
exists) rather than a new ai_kill_switch table - it already is exactly
what AI-001 §27 wants (a named, activatable switch with an audit trail:
code/is_active/activated_at/activated_by_principal_id/reason). Scoped
here by a naming convention on `code`: "ai_gateway.global",
"ai_gateway.provider.<provider code>", "ai_gateway.model.<model id>" -
not a capability_code, so this is a genuinely separate check from
policy.pdp's own kill-switch precedence step, not a duplicate of it.
"""

import datetime as dt
import uuid
from typing import Any

from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base, CreatedAtMixin, UUIDPrimaryKeyMixin

# AI-001 §5's Model Provider & Model Registry status lifecycle - a model
# must earn PRODUCTION status via evaluation (§22 Model/Prompt Change
# Management), never default there.
STATUS_CANDIDATE = "CANDIDATE"
STATUS_QA = "QA"
STATUS_PRODUCTION = "PRODUCTION"
STATUS_RESTRICTED = "RESTRICTED"
STATUS_DISABLED = "DISABLED"

KILL_SWITCH_GLOBAL_CODE = "ai_gateway.global"


def kill_switch_provider_code(provider_code: str) -> str:
    return f"ai_gateway.provider.{provider_code}"


def kill_switch_model_code(model_id: uuid.UUID) -> str:
    return f"ai_gateway.model.{model_id}"


class AIProvider(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    __tablename__ = "ai_provider"
    __table_args__ = {"schema": "ai_gateway"}

    code: Mapped[str] = mapped_column(String(64), unique=True)  # e.g. "groq", "gemini"
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(16), default=STATUS_CANDIDATE)


class AIModel(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """One callable model under a provider. task_type is the routing key
    research.conversation.model already produces (talvrin-go/talvrin-pro,
    see backend/app/modules/api/v1/chats.py's ALLOWED_MODELS) - AI-001
    §26.2's "no client-selected model": a caller picks a task tier, this
    registry resolves the actual provider/model, never the reverse.
    """

    __tablename__ = "ai_model"
    __table_args__ = {"schema": "ai_gateway"}

    provider_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_gateway.ai_provider.id"), index=True
    )
    model_key: Mapped[str] = mapped_column(String(200))  # e.g. "gemini-flash-lite-latest"
    task_type: Mapped[str] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(16), default=STATUS_CANDIDATE)


class AIModelExecution(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """The forensic/audit record (AI-001 §18, trimmed - see module
    docstring). §18.1's "forensic reconstruction, not false determinism":
    this must reproduce the request context, but never promises
    byte-identical replay from a hosted provider.
    """

    __tablename__ = "ai_model_execution"
    __table_args__ = {"schema": "ai_gateway"}

    task_type: Mapped[str] = mapped_column(String(32), index=True)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_gateway.ai_provider.id"), index=True
    )
    model_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_gateway.ai_model.id"), index=True
    )
    # Not a FK to evidence.evidence_bundle - same cross-schema convention
    # policy/models.py documents for research.message: the owning module
    # (evidence) isn't guaranteed to be imported first in every process,
    # and this row must still exist forensically even if the bundle it
    # names is later purged (EVID-001 purge semantics).
    evidence_bundle_id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True))
    request_started_at: Mapped[dt.datetime]
    response_received_at: Mapped[dt.datetime | None] = mapped_column(default=None)
    prompt_text: Mapped[str] = mapped_column(String())
    response_text: Mapped[str | None] = mapped_column(String(), default=None)
    finish_reason: Mapped[str | None] = mapped_column(String(32), default=None)
    token_usage: Mapped[dict[str, Any] | None] = mapped_column(JSONB, default=None)
    error: Mapped[str | None] = mapped_column(String(1000), default=None)


class AIValidationResult(UUIDPrimaryKeyMixin, CreatedAtMixin, Base):
    """AI-001 §27, §23: one row per validated response - up to two per
    invoke_model call (the original attempt, and the single bounded
    regeneration if the first failed). A row only exists when a provider
    actually returned text to validate - kill-switch/PDP/empty-bundle
    rejections never reach validation at all, so they never get one.
    """

    __tablename__ = "ai_validation_result"
    __table_args__ = {"schema": "ai_gateway"}

    ai_model_execution_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("ai_gateway.ai_model_execution.id"), index=True
    )
    passed: Mapped[bool] = mapped_column()
    failure_reasons: Mapped[list[str] | None] = mapped_column(JSONB, default=None)
