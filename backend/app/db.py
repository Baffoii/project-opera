from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    create_engine,
    event,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """SQLite drops tzinfo; always hand back aware UTC datetimes."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class Base(DeclarativeBase):
    pass


class UploadRow(Base):
    __tablename__ = "uploads"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    storage_key: Mapped[str] = mapped_column(String(64))
    sha256: Mapped[str] = mapped_column(String(64))
    phash: Mapped[str] = mapped_column(String(32))
    mime: Mapped[str] = mapped_column(String(32))
    bytes: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    analyses: Mapped[list["AnalysisRow"]] = relationship(
        back_populates="upload", cascade="all, delete-orphan", passive_deletes=True
    )


class AnalysisRow(Base):
    __tablename__ = "analyses"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    upload_id: Mapped[str] = mapped_column(ForeignKey("uploads.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16))
    abstain_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    model_kind: Mapped[str] = mapped_column(String(8))
    clues_kind: Mapped[str] = mapped_column(String(8), default="none")
    versions: Mapped[dict] = mapped_column(JSON, default=dict)
    clues: Mapped[list] = mapped_column(JSON, default=list)
    region_guesses: Mapped[list] = mapped_column(JSON, default=list)
    provenance: Mapped[list] = mapped_column(JSON, default=list)
    notices: Mapped[list] = mapped_column(JSON, default=list)
    latency: Mapped[dict] = mapped_column(JSON, default=dict)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime(), index=True)
    upload: Mapped[UploadRow] = relationship(back_populates="analyses")
    candidates: Mapped[list["CandidateRow"]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="CandidateRow.rank",
    )


class CandidateRow(Base):
    __tablename__ = "candidates"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    analysis_id: Mapped[str] = mapped_column(ForeignKey("analyses.id", ondelete="CASCADE"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    # lat/lon are the source of truth. On PostgreSQL `ensure_postgis` adds a generated geography(Point) column.
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    label: Mapped[str | None] = mapped_column(String(300), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(8), nullable=True)
    score: Mapped[float] = mapped_column(Float)
    confidence_band: Mapped[str] = mapped_column(String(8))
    uncalibrated: Mapped[bool] = mapped_column(Boolean, default=True)
    uncertainty_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_model: Mapped[str] = mapped_column(String(64))
    context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    analysis: Mapped[AnalysisRow] = relationship(back_populates="candidates")


class EvaluationRow(Base):
    __tablename__ = "evaluations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    config_hash: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(16))
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    slices: Mapped[dict] = mapped_column(JSON, default=dict)
    started_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)


class EvaluationItemRow(Base):
    __tablename__ = "evaluation_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[str] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), index=True
    )
    image_id: Mapped[str] = mapped_column(String(64))
    truth_lat: Mapped[float] = mapped_column(Float)
    truth_lon: Mapped[float] = mapped_column(Float)
    top1_lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    top1_lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    error_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    in_top5: Mapped[dict] = mapped_column(JSON, default=dict)
    band: Mapped[str | None] = mapped_column(String(8), nullable=True)
    abstained: Mapped[bool] = mapped_column(Boolean, default=False)
    latency_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)


class AuditLogRow(Base):
    """Request metadata only. Never image bytes, filenames, clue text or any image-derived content."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(32), index=True)
    endpoint: Mapped[str] = mapped_column(String(120))
    client_hash: Mapped[str] = mapped_column(String(32))
    model: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)


def make_engine(database_url: str) -> Engine:
    kwargs: dict = {}
    if database_url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
        if ":memory:" in database_url or database_url in ("sqlite://", "sqlite:///"):
            kwargs["poolclass"] = StaticPool
    engine = create_engine(database_url, **kwargs)
    if database_url.startswith("sqlite"):

        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _record):  # cascading deletes need this on SQLite
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


def init_db(engine: Engine) -> None:
    """Create tables. This is a deliberately simple migration story (create_all); see docs/DECISIONS.md."""
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    if engine.dialect.name == "postgresql":
        ensure_postgis(engine)


def _add_missing_columns(engine: Engine) -> None:
    """create_all never alters existing tables; add the few nullable columns introduced after M2."""
    from sqlalchemy import inspect

    inspector = inspect(engine)
    for table, column, ddl in (("candidates", "context", "JSON"),):
        if column not in {c["name"] for c in inspector.get_columns(table)}:
            with engine.begin() as conn:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))


def ensure_postgis(engine: Engine) -> None:
    """PostgreSQL only; UNTESTED in this build (Docker unavailable). Adds geography(Point) mirrors of lat/lon."""
    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        for table in ("candidates",):
            conn.execute(
                text(
                    f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS geom geography(Point,4326) "
                    "GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(lon, lat), 4326)::geography) STORED"
                )
            )
            conn.execute(text(f"CREATE INDEX IF NOT EXISTS {table}_geom_gix ON {table} USING GIST (geom)"))


def make_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(engine, expire_on_commit=False)


@contextmanager
def session_scope(factory: sessionmaker) -> Iterator:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
