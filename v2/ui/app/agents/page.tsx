import AgentTrajectory from "@/brand/components/AgentTrajectory";

export default function AgentsPage() {
  return (
    <div className="space-y-6">
      <div className="lh-card p-6">
        <h1 className="text-2xl font-bold text-[hsl(var(--lh-text))]">
          LeadHunterOS Agents
        </h1>
        <p className="mt-2 text-sm text-[hsl(var(--lh-text-sec))]">
          Run and inspect Hermes trajectories with explicit tool-step visibility.
        </p>
      </div>
      <AgentTrajectory />
    </div>
  );
}
