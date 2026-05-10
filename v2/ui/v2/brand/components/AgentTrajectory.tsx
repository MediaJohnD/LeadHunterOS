"use client";

import { useCallback, useMemo, useState } from "react";
import {
  callHermesAgent,
  executeHermesTool,
  type Tool,
  type TrajectoryStep,
} from "../lib/hermes";

const LEAD_HUNTER_TOOLS: Tool[] = [
  {
    type: "function",
    function: {
      name: "search_accounts",
      description: "Search for target accounts matching ICP criteria",
      parameters: {
        type: "object",
        properties: {
          industry: { type: "string" },
          funding_stage: { type: "string" },
          headcount_min: { type: "number" },
          headcount_max: { type: "number" },
          days_since_signal: { type: "number" },
        },
      },
    },
  },
  {
    type: "function",
    function: {
      name: "enrich_contact",
      description: "Enrich a contact with title, LinkedIn, email, phone",
      parameters: {
        type: "object",
        properties: {
          company: { type: "string" },
          name: { type: "string" },
        },
        required: ["company"],
      },
    },
  },
  {
    type: "function",
    function: {
      name: "score_icp",
      description: "Score account/contact fit and intent against ICP policy",
      parameters: {
        type: "object",
        properties: {
          company: { type: "string" },
          contact_name: { type: "string" },
          signals: { type: "array", items: { type: "string" } },
        },
      },
    },
  },
];

interface Props {
  objective?: string;
}

export default function AgentTrajectory({
  objective: defaultObjective = "Find high-fit US SMB leads with strong ICP + intent signals; score and rank top 3.",
}: Props) {
  const [objective, setObjective] = useState(defaultObjective);
  const [trajectory, setTrajectory] = useState<TrajectoryStep[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runAgent = useCallback(async () => {
    setRunning(true);
    setError(null);
    setTrajectory([]);

    const history: Array<{ role: string; content: string }> = [];
    let stepsRemaining = 8;

    try {
      let step = await callHermesAgent(objective, LEAD_HUNTER_TOOLS, history);
      setTrajectory([step]);

      while (step.tool_call && stepsRemaining-- > 0) {
        history.push({ role: "assistant", content: step.raw });
        const toolResult = await executeHermesTool(step.tool_call);

        const toolMessage = toolResult.ok
          ? toolResult.content
          : JSON.stringify({
              tool_error: true,
              detail: toolResult.content,
            });
        history.push({ role: "tool", content: toolMessage });

        step = await callHermesAgent(objective, LEAD_HUNTER_TOOLS, history);
        setTrajectory((prev) => [
          ...prev,
          { ...step, tool_result: toolMessage },
        ]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unknown error");
    } finally {
      setRunning(false);
    }
  }, [objective]);

  const canRun = useMemo(() => !running && objective.trim().length > 0, [running, objective]);

  return (
    <div className="lh-card mx-auto max-w-4xl space-y-5 p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-bold text-[hsl(var(--lh-text))]">
          Hermes Trajectory
        </h2>
        {running && (
          <span className="flex items-center gap-2 text-sm text-[hsl(var(--lh-text-sec))]">
            <span className="h-2 w-2 animate-pulse rounded-full bg-[hsl(var(--lh-accent))]" />
            Running
          </span>
        )}
      </div>

      <textarea
        value={objective}
        onChange={(e) => setObjective(e.target.value)}
        rows={3}
        className="w-full resize-none rounded-xl border border-[hsl(var(--lh-border))] bg-[hsl(var(--lh-surface))] p-3 text-sm text-[hsl(var(--lh-text))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--lh-accent))]"
        placeholder="Enter agent objective..."
      />

      <button onClick={runAgent} disabled={!canRun} className="lh-btn-primary">
        {running ? "Running..." : "Run Agent"}
      </button>

      {error && (
        <div className="rounded-xl border border-[hsl(var(--lh-danger))] bg-red-50 p-4 text-sm text-[hsl(var(--lh-danger))]">
          <strong>Error:</strong> {error}
        </div>
      )}

      {trajectory.length > 0 ? (
        <div className="space-y-3">
          <p className="text-xs font-semibold uppercase tracking-wide text-[hsl(var(--lh-text-sec))]">
            Steps ({trajectory.length})
          </p>
          {trajectory.map((step, idx) => (
            <div
              key={`${idx}-${step.raw.slice(0, 20)}`}
              className="space-y-2 rounded-xl border border-[hsl(var(--lh-border))] bg-[hsl(var(--lh-surface))] p-4"
            >
              <div className="flex items-center gap-2">
                <span className="rounded-full bg-[hsl(var(--lh-accent-light))] px-2 py-0.5 font-mono text-xs font-semibold text-[hsl(var(--lh-accent))]">
                  Step {idx + 1}
                </span>
                <span className="text-xs text-[hsl(var(--lh-text-sec))]">
                  {step.tool_call ? `Tool: ${step.tool_call.name}` : "Final Answer"}
                </span>
              </div>

              {step.tool_call && (
                <pre className="overflow-x-auto rounded-lg bg-[hsl(var(--lh-card))] p-3 font-mono text-xs text-[hsl(var(--lh-text-sec))]">
                  {JSON.stringify(step.tool_call.arguments, null, 2)}
                </pre>
              )}

              {step.final_answer && (
                <p className="text-sm leading-relaxed text-[hsl(var(--lh-text))]">
                  {step.final_answer}
                </p>
              )}
            </div>
          ))}
        </div>
      ) : (
        !running &&
        !error && (
          <div className="rounded-xl border border-dashed border-[hsl(var(--lh-border))] p-8 text-center text-sm text-[hsl(var(--lh-text-sec))]">
            Enter an objective and run Hermes to inspect each step and tool call.
          </div>
        )
      )}
    </div>
  );
}
