const HERMES_UPSTREAM =
  process.env.HERMES_UPSTREAM_URL ?? "http://localhost:8642";
const LEMONADE_UPSTREAM =
  process.env.LEMONADE_UPSTREAM_URL ?? "http://localhost:13305";
const DEFAULT_MODEL =
  process.env.LEMONADE_MODEL ?? "user.Qwen3-14B-Instruct-Q4_K_M-GGUF";

function base(url: string) {
  return url.replace(/\/+$/, "");
}

export function hermesUrl(path: string) {
  return `${base(HERMES_UPSTREAM)}${path}`;
}

export function lemonadeChatEndpoints() {
  const root = base(LEMONADE_UPSTREAM);
  return [`${root}/api/v1/chat/completions`, `${root}/v1/chat/completions`];
}

export function defaultModel() {
  return DEFAULT_MODEL;
}

export async function readJson<T>(request: Request): Promise<T> {
  return request.json() as Promise<T>;
}

export async function safeFetch(
  url: string,
  init: RequestInit,
  timeoutMs = 30000,
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

