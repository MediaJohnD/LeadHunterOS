-- LeadHunterOS PostgreSQL Schema
-- Auto-initialized by Docker Compose on first run
-- Tables: leads, signals, campaigns, outreach_messages, nurture_queue

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================
-- LEADS TABLE
-- Stores enriched lead profiles
-- ============================================================
CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Identity
    name VARCHAR(255),
    first_name VARCHAR(100),
    last_name VARCHAR(100),
    title VARCHAR(255),
    email VARCHAR(255),
    linkedin_url VARCHAR(500),
    twitter_handle VARCHAR(100),
    phone VARCHAR(50),

    -- Company
    company VARCHAR(255),
    company_domain VARCHAR(255),
    company_size INTEGER,
    industry VARCHAR(255),
    location VARCHAR(255),
    funding_stage VARCHAR(100),

    -- ICP Scoring
    icp_score INTEGER DEFAULT 0 CHECK (icp_score >= 0 AND icp_score <= 100),
    icp_fit_reason TEXT,
    urgency VARCHAR(20) DEFAULT 'low' CHECK (urgency IN ('low', 'medium', 'high')),
    recommended_channel VARCHAR(20) DEFAULT 'email',
    lead_status VARCHAR(50) DEFAULT 'new'
        CHECK (lead_status IN ('new', 'enriched', 'scored', 'immediate_outreach', 'nurture_queue', 'contacted', 'replied', 'meeting_booked', 'disqualified')),

    -- Source tracking
    signal_source VARCHAR(50),  -- reddit/twitter/linkedin/web/google_maps
    source_url VARCHAR(1000),
    source_id VARCHAR(255),

    -- Enrichment metadata
    enriched_via VARCHAR(100),  -- apollo/hunter/pdl/clearbit
    enrichment_confidence FLOAT,

    -- Dedup
    UNIQUE (email),
    UNIQUE (linkedin_url)
);

CREATE INDEX idx_leads_icp_score ON leads(icp_score DESC);
CREATE INDEX idx_leads_status ON leads(lead_status);
CREATE INDEX idx_leads_created ON leads(created_at DESC);
CREATE INDEX idx_leads_company ON leads(company);

-- ============================================================
-- SIGNALS TABLE
-- Raw intent signals before enrichment
-- ============================================================
CREATE TABLE IF NOT EXISTS signals (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMPTZ DEFAULT NOW(),

    source VARCHAR(50) NOT NULL,  -- reddit/twitter/linkedin/web
    source_id VARCHAR(255),        -- External ID for dedup
    signal_type VARCHAR(100),      -- reddit_post/tweet/linkedin_activity/news

    -- Content
    title VARCHAR(1000),
    text TEXT,
    url VARCHAR(2000),
    author_username VARCHAR(255),
    author_url VARCHAR(500),

    -- Signal strength
    intent_score INTEGER DEFAULT 0,
    matched_patterns JSONB DEFAULT '[]',

    -- Processing status
    processed BOOLEAN DEFAULT FALSE,
    lead_id UUID REFERENCES leads(id) ON DELETE SET NULL,

    -- Raw metadata
    metadata JSONB DEFAULT '{}',

    UNIQUE (source, source_id)
);

CREATE INDEX idx_signals_source ON signals(source);
CREATE INDEX idx_signals_processed ON signals(processed);
CREATE INDEX idx_signals_created ON signals(created_at DESC);

-- ============================================================
-- CAMPAIGNS TABLE
-- Outreach campaigns / sequences
-- ============================================================
CREATE TABLE IF NOT EXISTS campaigns (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    name VARCHAR(255) NOT NULL,
    description TEXT,
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'paused', 'completed', 'draft')),

    -- Sender config
    sender_name VARCHAR(255),
    sender_email VARCHAR(255),
    sender_company VARCHAR(255),
    value_proposition TEXT,

    -- Stats
    leads_enrolled INTEGER DEFAULT 0,
    messages_sent INTEGER DEFAULT 0,
    replies_received INTEGER DEFAULT 0,
    meetings_booked INTEGER DEFAULT 0
);

-- ============================================================
-- OUTREACH_MESSAGES TABLE
-- Individual outreach messages sent
-- ============================================================
CREATE TABLE IF NOT EXISTS outreach_messages (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    sent_at TIMESTAMPTZ,

    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    campaign_id UUID REFERENCES campaigns(id) ON DELETE SET NULL,

    channel VARCHAR(20) NOT NULL CHECK (channel IN ('linkedin', 'email', 'twitter')),
    message_type VARCHAR(50) DEFAULT 'opener',  -- opener/followup/nurture
    sequence_step INTEGER DEFAULT 1,

    subject VARCHAR(500),  -- For email
    body TEXT NOT NULL,

    status VARCHAR(50) DEFAULT 'draft'
        CHECK (status IN ('draft', 'queued', 'sent', 'delivered', 'opened', 'replied', 'bounced', 'failed')),

    -- AI generation metadata
    generated_by VARCHAR(50) DEFAULT 'claude_sonnet',
    generation_prompt TEXT,

    -- Response tracking
    replied BOOLEAN DEFAULT FALSE,
    replied_at TIMESTAMPTZ,
    reply_text TEXT
);

CREATE INDEX idx_messages_lead ON outreach_messages(lead_id);
CREATE INDEX idx_messages_status ON outreach_messages(status);
CREATE INDEX idx_messages_sent ON outreach_messages(sent_at DESC);

-- ============================================================
-- NURTURE_QUEUE TABLE
-- Leads in nurture flow (score 41-69)
-- ============================================================
CREATE TABLE IF NOT EXISTS nurture_queue (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    next_touchpoint_at TIMESTAMPTZ,

    lead_id UUID NOT NULL REFERENCES leads(id) ON DELETE CASCADE UNIQUE,
    touchpoint_count INTEGER DEFAULT 0,
    last_touchpoint_at TIMESTAMPTZ,
    status VARCHAR(50) DEFAULT 'active' CHECK (status IN ('active', 'upgraded', 'removed'))
);

CREATE INDEX idx_nurture_next ON nurture_queue(next_touchpoint_at);
CREATE INDEX idx_nurture_status ON nurture_queue(status);

-- ============================================================
-- TRIGGER: Auto-update updated_at
-- ============================================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_leads_updated_at
    BEFORE UPDATE ON leads
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_campaigns_updated_at
    BEFORE UPDATE ON campaigns
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Seed a default campaign
INSERT INTO campaigns (name, description, status)
VALUES (
    'Default LeadHunterOS Campaign',
    'Auto-created default campaign for LeadHunterOS outreach',
    'active'
) ON CONFLICT DO NOTHING;
