import { NextResponse } from "next/server";
import { hermesUrl, safeFetch } from "../_lib/upstream";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const upstream = await safeFetch(hermesUrl("/api/tasks"), { method: "GET" });
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown error";
    return NextResponse.json({ error: "tasks_proxy_failed", detail }, { status: 502 });
  }
}

