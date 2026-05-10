import { NextResponse } from "next/server";
import { hermesUrl, readJson, safeFetch } from "../_lib/upstream";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type CommandRequest = { command: string };

export async function POST(request: Request) {
  const payload = await readJson<CommandRequest>(request);
  if (!payload.command?.trim()) {
    return NextResponse.json(
      { error: "command is required" },
      { status: 400 },
    );
  }

  try {
    const upstream = await safeFetch(hermesUrl("/api/command"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const text = await upstream.text();
    return new NextResponse(text, {
      status: upstream.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : "unknown error";
    return NextResponse.json(
      { error: "command_proxy_failed", detail },
      { status: 502 },
    );
  }
}

