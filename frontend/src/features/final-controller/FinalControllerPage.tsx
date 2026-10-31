import { Layers3, Pause, Play, Scale } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ambulanceDelay, summarize } from "@/features/combined/claims";
import {
  useBilan,
  useCells,
  useFinalController,
  useLayers,
  useStudy,
  useTests,
  useValidation,
} from "@/shared/api/queries";
import { ClaimsBlock, EvidenceBadge, PlainBox, SourceNote } from "@/shared/components/evidence";
import { QueriesState } from "@/shared/components/QueriesState";
import { Panel, Section } from "@/shared/components/section";
import { AnimatedNumber, StatTile } from "@/shared/components/stat";
import { useFormat } from "@/shared/domain/format";
import { methodColorVar } from "@/shared/domain/methods";
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
    <div className="mx-auto flex max-w-7xl flex-col gap-8">
      <header className="flex flex-col gap-3">
        <p className="eyebrow">{t("final.eyebrow")}</p>
        <h1 className="text-3xl font-semibold tracking-tight text-balance text-text md:text-4xl">
          {t("pages.finalController.title")}
        </h1>
        <p className="max-w-3xl text-base leading-relaxed text-text-2">{t("final.lead")}</p>
      </header>
      <QueriesState queries={queries} height={480}>
        {(d) => (
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
            <TabsContent value="results" className="flex flex-col gap-12">
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
  const unfavourable = [...new Set(s.wideUnfavourable.map((r) => f.cellName(r)))].join(" ; ");

  return (
    <>
      <section aria-label={t("finalController.messages")} className="grid gap-4 lg:grid-cols-3">
        <StatTile
          label={t("final.messages.holds.label")}
          accent={methodColorVar("hybrid_h2")}
          value={
            <>
              <AnimatedNumber value={s.holds} format={(v) => f.number(Math.round(v), 0)} />{" "}
              <span className="text-2xl font-medium text-text-2">/ {s.total}</span>
            </>
          }
          badges={<EvidenceBadge kind="prereg" />}
          context={t("final.messages.holds.context", {
            best: s.best,
            loss: s.loss,
            wide: s.wide,
            margin: f.number(study.marginPct, 0),
          })}
        />
        <StatTile
          label={t("final.messages.worst.label")}
          accent={methodColorVar("hybrid_h2")}
          value={<AnimatedNumber value={final.worstGap.candidate} format={pct} />}
          badges={<EvidenceBadge kind="descriptive" />}
          context={t("final.messages.worst.context", {
            min: pct(final.worstGap.othersMin),
            max: pct(final.worstGap.othersMax),
          })}
        />
        <StatTile
          label={t("final.messages.ambulances.label")}
          accent={methodColorVar("hybrid_h2")}
          value={
            <>
              <AnimatedNumber value={peak.faster} format={(v) => f.number(Math.round(v), 0)} />{" "}
              <span className="text-2xl font-medium text-text-2">/ {peak.total}</span>
            </>
          }
          badges={<EvidenceBadge kind="secondary" />}
          context={t("final.messages.ambulances.context", {
            models: study.models,
            gain: f.number(peak.medianGainS, 0),
            run1: `${peak.run1Faster} / ${peak.run1Total}`,
          })}
        />
      </section>

      <Section
        id="forest"
        title={t("final.forest.title", { n: s.total })}
        description={t("final.forest.text", { margin: f.number(study.marginPct, 0) })}
        badges={<EvidenceBadge kind="prereg" />}
      >
        <Panel className="flex flex-col gap-5">
          <ForestControls filters={filters} tests={tests} margin={study.marginPct} />
          <ForestPlot tests={tests} cells={cells} margin={study.marginPct} filters={filters} />
        </Panel>
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
        <SourceNote
          source="combined/tests.json · results/combined/analysis_tests.csv"
          extra={t("final.prereg", { commit: study.prereg })}
        />
      </Section>

      <Section
        id="compromise"
        title={t("final.compromise.title")}
        description={t("final.compromise.text")}
        badges={<EvidenceBadge kind="descriptive" />}
      >
        <Panel>
          <CompromiseMatrix final={final} />
        </Panel>
        <PlainBox>{t("final.compromise.plain")}</PlainBox>
        <SourceNote source="final_controller.json (compromise) · scripts/combined_figures.py" />
      </Section>

      <Section
        id="ambulances"
        title={t("final.ambulances.title")}
        description={
          cand && mp
            ? t("final.ambulances.text", {
                candidate: f.number(cand.mean, 0),
                mp: f.number(mp.mean, 0),
                faster: peak.faster,
                total: peak.total,
              })
            : undefined
        }
        badges={<EvidenceBadge kind="secondary" />}
      >
        <Panel>
          <AmbulanceChart final={final} />
        </Panel>
        <SourceNote source="final_controller.json (ambulanceDelays, ambulances) · results/combined/raw" />
      </Section>

      <Section
        id="bilan"
        title={t("final.bilan.title")}
        description={t("final.bilan.text")}
        badges={<EvidenceBadge kind="exploratory" />}
      >
        <Panel>
          <BilanBars bilan={bilan} />
        </Panel>
        <SourceNote source={bilan.source} />
      </Section>

      <Section
        id="table"
        title={t("final.table.title")}
        description={t("final.table.text")}
        badges={<EvidenceBadge kind="prereg" />}
      >
        <TestsTable tests={tests} cells={cells} filters={filters} />
      </Section>

      <Demo final={final} />

      <Section id="llm" title={t("final.llm.title")} badges={<EvidenceBadge kind="secondary" />}>
        <Panel className="flex flex-col gap-3 text-sm leading-relaxed text-text-2">
          <p>{t("finalController.llm")}</p>
          <p>{t("finalController.credit")}</p>
        </Panel>
        <SourceNote source={final.source} />
      </Section>
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
    <Section
      id="demo"
      title={t("finalController.demo.title")}
      description={t("finalController.demo.text", {
        vehicle: d.vehicle,
        seed: d.seed,
        mp: `${f.number(d.delayMpS, 0)} s`,
        candidate: `${f.number(d.delayCandidateS, 0)} s`,
      })}
      actions={
        <Button variant="outline" size="sm" onClick={() => setPlaying((v) => !v)}>
          {playing ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
          {playing ? t("finalController.demo.stop") : t("finalController.demo.play")}
        </Button>
      }
    >
      <Panel>
        <img
          src={picture(playing ? "demo.gif" : "demo.png")}
          alt={t("finalController.demo.alt")}
          className="w-full rounded-lg border border-border bg-white"
        />
        <p className="mt-3 text-xs text-text-2">{t("finalController.demo.command")}</p>
        <code className="mt-1 block overflow-x-auto rounded-md bg-surface-2 p-2 font-mono text-xs">
          python scripts/demo_side_by_side.py --left mp --right hybrid_h2 --net grid4x4 --demand
          peak --scenarios emergency --seed 0 --only-ev ev_1 --ev-view-width 160 --no-chart
        </code>
      </Panel>
    </Section>
  );
}
