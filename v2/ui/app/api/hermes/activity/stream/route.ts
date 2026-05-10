import { NextResponse } from "next/server";
import { hermesUrl, safeFetch } from "../../_lib/upstream";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const upstream = await safeFetch(
      hermesUrl("/api/activity/stream"),
      {
        method: "GET",
        headers: { Accept: "text/event-stream" },
      },
      60000,
    );

    if (!upstream.ok || !upstream.body) {
      const detail = await upstream.text();
      return NextResponse.json(
        { error: "activity_stream_failed", status: upstream.status, detail },
        { status: 502 },
      );
    }

    return new NextResponse(upstream.body, {
      status: 200,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
      },
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown error";
    return NextResponse.json(
      { error: "activity_proxy_exception", detail },
      { status: 502 },
    );
  }
}
