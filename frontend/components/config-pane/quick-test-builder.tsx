"use client";

import { useState } from "react";
import JSON5 from "json5";
import { Loader2, Plus, Trash2, Zap } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ingestQuickBatch } from "@/lib/api";
import type { IngestSpecResponse, QuickEndpointDraft } from "@/lib/types";

/** Accepts strict JSON as well as looser input people actually paste — a
 * DevTools/console object dump with unquoted keys, single quotes, trailing
 * commas — and normalizes it to pretty-printed valid JSON. Returns null if
 * even the lenient parser can't make sense of it. */
function tryFormatAsJson(text: string): string | null {
  try {
    return JSON.stringify(JSON.parse(text), null, 2);
  } catch {
    try {
      return JSON.stringify(JSON5.parse(text), null, 2);
    } catch {
      return null;
    }
  }
}

const METHODS = ["auto", "GET", "POST", "PUT", "PATCH", "DELETE"] as const;

interface QuickTestBuilderProps {
  disabled?: boolean;
  onIngested: (result: IngestSpecResponse, token: string | null) => void;
}

const EMPTY_DRAFT = { method: "auto", url: "", bodyText: "", public: false };

export function QuickTestBuilder({ disabled, onIngested }: QuickTestBuilderProps) {
  const [token, setToken] = useState("");
  const [endpoints, setEndpoints] = useState<QuickEndpointDraft[]>([]);
  const [draft, setDraft] = useState(EMPTY_DRAFT);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleAdd = () => {
    setError(null);
    if (!draft.url.trim()) {
      setError("URL দিতে হবে।");
      return;
    }
    let bodyText = draft.bodyText;
    if (bodyText.trim()) {
      const formatted = tryFormatAsJson(bodyText);
      if (!formatted) {
        setError("পেলোড ভ্যালিড JSON হতে হবে।");
        return;
      }
      bodyText = formatted;
    }
    setEndpoints((prev) => [...prev, { ...draft, bodyText }]);
    setDraft({ ...EMPTY_DRAFT, public: draft.public });
  };

  const handleBodyBlur = () => {
    if (!draft.bodyText.trim()) return;
    const formatted = tryFormatAsJson(draft.bodyText);
    if (formatted) setDraft((d) => ({ ...d, bodyText: formatted }));
  };

  const handleRemove = (index: number) => {
    setEndpoints((prev) => prev.filter((_, i) => i !== index));
  };

  const handleAnalyze = async () => {
    setError(null);
    setLoading(true);
    try {
      const result = await ingestQuickBatch(endpoints, token);
      onIngested(result, token.trim() || null);
      setEndpoints([]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "এন্ডপয়েন্টগুলো বিশ্লেষণ করা যায়নি।");
    } finally {
      setLoading(false);
    }
  };

  const isBusy = disabled || loading;

  return (
    <div className="space-y-4">
      <div className="space-y-1.5">
        <Label htmlFor="quick-token" className="text-xs text-muted-foreground">
          শেয়ার্ড Bearer Token (ঐচ্ছিক — সব endpoint-এ একসাথে ব্যবহার হবে)
        </Label>
        <Input
          id="quick-token"
          type="password"
          autoComplete="off"
          placeholder="eyJhbGciOi..."
          value={token}
          onChange={(e) => setToken(e.target.value)}
          disabled={isBusy}
          className="font-mono text-sm"
        />
      </div>

      <div className="space-y-2 rounded-lg border border-dashed p-3">
        <div className="flex gap-2">
          <Select value={draft.method} onValueChange={(v) => setDraft((d) => ({ ...d, method: v ?? "auto" }))} disabled={isBusy}>
            <SelectTrigger className="w-[110px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {METHODS.map((m) => (
                <SelectItem key={m} value={m}>
                  {m === "auto" ? "Auto-detect" : m}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            placeholder="https://api.example.com/products/{id}"
            value={draft.url}
            onChange={(e) => setDraft((d) => ({ ...d, url: e.target.value }))}
            disabled={isBusy}
            className="font-mono text-sm"
          />
        </div>

        <Textarea
          placeholder={'পেলোড (ঐচ্ছিক, POST/PUT-এ লাগবে) — DevTools থেকে কপি করা object (unquoted keys) দিলেও চলবে, ফিল্ড ছাড়লেই স্বয়ংক্রিয়ভাবে JSON-এ ফরম্যাট হয়ে যাবে:\n{\n  "name": "demo",\n  "price": 10\n}'}
          value={draft.bodyText}
          onChange={(e) => setDraft((d) => ({ ...d, bodyText: e.target.value }))}
          onBlur={handleBodyBlur}
          disabled={isBusy}
          className="min-h-[80px] font-mono text-xs"
        />

        <div className="flex items-center justify-between">
          <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <input
              type="checkbox"
              checked={draft.public}
              onChange={(e) => setDraft((d) => ({ ...d, public: e.target.checked }))}
              disabled={isBusy}
              className="size-3.5 accent-primary"
            />
            Public (এতে auth লাগে না)
          </label>
          <Button size="sm" variant="outline" onClick={handleAdd} disabled={isBusy}>
            <Plus className="size-3.5" /> Add Endpoint
          </Button>
        </div>
      </div>

      {endpoints.length > 0 && (
        <ul className="space-y-1.5">
          {endpoints.map((ep, index) => (
            <li
              key={index}
              className="flex items-center gap-2 rounded-md bg-muted/50 px-3 py-2 text-xs font-mono"
            >
              <span className="font-semibold uppercase text-muted-foreground">
                {ep.method === "auto" ? "auto" : ep.method}
              </span>
              <span className="flex-1 truncate">{ep.url}</span>
              {ep.bodyText.trim() && <span className="text-muted-foreground">[payload]</span>}
              {ep.public && <span className="text-muted-foreground">[public]</span>}
              <button
                type="button"
                onClick={() => handleRemove(index)}
                disabled={isBusy}
                className="text-muted-foreground hover:text-destructive"
              >
                <Trash2 className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <Button onClick={handleAnalyze} disabled={isBusy || endpoints.length === 0} className="w-full">
        {loading ? <Loader2 className="size-4 animate-spin" /> : <Zap className="size-4" />}
        Analyze All Endpoints ({endpoints.length})
      </Button>

      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  );
}
