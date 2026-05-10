const HERMES_PROXY_BASE = "/api/hermes";

export interface Tool {
  type: "function";
  function: {
    name: string;
    description: string;
    parameters: Record<string, unknown>;
  };
}

export interface TrajectoryStep {
  tool_call?: { name: string; arguments: Record<string, unknown> };
  tool_result?: string;
  final_answer?: string;
  raw: string;
}

function parseHermesXML(content: string): Omit<TrajectoryStep, "raw"> {
  const toolMatch = /<tool_call>([\s\S]*?)<\/tool_call>/.exec(content);
  if (toolMatch) {
    try {
      return { tool_call: JSON.parse(toolMatch[1].trim()) };
    } catch {
      return { tool_call: { name: "unknown", arguments: {} } };
    }
  }

  const answerMatch = /<final_answer>([\s\S]*?)<\/final_answer>/.exec(content);
  if (answerMatch) {
    return { final_answer: answerMatch[1].trim() };
  }

  return { final_answer: content.trim() };
}

export async function callHermesAgent(
  objective: string,
  tools: Tool[],
  conversationHistory: Array<{ role: string; content: string }> = [],
): Promise<TrajectoryStep> {
  const response = await fetch(`${HERMES_PROXY_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      objective,
      tools,
      conversationHistory,
    }),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(`Hermes chat proxy failed: ${response.status} ${detail}`);
  }
  const data = (await response.json()) as { content: string };

  const content = data.content ?? "";
  return { ...parseHermesXML(content), raw: content };
}

export async function executeHermesTool(
  toolCall: NonNullable<TrajectoryStep["tool_call"]>,
): Promise<{ ok: boolean; content: string }> {
  const response = await fetch(`${HERMES_PROXY_BASE}/tools/execute`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      name: toolCall.name,
      arguments: toolCall.arguments,
    }),
  });

  if (!response.ok) {
    const body = await response.text();
    return {
      ok: false,
      content: JSON.stringify({
        error: "tool_execution_failed",
        status: response.status,
        body,
      }),
    };
  }

  const result = await response.json();
  return { ok: true, content: JSON.stringify(result) };
}

export async function getHermesActivity(): Promise<Response> {
  return fetch(`${HERMES_PROXY_BASE}/activity/stream`, {
    headers: { Accept: "text/event-stream" },
  });
}

export async function getHermesTasks() {
  const res = await fetch(`${HERMES_PROXY_BASE}/tasks`);
  if (!res.ok) throw new Error(`Tasks fetch failed: ${res.status}`);
  return res.json();
}

export async function getHermesAccounts() {
  const res = await fetch(`${HERMES_PROXY_BASE}/accounts`);
  if (!res.ok) throw new Error(`Accounts fetch failed: ${res.status}`);
  return res.json();
}

export async function approveHermesTask(taskId: string) {
  const res = await fetch(`${HERMES_PROXY_BASE}/tasks/${taskId}/approve`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Approve failed: ${res.status}`);
  return res.json();
}

export async function skipHermesTask(taskId: string) {
  const res = await fetch(`${HERMES_PROXY_BASE}/tasks/${taskId}/skip`, {
    method: "POST",
  });
  if (!res.ok) throw new Error(`Skip failed: ${res.status}`);
  return res.json();
}

export async function sendHermesCommand(command: string) {
  const res = await fetch(`${HERMES_PROXY_BASE}/command`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ command }),
  });
  if (!res.ok) throw new Error(`Command failed: ${res.status}`);
  return res.json();
}
