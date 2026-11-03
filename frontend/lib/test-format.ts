import type { TestVerdict } from "./types";

export function formatCategory(category: string): string {
  return category
    .split("_")
    .map((word) => word[0].toUpperCase() + word.slice(1))
    .join(" ");
}

export const VERDICT_LABEL: Record<TestVerdict, string> = {
  passed: "Passed",
  failed: "Failed",
  critical_leak: "Critical Leak",
  error: "Error",
};
