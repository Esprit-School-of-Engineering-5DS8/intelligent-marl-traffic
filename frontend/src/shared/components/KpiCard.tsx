import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useFormat } from "@/shared/domain/format";
import { gainPct } from "@/shared/domain/metrics";
import { cn } from "@/shared/lib/cn";
import type { Comparison, SummaryRow } from "@/shared/schemas";
import { Badge } from "@/shared/ui/badge";

/**
 * One indicator of the selected controller against the reference. The gain is the paired
 * improvement of the statistical test when one exists (with its significance after Holm
 * correction), otherwise the relative difference of the two means.
 */
export function KpiCard({
  metric,
  row,
  referenceRow,
  comparison,
  reference,
}: {
  metric: string;
  row?: SummaryRow;
  referenceRow?: SummaryRow;
  comparison?: Comparison;
  reference: string;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const value = row?.mean ?? null;
  const ref = referenceRow?.mean ?? null;
  const gain =
    comparison?.pairedImprovementPct ??
    (value !== null && ref !== null ? gainPct(metric, value, ref) : null);
  const better = gain !== null && gain > 0.05;
  const worse = gain !== null && gain < -0.05;
  // the arrow shows the direction of the change, the colour whether it is an improvement
  const down = value !== null && ref !== null && value < ref;
  const Icon = !better && !worse ? Minus : down ? ArrowDownRight : ArrowUpRight;

  return (
    <section
      aria-label={f.metricName(metric)}
      className="flex flex-col gap-2 rounded-lg border border-border bg-surface p-4"
    >
      <h3 className="text-xs font-medium text-text-2">{f.metricName(metric)}</h3>
      <p className="tabular text-2xl font-semibold tracking-tight text-text">
        {f.metric(value, metric)}
      </p>
      {row && row.ciLo !== null && row.ciHi !== null ? (
        <p className="tabular text-[11px] text-muted">
          {t("kpi.ci")} {f.metric(row.ciLo, metric)} – {f.metric(row.ciHi, metric)} ·{" "}
          {t("kpi.runs", { n: row.n })}
        </p>
      ) : null}
      <div className="mt-auto flex flex-wrap items-center gap-1.5 text-xs">
        {gain === null ? (
          <span className="text-muted">{t("kpi.noReference")}</span>
        ) : (
          <>
            <Badge tone={better ? "flow" : worse ? "jam" : "neutral"}>
              <Icon aria-hidden="true" />
              {f.pct(gain)} {better ? t("kpi.better") : worse ? t("kpi.worse") : ""}
            </Badge>
            <span className="text-muted">
              {t("kpi.vs", { ref: f.methodName(reference) })} ({f.metric(ref, metric)})
            </span>
            {comparison ? (
              <span
                className={cn("text-[11px]", comparison.significant ? "text-text-2" : "text-muted")}
              >
                {comparison.significant ? t("kpi.significant") : t("kpi.notSignificant")}
              </span>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
