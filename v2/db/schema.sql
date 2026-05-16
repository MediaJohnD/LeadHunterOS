-- LeadHunterOS v2 - PostgreSQL Schema
-- Run: psql $DATABASE_URL < db/schema.sql

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- LEADS
-- ============================================================
CREATE TABLE IF NOT EXISTS leads (
  id                UUID PRIMARY KEY DEFAULT uuid_generate_v4(),

  -- Identity
  full_name         TEXT,
  email             TEXT,
  phone             TEXT,
  linkedin_url      TEXT,
  twitter_handle    TEXT,

  -- Company
  company_name      TEXT,
  company_domain    TEXT,
  company_linkedin  TEXT,
  industry          TEXT,
  employee_count    INTEGER,
  annual_revenue    BIGINT,
  company_location  TEXT,
  hq_country        TEXT DEFAULT 'US',

  -- Role
  title             TEXT,
  seniority         TEXT,
  department        TEXT,

  -- ICP scoring
  icp_score         INTEGER DEFAULT 0 CHECK (icp_score BETWEEN 0 AND 100),
  icp_score_reason  TEXT,
  icp_scored_at     TIMESTAMPTZ,

  -- Lead status
  status            TEXT DEFAULT 'new'
                      CHECK (status IN ('new','qualified','contacted','replied',
                                        'converted','disqualified')),

  -- Signal that triggered discovery
  signal_type       TEXT,  -- 'reddit','news','apollo','manual'
  signal_source     TEXT,
  signal_summary    TEXT,
  raw_signal_data   JSONB DEFAULT '{}',

  -- Enrichment
  enriched          BOOLEAN DEFAULT FALSE,
  enriched_at       TIMESTAMPTZ,
  apollo_data       JSONB DEFAULT '{}',
  hunter_data       JSONB DEFAULT '{}',

  -- Outreach
  last_contacted_at TIMESTAMPTZ,
  reply_received    BOOLEAN DEFAULT FALSE,
  reply_at          TIMESTAMPTZ,
  converted         BOOLEAN DEFAULT FALSE,
  converted_at      TIMESTAMPTZ,
  conversion_value  DECIMAL(12,2),

  -- Meta
  notes             TEXT,
  tags              TEXT[],
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- AGENT RUN LOG
-- ============================================================
CREATE TABLE IF NOT EXISTS agent_runs (
  id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  started_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at TIMESTAMPTZ,
  status      TEXT DEFAULT 'running' CHECK (status IN ('running','success','error')),
  iterations  INTEGER DEFAULT 0,
  leads_found INTEGER DEFAULT 0,
  error_msg   TEXT,
  log         JSONB DEFAULT '[]'  -- array of {thought, action, observation}
);

-- ============================================================
-- SIGNALS (raw, before lead creation)
-- ============================================================
CREATE TABLE IF NOT EXISTS signals (
  id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  source       TEXT NOT NULL,  -- 'reddit','newsapi','apollo_search'
  raw_data     JSONB NOT NULL,
  processed    BOOLEAN DEFAULT FALSE,
  lead_id      UUID REFERENCES leads(id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- VERIFIED LEADS EVIDENCE GRAPH (commercial reality model)
-- ============================================================
CREATE TABLE IF NOT EXISTS verified_leads (
  id                             UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  company_name                   TEXT NOT NULL,
  objective_hash                 TEXT NOT NULL,
  signal_count                   INTEGER NOT NULL CHECK (signal_count >= 20),
  budget_score                   NUMERIC(5,2) NOT NULL CHECK (budget_score BETWEEN 0 AND 100),
  urgency_score                  NUMERIC(5,2) NOT NULL CHECK (urgency_score BETWEEN 0 AND 100),
  politics_score                 NUMERIC(5,2) NOT NULL CHECK (politics_score BETWEEN 0 AND 100),
  procurement_score              NUMERIC(5,2) NOT NULL CHECK (procurement_score BETWEEN 0 AND 100),
  vendor_maturity_score          NUMERIC(5,2) NOT NULL CHECK (vendor_maturity_score BETWEEN 0 AND 100),
  implementation_readiness_score NUMERIC(5,2) NOT NULL CHECK (implementation_readiness_score BETWEEN 0 AND 100),
  timing_score                   NUMERIC(5,2) NOT NULL CHECK (timing_score BETWEEN 0 AND 100),
  revenue_probability_score      NUMERIC(5,2) NOT NULL CHECK (revenue_probability_score BETWEEN 0 AND 100),
  evidence_summary               TEXT NOT NULL,
  created_at                     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS lead_signal_events (
  signal_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  verified_lead_id  UUID NOT NULL REFERENCES verified_leads(id) ON DELETE CASCADE,
  source            TEXT NOT NULL,
  signal_type       TEXT NOT NULL,
  confidence        NUMERIC(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  source_url        TEXT NOT NULL,
  observed_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  payload           JSONB NOT NULL DEFAULT '{}',
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- ============================================================
-- INDEXES
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_leads_email    ON leads(email) WHERE email IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_leads_domain   ON leads(company_domain) WHERE company_domain IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_leads_status   ON leads(status);
CREATE INDEX IF NOT EXISTS idx_leads_icp      ON leads(icp_score DESC) WHERE icp_score > 0;
CREATE INDEX IF NOT EXISTS idx_leads_created  ON leads(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source);
CREATE INDEX IF NOT EXISTS idx_signals_unproc ON signals(processed) WHERE processed = FALSE;
CREATE INDEX IF NOT EXISTS idx_verified_scores ON verified_leads(budget_score DESC, urgency_score DESC);
CREATE INDEX IF NOT EXISTS idx_verified_objective_hash ON verified_leads(objective_hash);
CREATE INDEX IF NOT EXISTS idx_signal_events_lead ON lead_signal_events(verified_lead_id);
CREATE INDEX IF NOT EXISTS idx_signal_events_source ON lead_signal_events(source);

-- ============================================================
-- AUTO-UPDATE updated_at
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS leads_updated_at ON leads;
CREATE TRIGGER leads_updated_at
  BEFORE UPDATE ON leads
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();
