"use client";

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Clock3, ShieldAlert, Sparkles, X } from "lucide-react";

type ApprovalState = "pending" | "approved" | "escalated" | "snoozed" | "rejected";

type ApprovalItem = {
  id: string;
  account: string;
  action: string;
  confidence: number;
  signal_count: number;
  is_qualified: boolean;
  state: ApprovalState;
};

type RuntimeLane = {
  lane: string;
  status: "Healthy" | "Degraded";
  latency: string;
};

type QualifiedPayload = {
  approvals?: ApprovalItem[];
  kpis?: Array<{ metric: string; value: string | number }>;
  runtime?: RuntimeLane[];
  executive_feed?: string[];
};

type HermesPolicy = {
  minSignalsForVerified: number;
  maxExternalCallsPerRun: number;
  cacheTtlMinutes: number;
  preferLocalFirst: boolean;
  semanticRecallEnabled: boolean;
};

async function getQualifiedDashboard(): Promise<QualifiedPayload> {
  const response = await fetch("/api/hermes/tasks", { cache: "no-store" });
  if (!response.ok) {
    return {};
  }
  const data = (await response.json()) as unknown;
  if (typeof data === "object" && data !== null && "tasks" in data) {
    const tasks = (data as { tasks?: ApprovalItem[] }).tasks;
    if (Array.isArray(tasks)) {
      return { approvals: tasks };
    }
  }
  if (typeof data === "object" && data !== null) {
    return data as QualifiedPayload;
  }
  return {};
}

async function getPolicy(): Promise<HermesPolicy | null> {
  const response = await fetch("/api/hermes/policy", { cache: "no-store" });
  if (!response.ok) return null;
  const body = (await response.json()) as { policy?: HermesPolicy };
  return body.policy ?? null;
}

async function savePolicy(policy: HermesPolicy): Promise<HermesPolicy | null> {
  const response = await fetch("/api/hermes/policy", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(policy),
  });
  if (!response.ok) return null;
  const body = (await response.json()) as { policy?: HermesPolicy };
  return body.policy ?? null;
}

