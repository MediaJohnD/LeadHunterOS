import { NextResponse } from "next/server";
import {
  defaultModel,
  lemonadeChatEndpoints,
  readJson,
  safeFetch,
} from "../_lib/upstream";
import { getPolicy } from "../_lib/policy";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type Tool = {
  type: "function";
  function: {
    name: string;
    description: string;
    parameters: Record<string, unknown>;
  };
};

type ChatRequest = {
  objective: string;
  tools: Tool[];
  conversationHistory?: Array<{ role: string; content: string }>;
};

export async function POST(request: Request) {
  const payload = await readJson<ChatRequest>(request);
  if (!payload.objective?.trim()) {
    return NextResponse.json(
      { error: "objective is required" },
      { status: 400 },
    );
  }

  const systemPrompt = `You are Hermes, a deterministic lead intelligence agent.
Available tools:
<tools>${JSON.stringify(payload.tools ?? [], null, 2)}</tools>

When using a tool, respond ONLY with:
<tool_call>{"name":"tool_name","arguments":{}}</tool_call>

When you have a final answer, respond ONLY with:
<final_answer>Your answer here</final_answer>

Objective: ${payload.objective}`;
  const policy = getPolicy();
  const policyBlock = `
Run policy:
- verified requires at least ${policy.minSignalsForVerified} independent signals
- max external calls per run: ${policy.maxExternalCallsPerRun}
- cache ttl minutes: ${policy.cacheTtlMinutes}
- prefer local first: ${policy.preferLocalFirst ? "yes" : "no"}
- semantic recall enabled: ${policy.semanticRecallEnabled ? "yes" : "no"}
`;

  const messages = [
    { role: "system", content: `${systemPrompt}\n${policyBlock}` },
    ...(payload.conversationHistory ?? []),
  ];

  const body = {
    model: defaultModel(),
    messages,
    temperature: 0.1,
    max_tokens: 1024,
  };

  let lastErr = "no endpoints available";
  for (const endpoint of lemonadeChatEndpoints()) {
    try {
      const response = await safeFetch(
        endpoint,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        },
        45000,
      );

      if (!response.ok) {
        lastErr = `status ${response.status} at ${endpoint}`;
        continue;
      }

      const data = (await response.json()) as {
        choices: Array<{ message: { content: string } }>;
      };
      return NextResponse.json({
        content: data.choices[0]?.message?.content ?? "",
        policy,
      });
    } catch (error) {
      lastErr = error instanceof Error ? error.message : "unknown error";
    }
  }

  return NextResponse.json(
    { error: "chat_proxy_failed", detail: lastErr },
    { status: 502 },
  );
}
