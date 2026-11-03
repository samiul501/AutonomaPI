"use client";

import { useMemo, useState } from "react";
import { FileDown } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { exportExecutiveReport } from "@/lib/pdf-report";
import { formatCategory, VERDICT_LABEL } from "@/lib/test-format";
import type { ParsedSpec, RunMetrics, TestResult, TestVerdict } from "@/lib/types";

interface TestMatrixProps {
  results: TestResult[];
  metrics: RunMetrics;
  spec: ParsedSpec | null;
}

type FilterKey = "all" | "passed" | "failed" | "negative";

const VERDICT_STYLE: Record<TestVerdict, string> = {
  passed: "border-emerald-500/30 bg-emerald-500/10 text-emerald-500",
  failed: "border-amber-500/30 bg-amber-500/10 text-amber-500",
  critical_leak: "border-red-500/30 bg-red-500/10 text-red-500",
  error: "border-zinc-500/30 bg-zinc-500/10 text-zinc-400",
};

export function TestMatrix({ results, metrics, spec }: TestMatrixProps) {
  const [filter, setFilter] = useState<FilterKey>("all");

  const filtered = useMemo(() => {
    switch (filter) {
      case "passed":
        return results.filter((r) => r.verdict === "passed");
      case "failed":
        return results.filter((r) => r.verdict !== "passed");
      case "negative":
        return results.filter((r) => r.case.category !== "positive" && r.case.category !== "dependency");
      default:
        return results;
    }
  }, [results, filter]);

  return (
    <Card className="gap-0 py-0">
      <CardHeader className="flex flex-row items-center justify-between gap-3 border-b px-4 py-3">
        <CardTitle className="text-sm">Test Case Matrix</CardTitle>
        <div className="flex items-center gap-2">
          <Tabs value={filter} onValueChange={(v) => setFilter(v as FilterKey)}>
            <TabsList>
              <TabsTrigger value="all">All</TabsTrigger>
              <TabsTrigger value="passed">Passed</TabsTrigger>
              <TabsTrigger value="failed">Failed</TabsTrigger>
              <TabsTrigger value="negative">Negative</TabsTrigger>
            </TabsList>
          </Tabs>
          <Button
            variant="outline"
            size="sm"
            onClick={() => exportExecutiveReport(spec, metrics, results)}
            disabled={results.length === 0}
          >
            <FileDown className="size-3.5" /> Export PDF
          </Button>
        </div>
      </CardHeader>

      <div className="max-h-[520px] overflow-y-auto">
        <Table>
          <TableHeader className="sticky top-0 bg-card">
            <TableRow>
              <TableHead>Endpoint</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>Description</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Latency</TableHead>
              <TableHead>Verdict</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="py-8 text-center text-muted-foreground">
                  No test cases yet.
                </TableCell>
              </TableRow>
            ) : (
              filtered.map((result) => (
                <TableRow key={result.case.id}>
                  <TableCell className="font-mono text-xs">
                    <span className="mr-1.5 font-semibold uppercase text-muted-foreground">
                      {result.case.method}
                    </span>
                    {result.case.path}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{formatCategory(result.case.category)}</Badge>
                  </TableCell>
                  <TableCell className="max-w-xs truncate text-xs text-muted-foreground" title={result.case.description}>
                    {result.case.description}
                  </TableCell>
                  <TableCell className="font-mono text-xs">{result.status_code ?? "—"}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">
                    {result.elapsed_ms ? `${Math.round(result.elapsed_ms)}ms` : "—"}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline" className={VERDICT_STYLE[result.verdict]}>
                      {VERDICT_LABEL[result.verdict]}
                    </Badge>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </Card>
  );
}
