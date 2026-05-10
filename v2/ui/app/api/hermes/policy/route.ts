import { NextResponse } from "next/server";
import { getPolicy, type HermesPolicy, updatePolicy } from "../_lib/policy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json({ policy: getPolicy() });
}

export async function POST(request: Request) {
  const body = (await request.json()) as Partial<HermesPolicy>;
  const policy = updatePolicy(body);
  return NextResponse.json({ policy });
}

