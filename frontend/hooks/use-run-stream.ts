"use client";

import { useEffect, useState } from "react";

import { wsUrlForRun } from "@/lib/api";
import type { LogEvent, RunEvent, RunMetrics, RunStatus, TestResult } from "@/lib/types";

interface RunStreamState {
  logs: LogEvent[];
  results: TestResult[];
  metrics: RunMetrics;
  status: RunStatus;
  connected: boolean;
}

const EMPTY_METRICS: RunMetrics = {
  total_cases: 0,
  passed: 0,
  failed: 0,
  critical_leaks: 0,
  errors: 0,
  success_rate: 0,
};

/** Subscribes to /ws/runs/{runId} and accumulates the agent's live log lines,
 * per-case results, and rolling metrics for the duration of a run.
 */
export function useRunStream(runId: string | null): RunStreamState {
  const [trackedRunId, setTrackedRunId] = useState(runId);
  const [logs, setLogs] = useState<LogEvent[]>([]);
  const [results, setResults] = useState<TestResult[]>([]);
  const [metrics, setMetrics] = useState<RunMetrics>(EMPTY_METRICS);
  const [status, setStatus] = useState<RunStatus>("pending");
  const [connected, setConnected] = useState(false);

  // A new runId means a fresh run: reset accumulated state during render
  // (the React-recommended way to adjust state in response to a prop change)
  // rather than in an effect, so the WebSocket effect below stays a pure
  // subscription with no state resets of its own.
  if (runId !== trackedRunId) {
    setTrackedRunId(runId);
    setLogs([]);
    setResults([]);
    setMetrics(EMPTY_METRICS);
    setStatus("pending");
  }

  useEffect(() => {
    if (!runId) return;

    const socket = new WebSocket(wsUrlForRun(runId));

    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onmessage = (event) => {
      const parsed = JSON.parse(event.data) as RunEvent;
      switch (parsed.type) {
        case "log":
          setLogs((prev) => [...prev, parsed.payload as unknown as LogEvent]);
          break;
        case "result":
          setResults((prev) => [...prev, parsed.payload as unknown as TestResult]);
          break;
        case "metrics":
          setMetrics(parsed.payload as unknown as RunMetrics);
          break;
        case "status":
          setStatus((parsed.payload as { status: RunStatus }).status);
          break;
      }
    };

    return () => socket.close();
  }, [runId]);

  return { logs, results, metrics, status, connected };
}
