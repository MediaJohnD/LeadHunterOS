import { NextResponse } from "next/server";
import { existsSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type LeadRow = {
  id: string;
  full_name: string;
  title: string;
  company_name: string;
  company_domain: string;
  icp_score: number;
  status: string;
  signal_summary: string;
  attribution_confidence: number;
  decision_reason: string;
  created_at: string;
  signal_count: number;
};

export async function GET() {
  try {
    const repoV2Path = path.resolve(process.cwd(), "..");
    const dbPath = path.join(repoV2Path, "leadhunter.db");
    if (!existsSync(dbPath)) {
      return NextResponse.json({ leads: [], source: "none" }, { status: 200 });
    }

    const py = [
      "import sqlite3, json",
      "from collections import OrderedDict",
      "con = sqlite3.connect('leadhunter.db')",
      "con.row_factory = sqlite3.Row",
      "cur = con.cursor()",
      "cur.execute(\"\"\"",
      "SELECT id, full_name, title, company_name, company_domain,",
      "       COALESCE(icp_score,0) as icp_score,",
      "       COALESCE(status,'new') as status,",
      "       COALESCE(signal_summary,'') as signal_summary,",
      "       COALESCE(attribution_confidence,0) as attribution_confidence,",
      "       COALESCE(decision_reason,'') as decision_reason,",
      "       COALESCE(created_at,'') as created_at",
      "FROM leads",
      "ORDER BY datetime(created_at) DESC",
      "LIMIT 100",
      "\"\"\")",
      "rows = []",
      "for r in cur.fetchall():",
      "  row = dict(r)",
      "  signal_count = 0",
      "  raw = row.get('raw_signal_data')",
      "  if raw:",
      "    try:",
      "      parsed = json.loads(raw)",
      "      payload = parsed.get('public_payload', {}) if isinstance(parsed, dict) else {}",
      "      signals = payload.get('signals', []) if isinstance(payload, dict) else []",
      "      if isinstance(signals, list):",
      "        signal_count = len([s for s in signals if str(s).strip()])",
      "    except Exception:",
      "      signal_count = 0",
      "  row['signal_count'] = signal_count",
      "  rows.append(row)",
      "",
      "cur.execute(\"\"\"",
      "SELECT DATE(created_at) as day, COUNT(*) as leads",
      "FROM leads",
      "WHERE created_at IS NOT NULL AND created_at != ''",
      "GROUP BY DATE(created_at)",
      "ORDER BY day DESC",
      "LIMIT 14",
      "\"\"\")",
      "velocity = [dict(r) for r in cur.fetchall()][::-1]",
      "",
      "cur.execute(\"\"\"",
      "SELECT component, tool_name, source_name, ok, COALESCE(latency_ms,0) as latency_ms, observed_at",
      "FROM run_health",
      "ORDER BY datetime(observed_at) DESC",
      "LIMIT 100",
      "\"\"\")",
      "health_rows = [dict(r) for r in cur.fetchall()]",
      "latest_by_tool = OrderedDict()",
      "for hr in health_rows:",
      "  key = hr.get('tool_name') or hr.get('component') or 'unknown'",
      "  if key not in latest_by_tool:",
      "    latest_by_tool[key] = hr",
      "runtime = []",
      "for key, hr in list(latest_by_tool.items())[:6]:",
      "  runtime.append({",
      "    'lane': key,",
      "    'status': 'Healthy' if int(hr.get('ok', 0)) == 1 else 'Degraded',",
      "    'latency': f\"{int(hr.get('latency_ms',0))}ms\" if int(hr.get('latency_ms',0)) > 0 else 'n/a'",
      "  })",
      "",
      "qualified = [r for r in rows if int(r.get('icp_score', 0) or 0) >= 70]",
      "avg_conf = int(round(sum(int(r.get('icp_score', 0) or 0) for r in qualified) / len(qualified))) if qualified else 0",
      "avg_signals = int(round(sum(int(r.get('signal_count', 0) or 0) for r in qualified) / len(qualified))) if qualified else 0",
      "kpis = [",
      "  {'metric': 'Qualified Leads (DB)', 'value': len(qualified)},",
      "  {'metric': 'Avg Confidence', 'value': avg_conf},",
      "  {'metric': 'Avg Signals', 'value': avg_signals},",
      "  {'metric': 'Saved (14d)', 'value': sum(int(v.get('leads', 0)) for v in velocity)},",
      "]",
      "executive_feed = []",
      "for r in qualified[:8]:",
      "  reason = (r.get('decision_reason') or r.get('signal_summary') or '').strip()",
      "  if not reason:",
      "    reason = 'Qualified and saved to lead store.'",
      "  executive_feed.append(f\"{r.get('company_name','Unknown')}: {reason}\")",
      "",
      "con.close()",
      "print(json.dumps({",
      "  'leads': rows,",
      "  'kpis': kpis,",
      "  'runtime': runtime,",
      "  'executive_feed': executive_feed,",
      "  'velocity': velocity,",
      "}, ensure_ascii=True))",
    ].join("\n");

    const out = spawnSync("python", ["-c", py], {
      cwd: repoV2Path,
      encoding: "utf-8",
      timeout: 15000,
    });

    if (out.status !== 0) {
      return NextResponse.json(
        {
          error: "qualified_leads_query_failed",
          detail: out.stderr?.trim() || "python query failed",
        },
        { status: 502 },
      );
    }

    const payload = JSON.parse(out.stdout ?? "{}") as {
      leads?: LeadRow[];
      kpis?: Array<{ metric: string; value: string | number }>;
      runtime?: Array<{ lane: string; status: "Healthy" | "Degraded"; latency: string }>;
      executive_feed?: string[];
      velocity?: Array<{ day: string; leads: number }>;
    };
    return NextResponse.json(
      {
        leads: payload.leads ?? [],
        kpis: payload.kpis ?? [],
        runtime: payload.runtime ?? [],
        executive_feed: payload.executive_feed ?? [],
        velocity: payload.velocity ?? [],
        source: "sqlite",
      },
      { status: 200 },
    );
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown error";
    return NextResponse.json({ error: "qualified_leads_proxy_failed", detail }, { status: 502 });
  }
}
