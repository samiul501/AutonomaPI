"use client";

import { KeyRound, ShieldCheck } from "lucide-react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { AuthField } from "@/lib/types";

interface AuthConfigProps {
  fields: AuthField[];
  credentials: Record<string, string>;
  onChange: (scheme: string, value: string) => void;
}

export function AuthConfig({ fields, credentials, onChange }: AuthConfigProps) {
  if (fields.length === 0) {
    return (
      <p className="flex items-start gap-2 rounded-md border border-dashed p-3 text-sm text-muted-foreground">
        <ShieldCheck className="mt-0.5 size-4 shrink-0" />
        No security schemes detected — every endpoint in this spec is public and will be tested without
        credentials.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      {fields.map((field) => (
        <div key={field.scheme} className="space-y-1.5">
          <Label htmlFor={field.scheme} className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <KeyRound className="size-3.5" />
            {field.label}
          </Label>
          <Input
            id={field.scheme}
            type="password"
            autoComplete="off"
            placeholder={field.placeholder}
            value={credentials[field.scheme] ?? ""}
            onChange={(e) => onChange(field.scheme, e.target.value)}
            className="font-mono text-sm"
          />
        </div>
      ))}
    </div>
  );
}
