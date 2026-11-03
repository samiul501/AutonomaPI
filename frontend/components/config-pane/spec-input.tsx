"use client";

import { useCallback, useRef, useState } from "react";
import { Link2, Loader2, UploadCloud } from "lucide-react";

import { QuickTestBuilder } from "@/components/config-pane/quick-test-builder";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ingestSpecFromFile, ingestSpecFromUrl } from "@/lib/api";
import type { IngestSpecResponse } from "@/lib/types";

interface SpecInputProps {
  disabled?: boolean;
  onIngested: (result: IngestSpecResponse, prefillToken?: string | null) => void;
}

export function SpecInput({ disabled, onIngested }: SpecInputProps) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const reportError = (err: unknown) => {
    setError(err instanceof Error ? err.message : "Something went wrong while analyzing the spec.");
  };

  const handleUrlSubmit = useCallback(async () => {
    if (!url.trim()) return;
    setLoading(true);
    setError(null);
    try {
      onIngested(await ingestSpecFromUrl(url.trim()));
    } catch (err) {
      reportError(err);
    } finally {
      setLoading(false);
    }
  }, [url, onIngested]);

  const handleFile = useCallback(
    async (file: File) => {
      setLoading(true);
      setError(null);
      try {
        onIngested(await ingestSpecFromFile(file));
      } catch (err) {
        reportError(err);
      } finally {
        setLoading(false);
      }
    },
    [onIngested]
  );

  return (
    <Tabs defaultValue="url" className="w-full">
      <TabsList className="grid w-full grid-cols-3">
        <TabsTrigger value="url">Spec URL</TabsTrigger>
        <TabsTrigger value="file">Upload File</TabsTrigger>
        <TabsTrigger value="quick">Quick Test</TabsTrigger>
      </TabsList>

      <TabsContent value="url" className="mt-3 flex gap-2">
        <Input
          placeholder="https://api.example.com/openapi.json"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={disabled || loading}
          onKeyDown={(e) => e.key === "Enter" && handleUrlSubmit()}
          className="font-mono text-sm"
        />
        <Button onClick={handleUrlSubmit} disabled={disabled || loading || !url.trim()}>
          {loading ? <Loader2 className="size-4 animate-spin" /> : <Link2 className="size-4" />}
          Analyze
        </Button>
      </TabsContent>

      <TabsContent value="file" className="mt-3">
        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragActive(true);
          }}
          onDragLeave={() => setDragActive(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragActive(false);
            const file = e.dataTransfer.files?.[0];
            if (file) handleFile(file);
          }}
          onClick={() => !disabled && !loading && fileInputRef.current?.click()}
          className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border border-dashed px-4 py-8 text-center text-sm transition-colors ${
            dragActive ? "border-primary bg-primary/5" : "border-border hover:bg-muted/40"
          }`}
        >
          {loading ? (
            <Loader2 className="size-6 animate-spin text-muted-foreground" />
          ) : (
            <UploadCloud className="size-6 text-muted-foreground" />
          )}
          <p className="text-muted-foreground">
            Drop a Swagger/OpenAPI <span className="font-medium text-foreground">.json</span> or{" "}
            <span className="font-medium text-foreground">.yaml</span> file, or click to browse.
          </p>
          <input
            ref={fileInputRef}
            type="file"
            accept=".json,.yaml,.yml"
            className="hidden"
            disabled={disabled || loading}
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) handleFile(file);
            }}
          />
        </div>
      </TabsContent>

      <TabsContent value="quick" className="mt-3">
        <QuickTestBuilder disabled={disabled} onIngested={onIngested} />
      </TabsContent>

      {error && <p className="mt-2 text-sm text-destructive">{error}</p>}
    </Tabs>
  );
}
