"use client";

import { useEffect, useRef } from "react";
import { AlertTriangle, Brain, CheckCircle2, Info, TerminalSquare, XCircle } from "lucide-react";

import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import type { LogEvent, LogLevel } from "@/lib/types";

interface ReasoningTerminalProps {
  logs: LogEvent[];
  connected: boolean;
}

const LEVEL_STYLES: Record<LogLevel, { icon: typeof Info; className: string }> = {
  thought: { icon: Brain, className: "text-violet-400" },
  info: { icon: Info, className: "text-sky-400" },
  success: { icon: CheckCircle2, className: "text-emerald-400" },
  warning: { icon: AlertTriangle, className: "text-amber-400" },
  error: { icon: XCircle, className: "text-red-400" },
};

function formatTime(timestamp: string): string {
  try {
    return new Date(timestamp).toLocaleTimeString([], { hour12: false });
  } catch {
    return "";
  }
}

export function ReasoningTerminal({ logs, connected }: ReasoningTerminalProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [logs]);

  return (
    <Card className="flex h-full flex-col gap-0 overflow-hidden py-0">
      <CardHeader className="flex flex-row items-center justify-between border-b border-white/10 bg-zinc-950 px-4 py-3">
        <CardTitle className="flex items-center gap-2 text-sm text-zinc-200">
          <TerminalSquare className="size-4" />
          Agent Reasoning Log
        </CardTitle>
        <span className="flex items-center gap-1.5 text-xs text-zinc-500">
          <span className={`size-1.5 rounded-full ${connected ? "bg-emerald-500" : "bg-zinc-600"}`} />
          {connected ? "live" : "idle"}
        </span>
      </CardHeader>
      <div ref={scrollRef} className="flex-1 overflow-y-auto bg-zinc-950 px-4 py-3 font-mono text-[13px] leading-relaxed">
        {logs.length === 0 ? (
          <p className="text-zinc-600">Awaiting agent activity — launch a run to see live reasoning here.</p>
        ) : (
          logs.map((log, index) => {
            const { icon: Icon, className } = LEVEL_STYLES[log.level];
            return (
              <div key={index} className="flex items-start gap-2 py-0.5">
                <span className="shrink-0 text-zinc-600">{formatTime(log.timestamp)}</span>
                <Icon className={`mt-0.5 size-3.5 shrink-0 ${className}`} />
                <span className="text-zinc-300">{log.message}</span>
              </div>
            );
          })
        )}
      </div>
    </Card>
  );
}
