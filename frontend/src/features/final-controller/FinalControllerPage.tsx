import { Layers3, Pause, Play, Scale } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ambulanceDelay, summarize } from "@/features/combined/claims";
import { TripDots, VerdictWaffle, WorstGapBars } from "@/features/combined/visuals";
import {
  useBilan,
  useCells,
  useFinalController,
  useLayers,
  useStudy,
  useTests,
  useValidation,
} from "@/shared/api/queries";
import { ClaimsBlock, EvidenceBadge, SourceNote } from "@/shared/components/evidence";
import { Details, PageHero, Spotlight } from "@/shared/components/page";
import { QueriesState } from "@/shared/components/QueriesState";
import { useFormat } from "@/shared/domain/format";
import { methodLabel } from "@/shared/domain/methods";
import { usePageTitle } from "@/shared/lib/use-page-title";
import type { FinalController } from "@/shared/schemas";
import type { Bilan, Cells, Study, TestRow } from "@/shared/schemas/combined";
import { Button } from "@/shared/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/shared/ui/tabs";

import { AblationTab } from "./AblationTab";
import { useForestFilters } from "./forest";
import { ForestControls, ForestPlot } from "./ForestPlot";
import { AmbulanceChart, BilanBars, CompromiseMatrix, TestsTable } from "./results";

/** Pictures of the demonstration (scripts/combined_figures.py). */
const picture = (name: string) => `${import.meta.env.BASE_URL}combined/${name}`;

export default function FinalControllerPage() {
  const { t } = useTranslation();
  const f = useFormat();
  usePageTitle(t("pages.finalController.title"));
  const queries = {
    final: useFinalController(),
    study: useStudy(),
    tests: useTests(),
    cells: useCells(),
    bilan: useBilan(),
    layers: useLayers(),
    validation: useValidation(),
  };
  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-8">
      <QueriesState queries={queries} height={480}>
        {(d) => (
          <>
            <PageHero
              eyebrow={t("final.eyebrow")}
              title={t("results.title")}
              answer={t("results.answer", {
                worst: `${f.number(d.final.worstGap.candidate, 1)} %`,
                min: `${f.number(d.final.worstGap.othersMin, 0)} %`,
                max: `${f.number(d.final.worstGap.othersMax, 0)} %`,
              })}
              badges={<EvidenceBadge kind="prereg" />}
            />
            <Tabs defaultValue="results" className="flex flex-col gap-8">
              <TabsList aria-label={t("final.tabs.label")}>
                <TabsTrigger value="results">
                  <Scale aria-hidden="true" />
                  {t("final.tabs.results")}
                </TabsTrigger>
                <TabsTrigger value="ablation">
                  <Layers3 aria-hidden="true" />
                  {t("final.tabs.ablation")}
                </TabsTrigger>
              </TabsList>
              <TabsContent value="results" className="flex flex-col gap-8">
                <Results
                  final={d.final}
                  study={d.study}
                  tests={d.tests.tests}
                  cells={d.cells.cells}
                  bilan={d.bilan}
                />
              </TabsContent>
              <TabsContent value="ablation">
                <AblationTab
                  layers={d.layers}
                  tests={d.tests.tests}
                  validation={d.validation}
                  study={d.study}
                />
              </TabsContent>
            </Tabs>
          </>
        )}
      </QueriesState>
    </div>
  );
}

