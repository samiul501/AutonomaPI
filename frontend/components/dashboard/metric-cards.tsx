import { ListChecks, ShieldAlert, TrendingUp, XOctagon } from "lucide-react";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import type { RunMetrics } from "@/lib/types";

interface MetricCardsProps {
  metrics: RunMetrics;
}

const CARD_DEFS: {
  key: keyof RunMetrics;
  label: string;
  icon: typeof ListChecks;
  accent: string;
  suffix?: string;
}[] = [
  { key: "total_cases", label: "Total Cases", icon: ListChecks, accent: "text-foreground" },
  { key: "success_rate", label: "Success Rate", icon: TrendingUp, accent: "text-emerald-500", suffix: "%" },
  { key: "critical_leaks", label: "Critical Leaks Found", icon: ShieldAlert, accent: "text-red-500" },
  { key: "failed", label: "Failed Cases", icon: XOctagon, accent: "text-amber-500" },
];

export function MetricCards({ metrics }: MetricCardsProps) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {CARD_DEFS.map(({ key, label, icon: Icon, accent, suffix }) => (
        <Card key={key} className="gap-2 py-4">
          <CardHeader className="flex flex-row items-center justify-between px-4">
            <CardTitle className="text-xs font-medium text-muted-foreground">{label}</CardTitle>
            <Icon className={`size-4 ${accent}`} />
          </CardHeader>
          <CardContent className="px-4">
            <span className={`text-2xl font-semibold tabular-nums ${accent}`}>
              {metrics[key]}
              {suffix ?? ""}
            </span>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
