import jsPDF from "jspdf";
import autoTable from "jspdf-autotable";

import { formatCategory, VERDICT_LABEL } from "./test-format";
import type { ParsedSpec, RunMetrics, TestResult } from "./types";

/** Builds the Executive Test Report as a real PDF file and triggers an
 * immediate browser download — no print dialog, no server round-trip.
 */
export function exportExecutiveReport(spec: ParsedSpec | null, metrics: RunMetrics, results: TestResult[]): void {
  const doc = new jsPDF();

  doc.setFontSize(16);
  doc.text("AutonomaPI — Executive Test Report", 14, 18);

  doc.setFontSize(10);
  doc.setTextColor(120);
  const subtitle = spec
    ? `${spec.title} · v${spec.version} · generated ${new Date().toLocaleString()}`
    : `Generated ${new Date().toLocaleString()}`;
  doc.text(subtitle, 14, 25);

  doc.setFontSize(11);
  doc.setTextColor(20);
  const summaryY = 35;
  doc.text(`Total Cases: ${metrics.total_cases}`, 14, summaryY);
  doc.text(`Success Rate: ${metrics.success_rate}%`, 75, summaryY);
  doc.text(`Critical Leaks: ${metrics.critical_leaks}`, 130, summaryY);
  doc.text(`Failed: ${metrics.failed}`, 180, summaryY);

  autoTable(doc, {
    startY: summaryY + 8,
    head: [["Endpoint", "Category", "Description", "Status", "Verdict"]],
    body: results.map((result) => [
      `${result.case.method.toUpperCase()} ${result.case.path}`,
      formatCategory(result.case.category),
      result.case.description,
      result.status_code === null ? "—" : String(result.status_code),
      VERDICT_LABEL[result.verdict],
    ]),
    styles: { fontSize: 8, cellPadding: 2, overflow: "linebreak" },
    columnStyles: { 2: { cellWidth: 70 } },
    headStyles: { fillColor: [24, 24, 27] },
  });

  doc.save(`autonomapi-report-${Date.now()}.pdf`);
}