function Results({
  final,
  study,
  tests,
  cells,
  bilan,
}: {
  final: FinalController;
  study: Study;
  tests: TestRow[];
  cells: Cells["cells"];
  bilan: Bilan;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const filters = useForestFilters();
  const s = summarize(tests, study);
  const pct = (v: number) => `${f.number(v, 1)} %`;
  const peak = final.ambulances.peak;
  const cand = ambulanceDelay(final, "hybrid_h2", "peak");
  const mp = ambulanceDelay(final, "mp", "peak");
  const ev = ambulanceDelay(final, "ev_rule_mp", "peak");
  const unfavourable = [...new Set(s.wideUnfavourable.map((r) => f.cellName(r)))].join(" ; ");

  return (
    <>
      <section aria-label={t("finalController.messages")} className="flex flex-col gap-6">
        <Spotlight
          title={t("results.compromise.title")}
          message={t("results.compromise.message", {
            worst: pct(final.worstGap.candidate),
            min: pct(final.worstGap.othersMin),
            max: pct(final.worstGap.othersMax),
          })}
          footer={t("results.compromise.footer")}
          visual={<WorstGapBars final={final} size="lg" />}
        />
        <Spotlight
          title={t("results.tests.title", { total: s.total })}
          message={t("results.tests.message", {
            holds: s.holds,
            total: s.total,
            best: s.best,
            loss: s.loss,
            wide: s.wide,
          })}
          footer={t("results.tests.footer", { margin: f.number(study.marginPct, 0) })}
          visual={<VerdictWaffle tests={tests} />}
        />
        <Spotlight
          title={t("results.ambulances.title")}
          message={t("results.ambulances.message", { faster: peak.faster, total: peak.total })}
          footer={
            cand && mp && ev
              ? t("results.ambulances.footer", {
                  candidate: f.number(cand.mean, 0),
                  mp: f.number(mp.mean, 0),
                  ev: f.number(ev.mean, 0),
                  evName: methodLabel("ev_rule_mp"),
                })
              : undefined
          }
          visual={<TripDots faster={peak.faster} total={peak.total} rows={study.models} />}
        />
      </section>

      <ClaimsBlock
        can={[
          t("final.claims.can.holds", {
            n: s.holds,
            total: s.total,
            margin: f.number(study.marginPct, 0),
          }),
          t("final.claims.can.best", {
            n: s.best,
            list: s.bestRows
              .map((r) => `${f.cellName(r)} (${t(`final.metrics.${r.metric}`)})`)
              .join(" ; "),
          }),
        ]}
        cannot={[
          t("final.claims.cannot.losses", {
            n: s.loss,
            min: f.number(s.lossMin, 1),
            max: f.number(s.lossMax, 1),
          }),
          t("final.claims.cannot.wide", { n: s.wide, real: s.wideRealPeak }),
          t("final.claims.cannot.unfavourable", {
            list: unfavourable,
            seeds: study.testSeeds.length,
          }),
        ]}
      />

      <section aria-label={t("results.details")} className="flex flex-col gap-3">
        <h2 className="eyebrow">{t("results.details")}</h2>
        <Details
          title={t("final.forest.title", { n: s.total })}
          hint={t("final.forest.text", { margin: f.number(study.marginPct, 0) })}
          badges={<EvidenceBadge kind="prereg" />}
        >
          <div className="flex flex-col gap-5">
            <ForestControls filters={filters} tests={tests} margin={study.marginPct} />
            <ForestPlot tests={tests} cells={cells} margin={study.marginPct} filters={filters} />
          </div>
        </Details>
        <Details
          title={t("final.compromise.title")}
          hint={t("final.compromise.text")}
          badges={<EvidenceBadge kind="descriptive" />}
        >
          <CompromiseMatrix final={final} />
        </Details>
        <Details
          title={t("final.ambulances.title")}
          hint={t("results.ambulances.hint")}
          badges={<EvidenceBadge kind="secondary" />}
        >
          <AmbulanceChart final={final} />
        </Details>
        <Details
          title={t("final.bilan.title")}
          hint={t("final.bilan.text")}
          badges={<EvidenceBadge kind="exploratory" />}
        >
          <BilanBars bilan={bilan} />
        </Details>
        <Details
          title={t("final.table.title")}
          hint={t("final.table.text")}
          badges={<EvidenceBadge kind="prereg" />}
        >
          <TestsTable tests={tests} cells={cells} filters={filters} />
        </Details>
        <Demo final={final} />
      </section>

      <SourceNote
        source="combined/tests.json · final_controller.json · results/combined"
        extra={t("final.prereg", { commit: study.prereg })}
      />
    </>
  );
}

function Demo({ final }: { final: FinalController }) {
  const { t } = useTranslation();
  const f = useFormat();
  // the recording moves for about 30 s: it starts only on request (WCAG 2.2.2)
  const [playing, setPlaying] = useState(false);
  const d = final.demo;
  return (
    <Details
      title={t("finalController.demo.title")}
      hint={t("finalController.demo.text", {
        vehicle: d.vehicle,
        seed: d.seed,
        mp: `${f.number(d.delayMpS, 0)} s`,
        candidate: `${f.number(d.delayCandidateS, 0)} s`,
      })}
    >
      <div className="flex flex-col gap-3">
        <Button variant="outline" size="sm" className="w-fit" onClick={() => setPlaying((v) => !v)}>
          {playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
          {playing ? t("finalController.demo.stop") : t("finalController.demo.play")}
        </Button>
        <img
          src={picture(playing ? "demo.gif" : "demo.png")}
          alt={t("finalController.demo.alt")}
          className="w-full rounded-lg border border-border bg-white"
        />
        <p className="text-xs text-text-2">{t("finalController.demo.command")}</p>
        <code className="block overflow-x-auto rounded-md bg-surface-2 p-2 font-mono text-xs">
          python scripts/demo_side_by_side.py --left mp --right hybrid_h2 --net grid4x4 --demand
          peak --scenarios emergency --seed 0 --only-ev ev_1 --ev-view-width 160 --no-chart
        </code>
      </div>
    </Details>
  );
}
