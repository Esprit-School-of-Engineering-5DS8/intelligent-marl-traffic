type Value = string | number | boolean | null | undefined;

function escape(value: Value): string {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\n;]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(rows: Record<string, Value>[]): string {
  const first = rows[0];
  if (!first) return "";
  const columns = Object.keys(first);
  return [columns.join(","), ...rows.map((r) => columns.map((c) => escape(r[c])).join(","))].join(
    "\n",
  );
}

/** Saves rows as a CSV file (UTF-8 with BOM so spreadsheet software reads accents). */
export function downloadCsv(rows: Record<string, Value>[], filename: string): void {
  const blob = new Blob(["﻿", toCsv(rows)], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
