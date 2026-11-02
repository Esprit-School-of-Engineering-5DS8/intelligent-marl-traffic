import { Box, Download, Map as MapIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { orderReplays, withCandidate } from "@/features/replay/catalog";
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
import { ExploreHeader } from "@/shared/components/explore";

import { NewScenario } from "./NewScenario";
import { Runs } from "./Runs";

export default function ScenariosPage() {
  const { t } = useTranslation();
  usePageTitle(t("pages.scenarios.title"));
  const meta = useMeta();
  return (
    <div className="flex flex-col gap-6">
      <ExploreHeader
        page="scenarios"
        scope="replay"
        links={[
          { to: "/live-map", label: t("nav.liveMap") },
          { to: "/simulation-3d", label: t("nav.simulation3d") },
        ]}
      />
      <QueryState query={meta} height={200}>
        {(m) => (
          <>
            <div className="grid gap-4 xl:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
              <NewScenario meta={m} />
              <Runs />
            </div>
            <Replays meta={m} />
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
        {orderReplays(meta.replays).map((r) => (
          <li key={r.id}>
            <Card className="flex h-full flex-col">
              <CardHeader>
                <div className="flex flex-wrap gap-1">
                  {r.llm ? <Badge strong>{t("scenarioPage.tagLlm")}</Badge> : null}
                  {withCandidate(r) ? <Badge strong>{t("scenarioPage.tagCandidate")}</Badge> : null}
                  {r.scale !== undefined && r.scale !== 1 ? (
                    <Badge>{t("scenarioPage.tagBig", { scale: f.number(r.scale) })}</Badge>
                  ) : null}
                </div>
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

function Badge({ children, strong }: { children: string; strong?: boolean }) {
  return (
    <span
      className={
        strong
          ? "rounded-full bg-text px-2 py-0.5 text-[10.5px] font-semibold text-bg"
          : "rounded-full border border-border-strong px-2 py-0.5 text-[10.5px] font-medium text-text-2"
      }
    >
      {children}
    </span>
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
      `cotraffic_${cell.network}_${cell.scenario}_${cell.demand}.csv`,
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
