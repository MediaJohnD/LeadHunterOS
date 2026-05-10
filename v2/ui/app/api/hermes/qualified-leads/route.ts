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
};

function parsePythonJson(raw: string): LeadRow[] {
  try {
    const data = JSON.parse(raw) as unknown;
    return Array.isArray(data) ? (data as LeadRow[]) : [];
  } catch {
    return [];
  }
}

export async function GET() {
  try {
    const repoV2Path = path.resolve(process.cwd(), "..");
    const dbPath = path.join(repoV2Path, "leadhunter.db");
    if (!existsSync(dbPath)) {
      return NextResponse.json({ leads: [], source: "none" }, { status: 200 });
    }

    const py = [
      "import sqlite3, json",
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
      "rows = [dict(r) for r in cur.fetchall()]",
      "con.close()",
      "print(json.dumps(rows, ensure_ascii=True))",
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

    const leads = parsePythonJson(out.stdout ?? "");
    return NextResponse.json({ leads, source: "sqlite" }, { status: 200 });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown error";
    return NextResponse.json({ error: "qualified_leads_proxy_failed", detail }, { status: 502 });
  }
}