export function CommandCenter() {
  const [approvals, setApprovals] = useState<ApprovalItem[]>([]);
  const [kpis, setKpis] = useState<Array<{ metric: string; value: string | number }>>([]);
  const [runtime, setRuntime] = useState<RuntimeLane[]>([]);
  const [executiveFeed, setExecutiveFeed] = useState<string[]>([]);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [loading, setLoading] = useState(true);
  const [policy, setPolicy] = useState<HermesPolicy | null>(null);

  useEffect(() => {
    let mounted = true;
    void (async () => {
      setLoading(true);
      const payload = await getQualifiedDashboard();
      if (!mounted) return;

      const qualifiedApprovals = (payload.approvals ?? []).filter(
        (item) => item.is_qualified && item.signal_count >= 30,
      );

      setApprovals(qualifiedApprovals);
      setKpis(payload.kpis ?? []);
      setRuntime(payload.runtime ?? []);
      setExecutiveFeed(payload.executive_feed ?? []);
      setPolicy(await getPolicy());
      setLoading(false);
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const pending = useMemo(
    () => approvals.map((a, idx) => ({ ...a, idx })).filter((a) => a.state === "pending"),
    [approvals],
  );

  const currentPending = pending[Math.min(selectedIndex, Math.max(0, pending.length - 1))];

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (!currentPending) return;
      const key = event.key.toUpperCase();
      if (!["A", "E", "S", "Z", "N"].includes(key)) return;
      event.preventDefault();

      if (key === "N") {
        setSelectedIndex((v) => Math.min(v + 1, Math.max(0, pending.length - 1)));
        return;
      }

      const state: ApprovalState =
        key === "A"
          ? "approved"
          : key === "E"
            ? "escalated"
            : key === "S"
              ? "snoozed"
              : "rejected";

      setApprovals((prev) =>
        prev.map((row) => (row.id === currentPending.id ? { ...row, state } : row)),
      );
    };

    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [currentPending, pending.length]);

  const policySummary = policy
    ? `Verified >= ${policy.minSignalsForVerified} signals | Max external calls ${policy.maxExternalCallsPerRun}/run | Cache TTL ${policy.cacheTtlMinutes}m`
    : "Policy unavailable";

  return (
    <div className="grid grid-cols-12 gap-4">
      <section className="col-span-12 rounded-lg border border-zinc-800 bg-zinc-900 p-4 lg:col-span-7">
        <h2 className="mb-3 text-sm font-semibold text-zinc-200">Signal Velocity</h2>
        <div className="rounded-md border border-zinc-800 bg-zinc-950 p-4 text-sm text-zinc-300">
          {loading
            ? "Loading qualified signal telemetry..."
            : "No chart is shown until qualified trend telemetry is provided by Hermes."}
        </div>
      </section>

      <section className="col-span-12 rounded-lg border border-zinc-800 bg-zinc-900 p-4 lg:col-span-5">
        <h2 className="mb-3 text-sm font-semibold text-zinc-200">Cost & Speed Policy</h2>
        {policy ? (
          <div className="space-y-3">
            <p className="text-xs text-zinc-400">{policySummary}</p>
            <div className="grid grid-cols-3 gap-2">
              <label className="text-xs text-zinc-400">
                Verified signals
                <input
                  type="number"
                  min={1}
                  className="mt-1 w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-zinc-200"
                  value={policy.minSignalsForVerified}
                  onChange={(e) =>
                    setPolicy((prev) =>
                      prev
                        ? { ...prev, minSignalsForVerified: Number(e.target.value) }
                        : prev,
                    )
                  }
                />
              </label>
              <label className="text-xs text-zinc-400">
                Max external calls
                <input
                  type="number"
                  min={1}
                  className="mt-1 w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-zinc-200"
                  value={policy.maxExternalCallsPerRun}
                  onChange={(e) =>
                    setPolicy((prev) =>
                      prev
                        ? { ...prev, maxExternalCallsPerRun: Number(e.target.value) }
                        : prev,
                    )
                  }
                />
              </label>
              <label className="text-xs text-zinc-400">
                Cache TTL (minutes)
                <input
                  type="number"
                  min={1}
                  className="mt-1 w-full rounded border border-zinc-700 bg-zinc-950 px-2 py-1 text-zinc-200"
                  value={policy.cacheTtlMinutes}
                  onChange={(e) =>
                    setPolicy((prev) =>
                      prev ? { ...prev, cacheTtlMinutes: Number(e.target.value) } : prev,
                    )
                  }
                />
              </label>
            </div>
            <div className="flex items-center gap-4 text-xs text-zinc-300">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={policy.preferLocalFirst}
                  onChange={(e) =>
                    setPolicy((prev) =>
                      prev ? { ...prev, preferLocalFirst: e.target.checked } : prev,
                    )
                  }
                />
                Prefer local-first providers
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={policy.semanticRecallEnabled}
                  onChange={(e) =>
                    setPolicy((prev) =>
                      prev ? { ...prev, semanticRecallEnabled: e.target.checked } : prev,
                    )
                  }
                />
                Semantic recall enabled
              </label>
            </div>
            <button
              type="button"
              className="rounded bg-zinc-100 px-3 py-1 text-xs font-semibold text-zinc-900"
              onClick={async () => {
                if (!policy) return;
                const saved = await savePolicy(policy);
                if (saved) setPolicy(saved);
              }}
            >
              Save Policy
            </button>
          </div>
        ) : (
          <div className="rounded-md border border-zinc-800 bg-zinc-950 p-4 text-sm text-zinc-400">
            Policy controls unavailable.
          </div>
        )}
      </section>

      <section className="col-span-12 rounded-lg border border-zinc-800 bg-zinc-900 p-4 lg:col-span-5">
        <h2 className="mb-3 text-sm font-semibold text-zinc-200">Pipeline KPIs</h2>
        {kpis.length === 0 ? (
          <div className="rounded-md border border-zinc-800 bg-zinc-950 p-4 text-sm text-zinc-400">
            No qualified KPI data available.
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-3">
            {kpis.map((item) => (
              <div key={item.metric} className="rounded-md border border-zinc-800 bg-zinc-950 p-3">
                <p className="text-xs text-zinc-400">{item.metric}</p>
                <p className="mt-1 text-xl font-semibold">{item.value}</p>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="col-span-12 rounded-lg border border-zinc-800 bg-zinc-900 p-4 lg:col-span-7">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-zinc-200">Approvals Queue</h2>
          <div className="text-xs text-zinc-400">Shortcuts: A / E / S / Z / N</div>
        </div>
        {approvals.length === 0 ? (
          <div className="rounded-md border border-zinc-800 bg-zinc-950 p-4 text-sm text-zinc-400">
            No qualified approvals. Leads must pass ICP and have at least 30 independent signals.
          </div>
        ) : (
          <div className="space-y-2">
            <AnimatePresence initial={false}>
              {approvals.map((row, idx) => (
                <motion.div
                  key={row.id}
                  layout
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  className={`rounded-md border p-3 ${
                    currentPending && row.id === currentPending.id && row.state === "pending"
                      ? "border-emerald-500 bg-emerald-500/10"
                      : "border-zinc-800 bg-zinc-950"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">{row.account}</p>
                      <p className="text-xs text-zinc-400">{row.action}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-xs text-zinc-400">Confidence</p>
                      <p className="text-sm font-semibold">{row.confidence}%</p>
                    </div>
                  </div>
                  <p className="mt-2 text-xs uppercase tracking-wide text-zinc-400">
                    Signals: {row.signal_count} | State: {row.state}
                  </p>
                </motion.div>
              ))}
            </AnimatePresence>
          </div>
        )}
      </section>

      <section className="col-span-12 rounded-lg border border-zinc-800 bg-zinc-900 p-4 lg:col-span-5">
        <h2 className="mb-3 text-sm font-semibold text-zinc-200">Runtime Health</h2>
        {runtime.length === 0 ? (
          <div className="rounded-md border border-zinc-800 bg-zinc-950 p-4 text-sm text-zinc-400">
            Runtime health data unavailable.
          </div>
        ) : (
          <div className="space-y-2">
            {runtime.map((lane) => (
              <div
                key={lane.lane}
                className="flex items-center justify-between rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2"
              >
                <div className="flex items-center gap-2">
                  {lane.status === "Healthy" ? (
                    <Check className="size-4 text-emerald-400" />
                  ) : (
                    <ShieldAlert className="size-4 text-amber-400" />
                  )}
                  <span className="text-sm">{lane.lane}</span>
                </div>
                <span className="text-xs text-zinc-400">{lane.latency}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="col-span-12 rounded-lg border border-zinc-800 bg-zinc-900 p-4">
        <h2 className="mb-3 text-sm font-semibold text-zinc-200">Executive Feed</h2>
        {executiveFeed.length === 0 ? (
          <div className="rounded-md border border-zinc-800 bg-zinc-950 p-4 text-sm text-zinc-400">
            No qualified executive updates available.
          </div>
        ) : (
          <div className="grid gap-2 md:grid-cols-2">
            {executiveFeed.map((item, index) => (
              <div
                key={index}
                className="flex items-center gap-2 rounded-md border border-zinc-800 bg-zinc-950 px-3 py-2 text-sm"
              >
                {index % 2 === 0 ? (
                  <Sparkles className="size-4 text-blue-400" />
                ) : (
                  <Clock3 className="size-4 text-violet-400" />
                )}
                <span>{item}</span>
              </div>
            ))}
          </div>
        )}
        <div className="mt-3 flex gap-2 text-xs text-zinc-400">
          <span className="rounded bg-zinc-800 px-2 py-1">A: Approve</span>
          <span className="rounded bg-zinc-800 px-2 py-1">E: Escalate</span>
          <span className="rounded bg-zinc-800 px-2 py-1">S: Snooze</span>
          <span className="rounded bg-zinc-800 px-2 py-1">Z: Reject</span>
          <span className="rounded bg-zinc-800 px-2 py-1">N: Next</span>
          <span className="rounded bg-zinc-800 px-2 py-1">
            <X className="inline size-3" /> queue action
          </span>
        </div>
      </section>
    </div>
  );
}
