"use client";

import { useState } from "react";
import { AlertTriangle, Layers, Loader2, PlayCircle } from "lucide-react";

import { AuthConfig } from "@/components/config-pane/auth-config";
import { SpecInput } from "@/components/config-pane/spec-input";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import type { AuthField, IngestSpecResponse, ParsedSpec } from "@/lib/types";

interface ConfigPaneProps {
  spec: ParsedSpec | null;
  authFields: AuthField[];
  credentials: Record<string, string>;
  isRunning: boolean;
  methodDetection?: IngestSpecResponse["method_detection"];
  onIngested: (result: IngestSpecResponse, prefillToken?: string | null) => void;
  onCredentialChange: (scheme: string, value: string) => void;
  onStartRun: () => void;
}

export function ConfigPane({
  spec,
  authFields,
  credentials,
  isRunning,
  methodDetection,
  onIngested,
  onCredentialChange,
  onStartRun,
}: ConfigPaneProps) {
  const [confirmingNoAuth, setConfirmingNoAuth] = useState(false);
  const [trackedSpec, setTrackedSpec] = useState(spec);

  // A newly ingested spec means a fresh decision — don't carry a stale
  // "launch anyway" confirmation over from a previous spec. Reset during
  // render (React's recommended way to adjust state on a prop change)
  // rather than in an effect.
  if (spec !== trackedSpec) {
    setTrackedSpec(spec);
    setConfirmingNoAuth(false);
  }

  const missingCredentials = authFields.filter((field) => !credentials[field.scheme]?.trim());
  const hasMissingCredentials = missingCredentials.length > 0;
  const unconfirmedMethods = (methodDetection ?? []).filter((d) => !d.confirmed_by_server);

  const handleLaunchClick = () => {
    if (hasMissingCredentials && !confirmingNoAuth) {
      setConfirmingNoAuth(true);
      return;
    }
    setConfirmingNoAuth(false);
    onStartRun();
  };

  return (
    <Card className="h-fit">
      <CardHeader>
        <CardTitle className="text-sm">1. Ingest API Specification</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <SpecInput disabled={isRunning} onIngested={onIngested} />

        {spec && (
          <div className="flex items-center gap-2 rounded-md bg-muted/50 px-3 py-2 text-xs">
            <Layers className="size-3.5 shrink-0 text-muted-foreground" />
            <span className="truncate font-medium">{spec.title}</span>
            <span className="text-muted-foreground">v{spec.version}</span>
            <span className="ml-auto shrink-0 text-muted-foreground">
              {spec.endpoints.length} endpoint{spec.endpoints.length === 1 ? "" : "s"}
            </span>
          </div>
        )}

        {unconfirmedMethods.length > 0 && (
          <div className="space-y-1.5 rounded-md border border-amber-500/30 bg-amber-500/10 p-3 text-xs">
            <p className="flex items-start gap-1.5 font-medium text-amber-500">
              <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
              সার্ভার এই {unconfirmedMethods.length}টা endpoint-এর method নিশ্চিত করেনি — এগুলো অনুমান করা হয়েছে, ভুল হতে পারে:
            </p>
            <ul className="space-y-0.5 pl-5 font-mono text-muted-foreground">
              {unconfirmedMethods.map((d, i) => (
                <li key={i} className="truncate">
                  {d.method} {d.url}
                </li>
              ))}
            </ul>
            <p className="text-muted-foreground">ভুল হলে সেটা Quick Test-এ ফিরে গিয়ে method সরাসরি বেছে দিয়ে আবার যোগ করুন।</p>
          </div>
        )}

        {spec && (
          <>
            <Separator />
            <div className="space-y-2">
              <h3 className="text-sm font-medium">2. Authentication</h3>
              <AuthConfig fields={authFields} credentials={credentials} onChange={onCredentialChange} />
              {hasMissingCredentials && (
                <p className="flex items-start gap-1.5 text-xs text-amber-500">
                  <AlertTriangle className="mt-0.5 size-3.5 shrink-0" />
                  {missingCredentials.length === authFields.length
                    ? "No credentials provided — every protected endpoint will get 401s, and any dependency chain that needs a protected create/update call first may break."
                    : `${missingCredentials.length} of ${authFields.length} detected credential(s) still empty.`}
                </p>
              )}
            </div>

            <Separator />
            <Button
              className="w-full"
              size="lg"
              variant={confirmingNoAuth ? "destructive" : "default"}
              onClick={handleLaunchClick}
              disabled={isRunning}
            >
              {isRunning ? (
                <>
                  <Loader2 className="size-4 animate-spin" /> Agent Running...
                </>
              ) : confirmingNoAuth ? (
                <>
                  <AlertTriangle className="size-4" /> Run Without Credentials Anyway?
                </>
              ) : (
                <>
                  <PlayCircle className="size-4" /> Launch Autonomous Test Run
                </>
              )}
            </Button>
            {confirmingNoAuth && (
              <p className="text-center text-xs text-muted-foreground">
                Click again to start anyway, or fill in a token above first.
              </p>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}
