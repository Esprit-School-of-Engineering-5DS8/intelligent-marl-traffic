import { useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { useSettings } from "@/features/settings/store";
import { useRuns } from "@/shared/api/backend";
import { useFormat, useTx } from "@/shared/domain/format";
import type { Run } from "@/shared/schemas";
import { Badge } from "@/shared/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";

const TONE: Record<Run["status"], "neutral" | "dense" | "flow" | "jam"> = {
  queued: "neutral",
  running: "dense",
  done: "flow",
  failed: "jam",
};

/** Simulations launched on the backend, refreshed while they run. */
export function Runs() {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const live = useSettings((s) => s.dataSource) === "live";
  const runs = useRuns();
  const client = useQueryClient();
  const done = runs.data?.filter((r) => r.status === "done").length ?? 0;

  // a finished run adds a replay: reload the index
  useEffect(() => {
    if (done) void client.invalidateQueries({ queryKey: ["data", "live", "meta"] });
  }, [done, client]);

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("scenarioPage.runs")}</CardTitle>
      </CardHeader>
      <CardContent>
        {!live ? (
          <p className="text-xs text-muted">{t("scenarioPage.liveOnly")}</p>
        ) : runs.isError ? (
          <p role="alert" className="text-xs text-jam">
            {t("data.loadErrorLive")}
          </p>
        ) : !runs.data?.length ? (
          <p className="text-xs text-muted">{t("scenarioPage.noRuns")}</p>
        ) : (
          <ul className="flex flex-col gap-2" aria-live="polite">
            {runs.data.map((r) => (
              <li key={r.id} className="flex flex-col gap-1 rounded-md border border-border p-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-text">
                    {String(r.request.network)} · {String(r.request.demand)} ·{" "}
                    {f.methodName(String(r.request.left))} / {f.methodName(String(r.request.right))}
                  </span>
                  <Badge tone={TONE[r.status]}>{tx(`scenarioPage.status.${r.status}`)}</Badge>
                </div>
                {r.log?.length ? (
                  <p className="truncate font-mono text-[11px] text-muted">
                    {r.log[r.log.length - 1]}
                  </p>
                ) : null}
                {r.error ? <p className="text-[11px] text-jam">{r.error}</p> : null}
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
