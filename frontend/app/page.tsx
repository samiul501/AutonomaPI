"use client";

import { useCallback, useState } from "react";
import { Bot, RotateCcw } from "lucide-react";

import { ConfigPane } from "@/components/config-pane/config-pane";
import { MetricCards } from "@/components/dashboard/metric-cards";
import { ReasoningTerminal } from "@/components/dashboard/reasoning-terminal";
import { TestMatrix } from "@/components/dashboard/test-matrix";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useRunStream } from "@/hooks/use-run-stream";
import { startRun } from "@/lib/api";
import type { AuthField, IngestSpecResponse, ParsedSpec } from "@/lib/types";

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  pending: { label: "Idle", className: "bg-muted text-muted-foreground" },
  running: { label: "Agent Running", className: "border-sky-500/30 bg-sky-500/10 text-sky-500" },
  completed: { label: "Completed", className: "border-emerald-500/30 bg-emerald-500/10 text-emerald-500" },
  failed: { label: "Failed", className: "border-red-500/30 bg-red-500/10 text-red-500" },
};

export default function DashboardPage() {
  const [spec, setSpec] = useState<ParsedSpec | null>(null);
  const [specId, setSpecId] = useState<string | null>(null);
  const [authFields, setAuthFields] = useState<AuthField[]>([]);
  const [methodDetection, setMethodDetection] = useState<IngestSpecResponse["method_detection"]>(undefined);
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [runId, setRunId] = useState<string | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const { logs, results, metrics, status, connected } = useRunStream(runId);

  const handleIngested = useCallback((result: IngestSpecResponse, prefillToken?: string | null) => {
    setSpec(result.spec);
    setSpecId(result.spec_id);
    setAuthFields(result.auth_fields);
    setMethodDetection(result.method_detection);
    // Quick Test already collected a token up front — seed it straight into
    // the (dynamically detected) auth field instead of asking for it twice.
    const seeded = prefillToken && result.auth_fields[0] ? { [result.auth_fields[0].scheme]: prefillToken } : {};
    setCredentials(seeded);
    setRunId(null);
  }, []);

  const handleCredentialChange = useCallback((scheme: string, value: string) => {
    setCredentials((prev) => ({ ...prev, [scheme]: value }));
  }, []);

  const handleStartRun = useCallback(async () => {
    if (!specId) return;
    setIsStarting(true);
    setStartError(null);
    try {
      const { run_id } = await startRun(specId, credentials);
      setRunId(run_id);
    } catch (err) {
      setStartError(err instanceof Error ? err.message : "Failed to start the run.");
    } finally {
      setIsStarting(false);
    }
  }, [specId, credentials]);

  const handleReset = useCallback(() => {
    setSpec(null);
    setSpecId(null);
    setAuthFields([]);
    setMethodDetection(undefined);
    setCredentials({});
    setRunId(null);
    setStartError(null);
  }, []);

  const isRunning = isStarting || status === "running";
  const badge = STATUS_BADGE[runId ? status : "pending"];

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b px-6 py-4">
        <div className="flex items-center gap-2.5">
          <div className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
            <Bot className="size-4.5" />
          </div>
          <div>
            <h1 className="text-sm font-semibold leading-none">AutonomaPI</h1>
            <p className="text-xs text-muted-foreground">Autonomous Agentic API Testing</p>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Badge variant="outline" className={badge.className}>
            {badge.label}
          </Badge>
          {spec && (
            <Button variant="ghost" size="sm" onClick={handleReset} disabled={isRunning}>
              <RotateCcw className="size-3.5" /> Reset
            </Button>
          )}
        </div>
      </header>

      <main className="flex-1 p-6">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[340px_1fr]">
          <div>
            <ConfigPane
              spec={spec}
              authFields={authFields}
              credentials={credentials}
              isRunning={isRunning}
              methodDetection={methodDetection}
              onIngested={handleIngested}
              onCredentialChange={handleCredentialChange}
              onStartRun={handleStartRun}
            />
            {startError && <p className="mt-2 text-sm text-destructive">{startError}</p>}
          </div>

          <div className="space-y-4">
            {!spec ? (
              <div className="flex h-full min-h-[400px] flex-col items-center justify-center gap-2 rounded-xl border border-dashed text-center text-sm text-muted-foreground">
                <Bot className="size-8" />
                <p>Ingest a Swagger/OpenAPI spec to let the agent start mapping routes.</p>
              </div>
            ) : (
              <>
                <MetricCards metrics={metrics} />
                <div className="grid grid-cols-1 gap-4 xl:grid-cols-[1fr_1.4fr]">
                  <div className="h-[460px]">
                    <ReasoningTerminal logs={logs} connected={connected} />
                  </div>
                  <TestMatrix results={results} metrics={metrics} spec={spec} />
                </div>
              </>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
