import { NextResponse } from "next/server";
import { hermesUrl, readJson, safeFetch } from "../../_lib/upstream";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type ExecuteRequest = {
  name: string;
  arguments?: Record<string, unknown>;
};

export async function POST(request: Request) {
  const payload = await readJson<ExecuteRequest>(request);
  if (!payload.name?.trim()) {
    return NextResponse.json(
      { error: "tool name is required" },
      { status: 400 },
    );
  }

  try {
    const upstream = await safeFetch(
      hermesUrl("/api/tools/execute"),
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: payload.name,
          arguments: payload.arguments ?? {},
        }),
      },
      45000,
    );

    const text = await upstream.text();
    if (!upstream.ok) {
      return NextResponse.json(
        {
          error: "tool_execution_failed",
          status: upstream.status,
          detail: text,
        },
        { status: 502 },
      );
    }

    return new NextResponse(text, {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown error";
    return NextResponse.json(
      { error: "tool_proxy_exception", detail },
      { status: 502 },
    );
  }
}

