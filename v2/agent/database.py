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
        "notes": payload.get("headline"),
        "created_at": now,
        "updated_at": now,
    }

    fallback_used = False
    try:
        _insert_lead_row(engine, row)
    except SQLAlchemyError:
        if engine.dialect.name == "sqlite":
            raise
        fallback_used = True
        fallback_engine = _sqlite_fallback_engine()
        _ensure_sqlite_schema(fallback_engine)
        _insert_lead_row(fallback_engine, row)

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
              notes, created_at, updated_at
            ) VALUES (
              :id, :full_name, :company_name, :company_domain, :industry, :employee_count,
              :company_location, :title, :icp_score, :icp_score_reason, :icp_scored_at,
              :status, :signal_type, :signal_source, :signal_summary, {raw_expr},
              :notes, :created_at, :updated_at
            )
        """), row)


def export_latest_leads_csv(path: str, limit: int = 200) -> dict[str, Any]:
    """Export recent leads to CSV for operator review and downstream workflows."""
    engine = _engine()
    ensure_schema()
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, full_name, title, company_name, company_domain, industry,
                       employee_count, company_location, icp_score, status,
                       signal_type, signal_source, signal_summary, created_at
                FROM leads
                ORDER BY created_at DESC
                LIMIT :limit
                """
            ),
            {"limit": max(1, int(limit))},
        ).mappings().all()

    headers = [
        "id", "full_name", "title", "company_name", "company_domain", "industry",
        "employee_count", "company_location", "icp_score", "status",
        "signal_type", "signal_source", "signal_summary", "created_at",
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        for row in rows:
            writer.writerow({h: row.get(h, "") for h in headers})

    return {"ok": True, "path": path, "rows": len(rows)}
