import { Pause, Play } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useFinalController } from "@/shared/api/queries";
import { ChartCard } from "@/shared/charts/ChartCard";
import { EmptyData, QueryState } from "@/shared/components/QueryState";
import { useFormat, useTx } from "@/shared/domain/format";
import { methodLabel } from "@/shared/domain/methods";
import { usePageTitle } from "@/shared/lib/use-page-title";
import type { FinalController } from "@/shared/schemas";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";
import { PageHeader } from "@/shared/ui/page-header";

/** Pictures of the report and of the demonstration (scripts/combined_figures.py). */
const picture = (name: string) => `${import.meta.env.BASE_URL}combined/${name}`;

export default function FinalControllerPage() {
  const { t } = useTranslation();
  usePageTitle(t("pages.finalController.title"));
  const query = useFinalController();
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("pages.finalController.title")}
        description={t("pages.finalController.description")}
      />
      <QueryState query={query} height={320}>
        {(data) =>
          data ? (
            <Content data={data} />
          ) : (
            <EmptyData title={t("data.pending")} text={t("data.pendingText")} />
          )
        }
      </QueryState>
    </div>
  );
}

function Content({ data }: { data: FinalController }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const pct = (v: number) => `${f.number(v, 1)} %`;
  const signed = (v: number) => `${v > 0 ? "+" : ""}${f.number(v, 1)} %`;
  const peak = data.ambulances.peak;
  const shown = data.tests.best + data.tests.noninf;
  const criteria = ["travel", "waiting", "ambulances", "pedestrians", "sensors"] as const;

  // the tables behind the figures, in the reader's language (one header per column)
  const compromise: Record<string, string>[] = data.compromise.map((row) => ({
    [t("finalController.columns.controller")]: methodLabel(row.controller),
    ...Object.fromEntries(
      criteria.map((c) => [t(`finalController.criteria.${c}`), `+${pct(row[c])}`]),
    ),
    [t("finalController.criteria.worst")]: `+${pct(row.worst)}`,
  }));
  const tests: Record<string, string>[] = data.tests36.map((row) => ({
    [t("finalController.columns.situation")]: [
      tx(`networks.${row.network}`),
      tx(`scenarios.${row.scenario}`),
      tx(`demands.${row.demand}`),
    ].join(" · "),
    [t("finalController.columns.metric")]: t(`finalController.criteria.${row.metric}`),
    [t("finalController.columns.reference")]: methodLabel(row.reference),
    [t("finalController.columns.gain")]: signed(row.gain),
    [t("finalController.columns.interval")]: `[${signed(row.low)} ; ${signed(row.high)}]`,
    [t("finalController.columns.verdict")]: t(`finalController.verdicts.${row.verdict}`),
  }));
  const delays: Record<string, string>[] = data.ambulanceDelays.map((row) => ({
    [t("finalController.columns.demand")]: tx(`demands.${row.demand}`),
    [t("finalController.columns.controller")]: methodLabel(row.controller),
    [t("finalController.columns.delay")]: `${f.number(row.mean, 1)} s`,
    [t("finalController.columns.interval")]:
      `[${f.number(row.low, 1)} ; ${f.number(row.high, 1)}] s`,
  }));

  return (
    <>
      <section aria-label={t("finalController.messages")} className="grid gap-4 md:grid-cols-3">
        <Message
          title={t("finalController.worstGap.title")}
          value={pct(data.worstGap.candidate)}
          text={t("finalController.worstGap.text", {
            min: pct(data.worstGap.othersMin),
            max: pct(data.worstGap.othersMax),
          })}
        />
        <Message
          title={t("finalController.ambulances.title")}
          value={`${peak.faster} / ${peak.total}`}
          text={t("finalController.ambulances.text", {
            gain: f.number(peak.medianGainS, 0),
            run1: `${peak.run1Faster} / ${peak.run1Total}`,
          })}
        />
        <Message
          title={t("finalController.tests.title")}
          value={`${shown} / ${data.tests.total}`}
          text={t("finalController.tests.text", {
            best: data.tests.best,
            loss: data.tests.loss,
            wide: data.tests.wide,
          })}
        />
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>{t("finalController.canSay.title")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc space-y-2 ps-5 text-sm text-text-2">
              <li>{t("finalController.canSay.one")}</li>
              <li>{t("finalController.canSay.two")}</li>
              <li>{t("finalController.canSay.three")}</li>
            </ul>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>{t("finalController.cannotSay.title")}</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="list-disc space-y-2 ps-5 text-sm text-text-2">
              <li>{t("finalController.cannotSay.one")}</li>
              <li>{t("finalController.cannotSay.two")}</li>
              <li>{t("finalController.cannotSay.three")}</li>
            </ul>
          </CardContent>
        </Card>
      </div>

      <ChartCard
        title={t("finalController.figures.compromise")}
        description={t("finalController.figures.compromiseText")}
        table={compromise}
        csvName="final_controller_compromise"
      >
        <Figure name="fig_compromis.png" alt={t("finalController.figures.compromiseAlt")} />
      </ChartCard>
      <ChartCard
        title={t("finalController.figures.forest")}
        description={t("finalController.figures.forestText")}
        table={tests}
        csvName="final_controller_tests"
      >
        <Figure name="fig_forest.png" alt={t("finalController.figures.forestAlt")} />
      </ChartCard>
      <ChartCard
        title={t("finalController.figures.ambulances")}
        description={t("finalController.figures.ambulancesText")}
        table={delays}
        csvName="final_controller_ambulances"
      >
        <Figure name="fig_ambulances.png" alt={t("finalController.figures.ambulancesAlt")} />
      </ChartCard>

      <Demo data={data} />

      <Card>
        <CardHeader>
          <CardTitle>{t("finalController.honest.title")}</CardTitle>
          <CardDescription>{t("finalController.honest.text")}</CardDescription>
        </CardHeader>
        <CardContent className="text-sm text-text-2">
          <p>{t("finalController.llm")}</p>
          <p className="mt-2">{t("finalController.credit")}</p>
          <p className="mt-2 text-xs text-text-2">{data.source}</p>
        </CardContent>
      </Card>
    </>
  );
}

function Message({ title, value, text }: { title: string; value: string; text: string }) {
  return (
    <Card>
      <CardHeader>
        <CardDescription>{title}</CardDescription>
        <CardTitle className="text-3xl font-semibold">{value}</CardTitle>
      </CardHeader>
      <CardContent className="text-sm text-text-2">{text}</CardContent>
    </Card>
  );
}

function Figure({ name, alt }: { name: string; alt: string }) {
  return (
    <img
      src={picture(name)}
      alt={alt}
      loading="lazy"
      className="w-full rounded-md border border-border bg-white"
    />
  );
}

function Demo({ data }: { data: FinalController }) {
  const { t } = useTranslation();
  const f = useFormat();
  // the recording moves for about 30 s: it starts only on request (WCAG 2.2.2)
  const [playing, setPlaying] = useState(false);
  const d = data.demo;
  return (
    <ChartCard
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
      <img
        src={picture(playing ? "demo.gif" : "demo.png")}
        alt={t("finalController.demo.alt")}
        className="w-full rounded-md border border-border bg-white"
      />
      <p className="mt-3 text-xs text-text-2">{t("finalController.demo.command")}</p>
      <code className="mt-1 block overflow-x-auto rounded-md bg-surface-2 p-2 text-xs">
        python scripts/demo_side_by_side.py --left mp --right hybrid_h2 --net grid4x4 --demand peak
        --scenarios emergency --seed 0 --only-ev ev_1 --ev-view-width 160 --no-chart
      </code>
    </ChartCard>
  );
}
