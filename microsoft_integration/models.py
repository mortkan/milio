"""SQLAlchemy ORM models for all Microsoft integration tables (ms_ prefix).

These models define ONLY the Microsoft-specific schema.
Milo tables are accessed via sync/local_repository.py using raw queries.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, declarative_base, mapped_column, relationship

Base = declarative_base()


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# ms_schema_version — tracks applied Microsoft migrations
# ---------------------------------------------------------------------------


class MsSchemaVersion(Base):
    __tablename__ = "ms_schema_version"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)


# ---------------------------------------------------------------------------
# ms_accounts — one row per connected Microsoft account
# ---------------------------------------------------------------------------


class MsAccount(Base):
    __tablename__ = "ms_accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    microsoft_user_id: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )
    tenant_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    email: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    account_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="personal"
    )  # personal | work | school
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    needs_reauthentication: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationships
    token_cache: Mapped[MsTokenCache | None] = relationship(
        "MsTokenCache", back_populates="account", uselist=False, cascade="all, delete-orphan"
    )
    sync_targets: Mapped[list[MsSyncTarget]] = relationship(
        "MsSyncTarget", back_populates="account", cascade="all, delete-orphan"
    )
    entity_links: Mapped[list[MsEntityLink]] = relationship(
        "MsEntityLink", back_populates="account", cascade="all, delete-orphan"
    )
    sync_runs: Mapped[list[MsSyncRun]] = relationship(
        "MsSyncRun", back_populates="account", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_ms_accounts_email", "email"),
        Index("ix_ms_accounts_enabled", "enabled"),
    )


# ---------------------------------------------------------------------------
# ms_token_cache — encrypted MSAL token cache, one row per account
# ---------------------------------------------------------------------------


class MsTokenCache(Base):
    __tablename__ = "ms_token_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ms_accounts.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    encrypted_cache: Mapped[str] = mapped_column(Text, nullable=False)  # Fernet-encrypted
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    account: Mapped[MsAccount] = relationship("MsAccount", back_populates="token_cache")

    __table_args__ = (Index("ix_ms_token_cache_account_id", "account_id"),)


# ---------------------------------------------------------------------------
# ms_sync_targets — which remote resources to sync per account
# ---------------------------------------------------------------------------


class MsSyncTarget(Base):
    __tablename__ = "ms_sync_targets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ms_accounts.id", ondelete="CASCADE"), nullable=False
    )
    target_type: Mapped[str] = mapped_column(String(20), nullable=False)  # calendar | todo_list
    remote_id: Mapped[str] = mapped_column(String(400), nullable=False)
    remote_name: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    sync_direction: Mapped[str] = mapped_column(
        String(30), nullable=False, default="bidirectional"
    )  # bidirectional | milo_to_microsoft | microsoft_to_milo
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    account: Mapped[MsAccount] = relationship("MsAccount", back_populates="sync_targets")

    __table_args__ = (
        UniqueConstraint("account_id", "target_type", "remote_id", name="uq_ms_sync_targets"),
        Index("ix_ms_sync_targets_account_id", "account_id"),
        Index("ix_ms_sync_targets_type", "target_type"),
    )


# ---------------------------------------------------------------------------
# ms_entity_links — mapping between Milo local entities and Microsoft remote
# ---------------------------------------------------------------------------


class MsEntityLink(Base):
    __tablename__ = "ms_entity_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ms_accounts.id", ondelete="CASCADE"), nullable=False
    )

    # Local entity (Milo side) — NO foreign key to Milo tables
    local_entity_type: Mapped[str] = mapped_column(String(20), nullable=False)  # task | event
    local_entity_id: Mapped[int] = mapped_column(Integer, nullable=False)

    # Remote entity (Microsoft side)
    remote_entity_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # todo_task | calendar_event
    remote_entity_id: Mapped[str] = mapped_column(String(400), nullable=False)
    remote_container_id: Mapped[str | None] = mapped_column(
        String(400), nullable=True
    )  # calendar id / todo list id

    # Change tracking
    remote_etag: Mapped[str | None] = mapped_column(String(200), nullable=True)
    remote_last_modified: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    local_last_modified: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sync_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Deletion tracking
    remote_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    local_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    account: Mapped[MsAccount] = relationship("MsAccount", back_populates="entity_links")

    __table_args__ = (
        UniqueConstraint(
            "account_id", "local_entity_type", "local_entity_id",
            name="uq_ms_entity_links_local",
        ),
        UniqueConstraint(
            "account_id", "remote_entity_type", "remote_entity_id",
            name="uq_ms_entity_links_remote",
        ),
        Index("ix_ms_entity_links_account_id", "account_id"),
        Index("ix_ms_entity_links_local", "local_entity_type", "local_entity_id"),
        Index("ix_ms_entity_links_remote", "remote_entity_type", "remote_entity_id"),
    )


# ---------------------------------------------------------------------------
# ms_sync_state — delta tokens and incremental sync state
# ---------------------------------------------------------------------------


class MsSyncState(Base):
    __tablename__ = "ms_sync_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ms_accounts.id", ondelete="CASCADE"), nullable=False
    )
    resource_type: Mapped[str] = mapped_column(String(20), nullable=False)  # calendar | todo_list
    resource_id: Mapped[str] = mapped_column(String(400), nullable=False)  # calendar/list remote id
    delta_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_full_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sync_window_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sync_window_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        UniqueConstraint(
            "account_id", "resource_type", "resource_id", name="uq_ms_sync_state"
        ),
        Index("ix_ms_sync_state_account_id", "account_id"),
    )


# ---------------------------------------------------------------------------
# ms_sync_runs — history of sync operations
# ---------------------------------------------------------------------------


class MsSyncRun(Base):
    __tablename__ = "ms_sync_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ms_accounts.id", ondelete="CASCADE"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="running"
    )  # running | success | partial | failed
    is_full_sync: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Calendar counters
    calendar_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    calendar_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    calendar_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # To Do counters
    tasks_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tasks_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tasks_deleted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Conflicts and errors
    conflicts_detected: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    account: Mapped[MsAccount] = relationship("MsAccount", back_populates="sync_runs")

    __table_args__ = (
        Index("ix_ms_sync_runs_account_id", "account_id"),
        Index("ix_ms_sync_runs_started_at", "started_at"),
        Index("ix_ms_sync_runs_status", "status"),
    )


# ---------------------------------------------------------------------------
# ms_sync_errors — per-entity errors during sync
# ---------------------------------------------------------------------------


class MsSyncError(Base):
    __tablename__ = "ms_sync_errors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sync_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ms_sync_runs.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ms_accounts.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    local_entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    remote_entity_id: Mapped[str | None] = mapped_column(String(400), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    safe_message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("ix_ms_sync_errors_account_id", "account_id"),
        Index("ix_ms_sync_errors_sync_run_id", "sync_run_id"),
    )


# ---------------------------------------------------------------------------
# ms_sync_conflicts — records when both sides changed since last sync
# ---------------------------------------------------------------------------


class MsSyncConflict(Base):
    __tablename__ = "ms_sync_conflicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ms_accounts.id", ondelete="CASCADE"), nullable=False
    )
    entity_link_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ms_entity_links.id", ondelete="SET NULL"), nullable=True
    )
    entity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    local_entity_id: Mapped[int] = mapped_column(Integer, nullable=False)
    remote_entity_id: Mapped[str] = mapped_column(String(400), nullable=False)

    local_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)   # JSON
    remote_snapshot: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON

    local_modified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    remote_modified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | resolved | ignored
    resolution: Mapped[str | None] = mapped_column(
        String(30), nullable=True
    )  # keep_local | keep_microsoft | merge

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_ms_sync_conflicts_account_id", "account_id"),
        Index("ix_ms_sync_conflicts_status", "status"),
    )


# ---------------------------------------------------------------------------
# ms_subscriptions — Graph change notification subscriptions
# ---------------------------------------------------------------------------


class MsSubscription(Base):
    __tablename__ = "ms_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("ms_accounts.id", ondelete="CASCADE"), nullable=False
    )
    subscription_id: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    resource: Mapped[str] = mapped_column(String(400), nullable=False)
    change_type: Mapped[str] = mapped_column(String(100), nullable=False, default="created,updated,deleted")
    expiration_datetime: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    client_state: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active"
    )  # active | expired | error
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (Index("ix_ms_subscriptions_account_id", "account_id"),)


# ---------------------------------------------------------------------------
# ms_auth_flows — tracks in-progress device code auth flows
# ---------------------------------------------------------------------------


class MsAuthFlow(Base):
    __tablename__ = "ms_auth_flows"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    flow_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    device_code: Mapped[str] = mapped_column(
        Text, nullable=False
    )  # encrypted device code (short-lived)
    user_code: Mapped[str] = mapped_column(String(20), nullable=False)
    verification_uri: Mapped[str] = mapped_column(String(300), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending"
    )  # pending | completed | failed | expired
    account_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ms_accounts.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, onupdate=utcnow
    )

    __table_args__ = (
        Index("ix_ms_auth_flows_flow_id", "flow_id"),
        Index("ix_ms_auth_flows_status", "status"),
    )
