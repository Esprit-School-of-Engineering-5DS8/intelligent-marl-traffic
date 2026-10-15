import { Download, Table2 } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { downloadCsv } from "@/shared/lib/csv";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";

type Row = Record<string, string | number | boolean | null | undefined>;

/**
 * A chart with its title, a one-line reading guide and the numbers behind it: the table
 * gives screen-reader and keyboard users the same information as the picture.
 */
export function ChartCard({
  title,
  description,
  actions,
  table,
  csvName,
  children,
  className,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  table?: Row[];
  csvName?: string;
  children: ReactNode;
  className?: string;
}) {
  const { t } = useTranslation();
  const [showTable, setShowTable] = useState(false);
  const columns = table?.[0] ? Object.keys(table[0]) : [];

  return (
    <Card className={className}>
      <CardHeader className="flex-row flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 flex-col gap-1">
          <CardTitle>{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </div>
        <div className="flex items-center gap-1">
          {actions}
          {table && table.length ? (
            <>
              <Button
                variant="ghost"
                size="sm"
                aria-pressed={showTable}
                onClick={() => setShowTable((v) => !v)}
              >
                <Table2 aria-hidden="true" />
                <span className="sr-only sm:not-sr-only">{t("data.showTable")}</span>
              </Button>
              {csvName ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => downloadCsv(table, csvName)}
                  aria-label={t("data.exportCsv")}
                  title={t("data.exportCsv")}
                >
                  <Download aria-hidden="true" />
                </Button>
              ) : null}
            </>
          ) : null}
        </div>
      </CardHeader>
      <CardContent>
        {children}
        {showTable && table ? (
          <div
            tabIndex={0}
            role="region"
            aria-label={title}
            className="mt-3 max-h-72 overflow-auto rounded-md border border-border"
          >
            <table className="w-full text-start text-xs">
              <caption className="sr-only">{title}</caption>
              <thead className="sticky top-0 bg-surface-2">
                <tr>
                  {columns.map((c) => (
                    <th
                      key={c}
                      scope="col"
                      className="px-2 py-1.5 text-start font-medium text-text-2"
                    >
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="tabular">
                {table.map((row, i) => (
                  <tr key={i} className="border-t border-border">
                    {columns.map((c) => (
                      <td key={c} className="px-2 py-1 text-text">
                        {String(row[c] ?? "–")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
