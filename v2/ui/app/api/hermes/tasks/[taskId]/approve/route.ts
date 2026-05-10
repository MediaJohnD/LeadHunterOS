import { NextResponse } from "next/server";
import { hermesUrl, safeFetch } from "../../../_lib/upstream";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(
  _request: Request,
  { params }: { params: Promise<{ taskId: string }> },
) {
  const { taskId } = await params;
  if (!taskId?.trim()) {
    return NextResponse.json({ error: "taskId is required" }, { status: 400 });
  }

  try {
    const upstream = await safeFetch(
      hermesUrl(`/api/tasks/${encodeURIComponent(taskId)}/approve`),
      { method: "POST" },
    );
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown error";
    return NextResponse.json(
      { error: "approve_proxy_failed", detail },
      { status: 502 },
    );
  }
}

