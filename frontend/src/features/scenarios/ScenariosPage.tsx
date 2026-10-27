import { Box, Download, Map as MapIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { replayTitle } from "@/features/replay/title";
import { usePlayback } from "@/features/replay/store";
import { useMeta, useSummary } from "@/shared/api/queries";
import { QueryState } from "@/shared/components/QueryState";
import { CellPicker } from "@/shared/components/pickers";
import { sameCell } from "@/shared/domain/cells";
import { useFormat } from "@/shared/domain/format";
import { methodColor } from "@/shared/domain/methods";
import { downloadCsv } from "@/shared/lib/csv";
import { usePageTitle } from "@/shared/lib/use-page-title";
import type { Meta, SummaryRow } from "@/shared/schemas";
import { useFilters } from "@/shared/state/filters";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";
import { PageHeader } from "@/shared/ui/page-header";

import { NewScenario } from "./NewScenario";
import { Runs } from "./Runs";

export default function ScenariosPage() {
  const { t } = useTranslation();
  usePageTitle(t("pages.scenarios.title"));
  const meta = useMeta();
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("pages.scenarios.title")}
        description={t("pages.scenarios.description")}
      />
      <QueryState query={meta} height={200}>
        {(m) => (
          <>
            <Replays meta={m} />
            <div className="grid gap-4 xl:grid-cols-2">
              <NewScenario meta={m} />
              <Runs />
            </div>
            <ExportCell meta={m} />
          </>
        )}
      </QueryState>
    </div>
  );
}

function Replays({ meta }: { meta: Meta }) {
  const { t } = useTranslation();
  const f = useFormat();
  const navigate = useNavigate();
  const setReplay = usePlayback((s) => s.setReplay);
  const open = (id: string, path: string) => {
    setReplay(id);
    void navigate(path);
  };
  return (
    <section aria-labelledby="replays-title" className="flex flex-col gap-3">
      <div>
        <h2 id="replays-title" className="text-sm font-semibold text-text">
          {t("scenarioPage.replays")}
        </h2>
        <p className="text-xs text-text-2">{t("scenarioPage.replaysText")}</p>
      </div>
      <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {meta.replays.map((r) => (
          <li key={r.id}>
            <Card className="flex h-full flex-col">
              <CardHeader>
                <CardTitle className="text-[13px]">{replayTitle(r.id, f)}</CardTitle>
                <CardDescription className="flex flex-wrap items-center gap-1.5">
                  <span
                    aria-hidden="true"
                    className="size-2 rounded-full"
                    style={{ background: methodColor(r.left) }}
                  />
                  {f.methodName(r.left)}
                  <span aria-hidden="true">·</span>
                  <span
                    aria-hidden="true"
                    className="size-2 rounded-full"
                    style={{ background: methodColor(r.right) }}
                  />
                  {f.methodName(r.right)}
                  <span className="text-muted">
                    · {t("scenarioPage.window", { minutes: Math.round(r.window / 60) })}
                  </span>
                </CardDescription>
              </CardHeader>
              <CardContent className="mt-auto flex gap-2">
                <Button size="sm" variant="secondary" onClick={() => open(r.id, "/live-map")}>
                  <MapIcon aria-hidden="true" />
                  {t("scenarioPage.openMap")}
                </Button>
                <Button size="sm" variant="secondary" onClick={() => open(r.id, "/simulation-3d")}>
                  <Box aria-hidden="true" />
                  {t("scenarioPage.open3d")}
                </Button>
              </CardContent>
            </Card>
          </li>
        ))}
      </ul>
    </section>
  );
}

function ExportCell({ meta }: { meta: Meta }) {
  const { t } = useTranslation();
  const summary = useSummary();
  const { cell, setCell } = useFilters();
  const exportRows = (rows: SummaryRow[]) =>
    downloadCsv(
      rows
        .filter((r) => sameCell(r, cell))
        .map((r) => ({
          network: r.network,
          scenario: r.scenario,
          demand: r.demand,
          controller: r.method,
          metric: r.metric,
          n: r.n,
          mean: r.mean,
          ci_lo: r.ciLo,
          ci_hi: r.ciHi,
          std: r.std,
        })),
      `kemetra_${cell.network}_${cell.scenario}_${cell.demand}.csv`,
    );
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("scenarioPage.exportCell")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 sm:flex-row sm:items-end">
        <div className="flex-1">
          <CellPicker meta={meta} value={cell} onChange={setCell} />
        </div>
        <Button
          variant="outline"
          disabled={!summary.data}
          onClick={() => summary.data && exportRows(summary.data)}
        >
          <Download aria-hidden="true" />
          {t("data.exportCsv")}
        </Button>
      </CardContent>
    </Card>
  );
}
