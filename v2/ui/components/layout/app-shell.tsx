"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";
import {
  Activity,
  Bot,
  Brain,
  ChevronLeft,
  ChevronRight,
  Command,
  Settings,
  Sparkles,
} from "lucide-react";
import { useUiStore } from "@/lib/stores/ui-store";

type Props = {
  children: ReactNode;
};

const nav = [
  { href: "/", label: "Command Center", icon: Command },
  { href: "/skills", label: "Skills", icon: Sparkles },
  { href: "/memory", label: "Memory", icon: Brain },
  { href: "/agents", label: "Agents", icon: Bot },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function AppShell({ children }: Props) {
  const pathname = usePathname();
  const { sidebarCollapsed, toggleSidebar } = useUiStore();

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100">
      <aside
        className={`fixed left-0 top-0 z-40 h-screen border-r border-zinc-800 bg-zinc-900/95 transition-all duration-200 ${
          sidebarCollapsed ? "w-[60px]" : "w-[240px]"
        }`}
      >
        <div className="flex h-14 items-center justify-between border-b border-zinc-800 px-3">
          <div className="flex items-center gap-2 overflow-hidden">
            <Activity className="size-4 text-emerald-400" />
            {!sidebarCollapsed && <span className="text-sm font-semibold">LeadHunterOS</span>}
          </div>
          <button
            type="button"
            onClick={toggleSidebar}
            className="rounded-md border border-zinc-700 p-1 hover:bg-zinc-800"
            aria-label="Toggle sidebar"
          >
            {sidebarCollapsed ? <ChevronRight className="size-4" /> : <ChevronLeft className="size-4" />}
          </button>
        </div>
        <nav className="p-2">
          {nav.map((item) => {
            const Icon = item.icon;
            const active = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`mb-1 flex items-center gap-3 rounded-md px-2 py-2 text-sm ${
                  active ? "bg-zinc-800 text-white" : "text-zinc-300 hover:bg-zinc-800 hover:text-white"
                }`}
              >
                <Icon className="size-4 shrink-0" />
                {!sidebarCollapsed && <span className="truncate">{item.label}</span>}
              </Link>
            );
          })}
        </nav>
      </aside>

      <div className={`transition-all duration-200 ${sidebarCollapsed ? "ml-[60px]" : "ml-[240px]"}`}>
        <header className="sticky top-0 z-30 h-14 border-b border-zinc-800 bg-zinc-900/90 backdrop-blur">
          <div className="flex h-full items-center justify-between px-4">
            <div className="text-sm font-medium">LeadHunterOS</div>
            <div className="flex items-center gap-3 text-xs text-zinc-300">
              <span className="rounded bg-zinc-800 px-2 py-1">Engine: Hermes</span>
              <span className="rounded bg-zinc-800 px-2 py-1">Mode: Executive Ops</span>
              <span className="rounded bg-emerald-500/20 px-2 py-1 text-emerald-300">Status: Active</span>
            </div>
          </div>
        </header>
        <main className="p-4">{children}</main>
      </div>
    </div>
  );
}

