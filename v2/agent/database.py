"""Persistence helpers for LeadHunterOS agent tools."""

from __future__ import annotations

import json
import uuid
import csv
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

import config


def _engine() -> Engine:
    connect_args = {"check_same_thread": False} if config.DATABASE_URL.startswith("sqlite") else {}
    return create_engine(config.DATABASE_URL, future=True, connect_args=connect_args)


def _sqlite_fallback_engine() -> Engine:
    return create_engine("sqlite:///./leadhunter.db", future=True, connect_args={"check_same_thread": False})


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=True)


def _ensure_sqlite_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS leads (
              id TEXT PRIMARY KEY,
              full_name TEXT,
              email TEXT,
              phone TEXT,
              linkedin_url TEXT,
              twitter_handle TEXT,
              company_name TEXT,
              company_domain TEXT,
              company_linkedin TEXT,
              industry TEXT,
              employee_count INTEGER,
              annual_revenue INTEGER,
              company_location TEXT,
              hq_country TEXT DEFAULT 'US',
              title TEXT,
              seniority TEXT,
              department TEXT,
              icp_score INTEGER DEFAULT 0,
              icp_score_reason TEXT,
              icp_scored_at TEXT,
              status TEXT DEFAULT 'new',
              signal_type TEXT,
              signal_source TEXT,
              signal_summary TEXT,
              raw_signal_data TEXT DEFAULT '{}',
              enriched INTEGER DEFAULT 0,
              enriched_at TEXT,
              apollo_data TEXT DEFAULT '{}',
              hunter_data TEXT DEFAULT '{}',
              last_contacted_at TEXT,
              reply_received INTEGER DEFAULT 0,
              reply_at TEXT,
              converted INTEGER DEFAULT 0,
              converted_at TEXT,
              conversion_value REAL,
              notes TEXT,
              tags TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_leads_domain ON leads(company_domain)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_leads_icp ON leads(icp_score)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS lead_entities (
              entity_id TEXT PRIMARY KEY,
              entity_type TEXT NOT NULL,
              display_name TEXT,
              canonical_key TEXT NOT NULL,
              confidence REAL DEFAULT 0.0,
              metadata TEXT DEFAULT '{}',
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_entities_key ON lead_entities(canonical_key)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS entity_edges (
              edge_id TEXT PRIMARY KEY,
              from_entity_id TEXT NOT NULL,
              to_entity_id TEXT NOT NULL,
              relation_type TEXT NOT NULL,
              confidence REAL DEFAULT 0.0,
              source_tool TEXT,
              source_url TEXT,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_edges_from ON entity_edges(from_entity_id)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_edges_to ON entity_edges(to_entity_id)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS run_health (
              event_id TEXT PRIMARY KEY,
              observed_at TEXT NOT NULL,
              component TEXT NOT NULL,
              tool_name TEXT,
              source_name TEXT,
              ok INTEGER NOT NULL,
              latency_ms INTEGER,
              error_text TEXT,
              context TEXT DEFAULT '{}'
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_run_health_component ON run_health(component)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_run_health_tool ON run_health(tool_name)"))
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS suppressions (
              suppression_id TEXT PRIMARY KEY,
              suppression_type TEXT NOT NULL,
              suppression_value TEXT NOT NULL,
              reason TEXT,
              active INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("CREATE INDEX IF NOT EXISTS idx_suppressions_type_value ON suppressions(suppression_type, suppression_value)"))
        # Best-effort columns for attribution fields (safe for repeated runs).
        for ddl in [
            "ALTER TABLE leads ADD COLUMN attribution_source_family TEXT",
            "ALTER TABLE leads ADD COLUMN attribution_confidence REAL",
            "ALTER TABLE leads ADD COLUMN decision_reason TEXT",
        ]:
            try:
                conn.execute(text(ddl))
            except Exception:
                pass


def ensure_schema() -> None:
    """Create the SQLite schema when using the zero-config default database."""
    engine = _engine()
    if engine.dialect.name == "sqlite":
        _ensure_sqlite_schema(engine)


def save_public_lead(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist a public lead payload into the canonical leads table."""
    engine = _engine()
    ensure_schema()

    now = datetime.now(timezone.utc).isoformat()
    signals = payload.get("signals") or []
    signal_summary = "; ".join(str(item) for item in signals[:5]) if isinstance(signals, list) else str(signals)
    raw_signal_data = {
        "public_payload": payload,
        "source_url": payload.get("source_url"),
        "observed_at": payload.get("observed_at"),
    }
    row = {
        "id": str(uuid.uuid4()),
        "full_name": payload.get("name"),
        "company_name": payload.get("company"),
        "company_domain": payload.get("company_domain"),
        "industry": payload.get("industry"),
        "employee_count": payload.get("company_size"),
        "company_location": payload.get("work_location"),
        "title": payload.get("title"),
        "icp_score": int(payload.get("icp_score") or 0),
        "icp_score_reason": payload.get("personalized_opener"),
        "icp_scored_at": now,
        "status": "qualified" if int(payload.get("icp_score") or 0) >= getattr(config, "ICP_MIN_SCORE", 70) else "new",
        "signal_type": payload.get("source_type"),
        "signal_source": payload.get("source_url"),
        "signal_summary": signal_summary[:1000],
        "raw_signal_data": _json(raw_signal_data),
        "attribution_source_family": payload.get("source_type"),
        "attribution_confidence": float(payload.get("evidence_confidence_score") or payload.get("evidence_score") or 0),
        "decision_reason": payload.get("decision_reason") or payload.get("icp_score_reason"),
        "notes": payload.get("headline"),
        "created_at": now,
        "updated_at": now,
    }

    fallback_used = False
    try:
        _insert_lead_row(engine, row)
        _upsert_entity_graph(engine, row)
    except SQLAlchemyError:
        if engine.dialect.name == "sqlite":
            raise
        fallback_used = True
        fallback_engine = _sqlite_fallback_engine()
        _ensure_sqlite_schema(fallback_engine)
        _insert_lead_row(fallback_engine, row)
        _upsert_entity_graph(fallback_engine, row)

    return {
        "id": row["id"],
        "status": row["status"],
        "saved_at": now,
        "database": "sqlite_fallback" if fallback_used else engine.dialect.name,
    }


def _insert_lead_row(engine: Engine, row: dict[str, Any]) -> None:
    with engine.begin() as conn:
        raw_expr = "CAST(:raw_signal_data AS JSONB)" if engine.dialect.name == "postgresql" else ":raw_signal_data"
        conn.execute(text(f"""
            INSERT INTO leads (
              id, full_name, company_name, company_domain, industry, employee_count,
              company_location, title, icp_score, icp_score_reason, icp_scored_at,
              status, signal_type, signal_source, signal_summary, raw_signal_data,
              attribution_source_family, attribution_confidence, decision_reason,
              notes, created_at, updated_at
            ) VALUES (
              :id, :full_name, :company_name, :company_domain, :industry, :employee_count,
              :company_location, :title, :icp_score, :icp_score_reason, :icp_scored_at,
              :status, :signal_type, :signal_source, :signal_summary, {raw_expr},
              :attribution_source_family, :attribution_confidence, :decision_reason,
              :notes, :created_at, :updated_at
            )
        """), row)


def _upsert_entity_graph(engine: Engine, row: dict[str, Any]) -> None:
    person_key = (row.get("full_name") or "").strip().lower()
    company_key = (row.get("company_domain") or row.get("company_name") or "").strip().lower()
    if not person_key or not company_key:
        return
    person_id = str(uuid.uuid4())
    company_id = str(uuid.uuid4())
    edge_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO lead_entities (entity_id, entity_type, display_name, canonical_key, confidence, metadata, created_at, updated_at)
                VALUES (:id, :etype, :name, :ckey, :conf, :meta, :now, :now)
                ON CONFLICT(canonical_key) DO UPDATE SET
                    display_name = excluded.display_name,
                    confidence = CASE WHEN excluded.confidence > lead_entities.confidence THEN excluded.confidence ELSE lead_entities.confidence END,
                    updated_at = excluded.updated_at
                """
            ),
            {
                "id": person_id,
                "etype": "person",
                "name": row.get("full_name"),
                "ckey": person_key,
                "conf": 0.7,
                "meta": _json({"title": row.get("title")}),
                "now": now,
            },
        )
        conn.execute(
            text(
                """
                INSERT INTO lead_entities (entity_id, entity_type, display_name, canonical_key, confidence, metadata, created_at, updated_at)
                VALUES (:id, :etype, :name, :ckey, :conf, :meta, :now, :now)
                ON CONFLICT(canonical_key) DO UPDATE SET
                    display_name = excluded.display_name,
                    confidence = CASE WHEN excluded.confidence > lead_entities.confidence THEN excluded.confidence ELSE lead_entities.confidence END,
                    updated_at = excluded.updated_at
                """
            ),
            {
                "id": company_id,
                "etype": "company",
                "name": row.get("company_name"),
                "ckey": company_key,
                "conf": 0.8,
                "meta": _json({"industry": row.get("industry")}),
                "now": now,
            },
        )
        person_entity_id = conn.execute(
            text("SELECT entity_id FROM lead_entities WHERE canonical_key = :ckey LIMIT 1"),
            {"ckey": person_key},
        ).scalar()
        company_entity_id = conn.execute(
            text("SELECT entity_id FROM lead_entities WHERE canonical_key = :ckey LIMIT 1"),
            {"ckey": company_key},
        ).scalar()
        if person_entity_id and company_entity_id:
            conn.execute(
                text(
                    """
                    INSERT INTO entity_edges (edge_id, from_entity_id, to_entity_id, relation_type, confidence, source_tool, source_url, created_at)
                    VALUES (:edge_id, :from_id, :to_id, :rtype, :conf, :tool, :url, :created_at)
                    """
                ),
                {
                    "edge_id": edge_id,
                    "from_id": person_entity_id,
                    "to_id": company_entity_id,
                    "rtype": "works_at",
                    "conf": 0.75,
                    "tool": row.get("signal_type"),
                    "url": row.get("signal_source"),
                    "created_at": now,
                },
            )


def export_latest_leads_csv(path: str, limit: int = 200) -> dict[str, Any]:
    """Export recent leads to CSV for operator review and downstream workflows."""
    engine = _engine()
    ensure_schema()
    query = text(
        """
        SELECT id, full_name, title, company_name, company_domain, industry,
               employee_count, company_location, icp_score, status,
               signal_type, signal_source, signal_summary,
               attribution_source_family, attribution_confidence, decision_reason, created_at
        FROM leads
        ORDER BY created_at DESC
        LIMIT :limit
        """
    )

    fallback_used = False
    try:
        with engine.begin() as conn:
            rows = conn.execute(query, {"limit": max(1, int(limit))}).mappings().all()
    except SQLAlchemyError:
        if engine.dialect.name == "sqlite":
            raise
        fallback_used = True
        fallback_engine = _sqlite_fallback_engine()
        _ensure_sqlite_schema(fallback_engine)
        with fallback_engine.begin() as conn:
            rows = conn.execute(query, {"limit": max(1, int(limit))}).mappings().all()

    headers = [
        "id", "full_name", "title", "company_name", "company_domain", "industry",
        "employee_count", "company_location", "icp_score", "status",
        "signal_type", "signal_source", "signal_summary",
        "attribution_source_family", "attribution_confidence", "decision_reason", "created_at",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({h: row.get(h, "") for h in headers})

    return {
        "ok": True,
        "path": path,
        "rows": len(rows),
        "database": "sqlite_fallback" if fallback_used else engine.dialect.name,
    }


def record_tool_health_event(
    *,
    component: str,
    tool_name: str = "",
    source_name: str = "",
    ok: bool,
    latency_ms: int | None = None,
    error_text: str = "",
    context: dict[str, Any] | None = None,
) -> None:
    engine = _engine()
    ensure_schema()
    row = {
        "event_id": str(uuid.uuid4()),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "component": component,
        "tool_name": tool_name,
        "source_name": source_name,
        "ok": 1 if ok else 0,
        "latency_ms": int(latency_ms) if latency_ms is not None else None,
        "error_text": (error_text or "")[:1000],
        "context": _json(context or {}),
    }
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO run_health (
                      event_id, observed_at, component, tool_name, source_name, ok, latency_ms, error_text, context
                    ) VALUES (
                      :event_id, :observed_at, :component, :tool_name, :source_name, :ok, :latency_ms, :error_text, :context
                    )
                    """
                ),
                row,
            )
    except SQLAlchemyError:
        if engine.dialect.name != "sqlite":
            fallback_engine = _sqlite_fallback_engine()
            _ensure_sqlite_schema(fallback_engine)
            with fallback_engine.begin() as conn:
                conn.execute(
                    text(
                        """
                        INSERT INTO run_health (
                          event_id, observed_at, component, tool_name, source_name, ok, latency_ms, error_text, context
                        ) VALUES (
                          :event_id, :observed_at, :component, :tool_name, :source_name, :ok, :latency_ms, :error_text, :context
                        )
                        """
                    ),
                    row,
                )


def get_tool_failure_penalty(tool_name: str, source_name: str = "", window: int = 100) -> int:
    engine = _engine()
    ensure_schema()
    try:
        with engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT ok
                    FROM run_health
                    WHERE tool_name = :tool_name
                      AND (:source_name = '' OR source_name = :source_name)
                    ORDER BY observed_at DESC
                    LIMIT :window
                    """
                ),
                {"tool_name": tool_name, "source_name": source_name, "window": max(10, int(window))},
            ).all()
    except SQLAlchemyError:
        return 0
    if not rows:
        return 0
    total = len(rows)
    failures = sum(1 for row in rows if int(row[0] or 0) == 0)
    fail_rate = failures / max(1, total)
    return int(min(20, round(fail_rate * 20)))


def is_suppressed(suppression_type: str, suppression_value: str) -> bool:
    value = (suppression_value or "").strip().lower()
    if not value:
        return False
    engine = _engine()
    ensure_schema()
    try:
        with engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    SELECT 1 FROM suppressions
                    WHERE suppression_type = :stype
                      AND suppression_value = :svalue
                      AND active = 1
                    LIMIT 1
                    """
                ),
                {"stype": suppression_type, "svalue": value},
            ).first()
            return bool(row)
    except SQLAlchemyError:
        return False
