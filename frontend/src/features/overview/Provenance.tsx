import { Database } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useFormat } from "@/shared/domain/format";
import type { Meta } from "@/shared/schemas";
import { Badge } from "@/shared/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";

/** Where the numbers come from: export date, run counts, what is still being computed. */
export function Provenance({ meta }: { meta: Meta }) {
  const { t } = useTranslation();
  const f = useFormat();
  const items = [
    [t("data.generatedAt"), f.date(meta.generatedAt)],
    [t("data.runs"), meta.runs === null ? "–" : f.number(meta.runs, 0)],
    [t("data.extraRuns"), f.number(meta.extraRuns, 0)],
    [t("data.cells"), f.number(meta.cells.length, 0)],
    [t("data.controllers"), f.number(meta.methods.length, 0)],
  ] as const;
  return (
    <Card>
      <CardHeader className="flex-row items-center gap-2">
        <Database aria-hidden="true" className="size-4 text-muted" />
        <CardTitle>{t("data.provenance")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {items.map(([label, value]) => (
            <div key={label} className="flex flex-col gap-0.5">
              <dt className="text-[11px] text-muted">{label}</dt>
              <dd className="tabular text-sm font-medium text-text">{value}</dd>
            </div>
          ))}
          <div className="flex flex-col gap-0.5">
            <dt className="text-[11px] text-muted">{t("data.dqn")}</dt>
            <dd>
              <Badge tone={meta.dqnAvailable ? "flow" : "dense"}>
                {meta.dqnAvailable ? t("data.available") : t("data.pending")}
              </Badge>
            </dd>
          </div>
        </dl>
        <p className="text-xs text-text-2">{t("data.provenanceText")}</p>
      </CardContent>
    </Card>
  );
}
