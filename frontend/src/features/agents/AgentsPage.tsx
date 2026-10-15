import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { useDecisions, useMeta, useSummary, useTraining } from "@/shared/api/queries";
import { barsWithCi, lines } from "@/shared/charts/builders";
import { ChartCard } from "@/shared/charts/ChartCard";
import { EChart } from "@/shared/charts/EChart";
import type { ChartTokens } from "@/shared/charts/tokens";
import { Select } from "@/shared/components/pickers";
import { EmptyData, QueryState } from "@/shared/components/QueryState";
import { useFormat } from "@/shared/domain/format";
import { methodColor, sortMethods } from "@/shared/domain/methods";
import { usePageTitle } from "@/shared/lib/use-page-title";
import { useRtl } from "@/shared/lib/use-rtl";
import type { Decisions, Meta, SummaryRow, Training } from "@/shared/schemas";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent } from "@/shared/ui/card";
import { PageHeader } from "@/shared/ui/page-header";

import { DecisionTimeline } from "./DecisionTimeline";

const SEED_COLORS = ["#2a78d6", "#eda100", "#1baf7a", "#d6337a", "#7c6cf0"];
const REWARD_TERMS = ["reward_delay", "reward_co2", "reward_ev", "reward_ped"];

function movingAverage(values: (number | null)[], window = 5): (number | null)[] {
  return values.map((_, i) => {
    const slice = values
      .slice(Math.max(0, i - window + 1), i + 1)
      .filter((v): v is number => v !== null);
    return slice.length ? slice.reduce((a, b) => a + b, 0) / slice.length : null;
  });
}

export default function AgentsPage() {
  const { t } = useTranslation();
  usePageTitle(t("pages.agents.title"));
  const meta = useMeta();
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={t("pages.agents.title")} description={t("pages.agents.description")} />
      <QueryState query={meta} height={80}>
        {(m) => (
          <>
            <LearningCurves meta={m} />
            <RewardTerms />
            <DecisionsExplorer meta={m} />
          </>
        )}
      </QueryState>
    </div>
  );
}

function LearningCurves({ meta }: { meta: Meta }) {
  const { t } = useTranslation();
  const f = useFormat();
  const agents = sortMethods(new Set(meta.training.map((x) => x.agent)));
  const [agent, setAgent] = useState(
    agents.includes("coop_full") ? "coop_full" : (agents[0] ?? ""),
  );
  const networks = meta.training.filter((x) => x.agent === agent).map((x) => x.network);
  const [network, setNetwork] = useState("grid4x4");
  const net = networks.includes(network) ? network : (networks[0] ?? "");
  const query = useTraining(agent, net);

  return (
    <section aria-labelledby="training-title" className="flex flex-col gap-3">
      <h2 id="training-title" className="text-sm font-semibold text-text">
        {t("agents.training")}
      </h2>
      <Card>
        <CardContent className="grid gap-3 pt-4 sm:grid-cols-3">
          <Select
            label={t("agents.agent")}
            value={agent}
            options={agents.map((a) => ({ value: a, label: f.methodName(a) }))}
            onChange={setAgent}
          />
          <Select
            label={t("filters.network")}
            value={net}
            options={networks.map((n) => ({ value: n, label: f.networkName(n) }))}
            onChange={setNetwork}
          />
          <p className="self-end text-xs text-text-2">{t("agents.trainingText")}</p>
        </CardContent>
      </Card>
      <QueryState query={query} height={300} empty={<EmptyData text={t("agents.noTraining")} />}>
        {(training) => <Curves training={training} />}
      </QueryState>
    </section>
  );
}

function Curves({ training }: { training: Training }) {
  const { t } = useTranslation();
  const f = useFormat();
  const rtl = useRtl();
  const runs = training.runs;
  const longest = runs.reduce(
    (a, b) => (b.timesteps.length > a.timesteps.length ? b : a),
    runs[0]!,
  );
  const x = longest.timesteps;
  const align = (values: (number | null)[], steps: number[]) =>
    x.map((s) => {
      const i = steps.indexOf(s);
      return i === -1 ? null : (values[i] ?? null);
    });

  // plain builders: the chart redraws when this component renders (rarely: on a new choice)
  const build = (key: "episodeReward" | "meanHalting") => (tk: ChartTokens) =>
    lines(tk, {
      x: x.map((s) => Math.round(s / 1000)),
      series: runs.map((r, i) => ({
        name: t("agents.seed", { seed: r.seed }),
        color: SEED_COLORS[i % SEED_COLORS.length]!,
        data: align(movingAverage(r[key]), r.timesteps),
      })),
      xName: `${t("agents.timesteps")} (k)`,
      yName: key === "episodeReward" ? t("agents.reward") : t("agents.halting"),
      format: (v) => f.number(v, 2),
      rtl,
      dataZoom: true,
    });
  const reward = build("episodeReward");
  const halting = build("meanHalting");
  const algorithm = runs[0]?.algorithm.toUpperCase() ?? "PPO";
  const episodes = runs.reduce((a, r) => a + r.timesteps.length, 0);

  return (
    <div className="grid gap-4 xl:grid-cols-2">
      <ChartCard
        title={t("agents.reward")}
        actions={
          <div className="flex gap-1.5">
            <Badge tone="accent">
              {t("agents.algorithm")} : {algorithm}
            </Badge>
            <Badge>{t("agents.episodes", { n: episodes })}</Badge>
          </div>
        }
      >
        <EChart build={reward} height={300} label={t("agents.reward")} />
      </ChartCard>
      <ChartCard title={t("agents.halting")}>
        <EChart build={halting} height={300} label={t("agents.halting")} />
      </ChartCard>
    </div>
  );
}

function RewardTerms() {
  const summary = useSummary();
  return (
    <QueryState query={summary} height={260}>
      {(rows) => <RewardTermsChart rows={rows} />}
    </QueryState>
  );
}

function RewardTermsChart({ rows }: { rows: SummaryRow[] }) {
  const { t } = useTranslation();
  const f = useFormat();
  const rtl = useRtl();
  const terms = rows.filter((r) => REWARD_TERMS.includes(r.metric) && r.mean !== null);
  const cells = [...new Set(terms.map((r) => `${r.network}__${r.scenario}__${r.demand}`))].sort();
  const [cell, setCell] = useState(cells[0] ?? "");
  const current = cells.includes(cell) ? cell : (cells[0] ?? "");
  const inCell = terms.filter((r) => `${r.network}__${r.scenario}__${r.demand}` === current);
  const methods = sortMethods(new Set(inCell.map((r) => r.method)));
  const items = methods
    .flatMap((m) =>
      REWARD_TERMS.map((term) => ({
        m,
        term,
        row: inCell.find((r) => r.method === m && r.metric === term),
      })),
    )
    .filter((d) => d.row && Math.abs(d.row.mean ?? 0) > 1e-9);

  const build = (tk: ChartTokens) =>
    barsWithCi(tk, {
      categories: items.map(
        (d) => `${f.methodName(d.m)} · ${f.metricName(d.term).split(":").pop()?.trim()}`,
      ),
      values: items.map((d) => d.row?.mean ?? null),
      lo: items.map((d) => d.row?.ciLo ?? null),
      hi: items.map((d) => d.row?.ciHi ?? null),
      colors: items.map((d) => methodColor(d.m)),
      axisName: "",
      format: (v) => f.number(v, 3),
      rtl,
    });

  return (
    <ChartCard
      title={t("agents.rewardTerms")}
      description={t("agents.rewardTermsText")}
      actions={
        cells.length > 1 ? (
          <div className="w-64">
            <Select
              label={t("filters.scenario")}
              value={current}
              options={cells.map((c) => {
                const [network = "", scenario = "", demand = ""] = c.split("__");
                return { value: c, label: f.cellName({ network, scenario, demand }) };
              })}
              onChange={setCell}
            />
          </div>
        ) : undefined
      }
    >
      {items.length ? (
        <EChart build={build} height={300} label={t("agents.rewardTerms")} />
      ) : (
        <EmptyData title={t("data.pending")} text={t("data.pendingText")} />
      )}
    </ChartCard>
  );
}

function DecisionsExplorer({ meta }: { meta: Meta }) {
  const { t } = useTranslation();
  const f = useFormat();
  const [runId, setRunId] = useState(
    meta.decisions.find((d) => d.method === "coop_full")?.runId ?? meta.decisions[0]?.runId ?? "",
  );
  const query = useDecisions(runId || null);
  return (
    <section aria-labelledby="decisions-title" className="flex flex-col gap-3">
      <h2 id="decisions-title" className="text-sm font-semibold text-text">
        {t("agents.decisions")}
      </h2>
      <p className="-mt-2 text-xs text-text-2">{t("agents.decisionsText")}</p>
      <Card>
        <CardContent className="pt-4">
          <Select
            label={t("agents.run")}
            value={runId}
            options={meta.decisions.map((d) => ({
              value: d.runId,
              label: `${f.methodName(d.method)} · ${f.cellName(d)} · s${d.seed}`,
            }))}
            onChange={setRunId}
          />
        </CardContent>
      </Card>
      <QueryState query={query} height={360}>
        {(d) => <DecisionsView decisions={d} />}
      </QueryState>
    </section>
  );
}

const PAGE = 40;

function DecisionsView({ decisions }: { decisions: Decisions }) {
  const { t } = useTranslation();
  const f = useFormat();
  const [agent, setAgent] = useState(decisions.agents[0] ?? "");
  const [page, setPage] = useState(0);
  const rows = useMemo(
    () =>
      decisions.time
        .map((time, i) => ({
          time,
          agent: decisions.agent[i]!,
          requested: decisions.requested[i]!,
          executed: decisions.executed[i]!,
          shield: decisions.shield[i]!,
          explanation: decisions.explanation[i]!,
        }))
        .filter((r) => r.agent === agent),
    [decisions, agent],
  );
  const corrected = rows.filter((r) => r.shield && r.shield !== "none").length;
  const switches = rows.filter((r, i) => i > 0 && r.executed !== rows[i - 1]!.executed).length;
  const pages = Math.max(1, Math.ceil(rows.length / PAGE));
  const shown = rows.slice(page * PAGE, page * PAGE + PAGE);

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <CardContent className="flex flex-wrap items-end gap-4 pt-4">
          <div className="w-48">
            <Select
              label={t("agents.intersection")}
              value={agent}
              options={decisions.agents.map((a) => ({ value: a, label: a }))}
              onChange={(a) => {
                setAgent(a);
                setPage(0);
              }}
            />
          </div>
          <dl className="tabular flex gap-6 text-xs">
            <div>
              <dt className="text-muted">{t("agents.shieldShare")}</dt>
              <dd className="text-sm font-semibold text-text">
                {f.pct(rows.length ? (100 * corrected) / rows.length : null, 1, false)}
              </dd>
            </div>
            <div>
              <dt className="text-muted">{t("agents.switches")}</dt>
              <dd className="text-sm font-semibold text-text">{f.number(switches, 0)}</dd>
            </div>
          </dl>
        </CardContent>
      </Card>
      <DecisionTimeline rows={rows} />
      <div
        tabIndex={0}
        role="region"
        aria-label={t("agents.decisions")}
        className="overflow-auto rounded-lg border border-border"
      >
        <table className="w-full text-xs">
          <caption className="sr-only">{t("agents.decisions")}</caption>
          <thead className="bg-surface-2 text-text-2">
            <tr>
              {[
                t("agents.time"),
                t("agents.requested"),
                t("agents.executed"),
                t("agents.shield"),
                t("agents.explanation"),
              ].map((h) => (
                <th key={h} scope="col" className="px-2 py-2 text-start font-medium">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="tabular">
            {shown.map((r, i) => (
              <tr key={i} className="border-t border-border">
                <td className="px-2 py-1.5 text-text-2">{f.clock(r.time)}</td>
                <td className="px-2 py-1.5">{r.requested}</td>
                <td className="px-2 py-1.5">{r.executed}</td>
                <td className="px-2 py-1.5">
                  {r.shield && r.shield !== "none" ? (
                    <Badge tone="dense">{r.shield}</Badge>
                  ) : (
                    <span className="text-muted">{t("agents.none")}</span>
                  )}
                </td>
                <td className="px-2 py-1.5 text-text">{r.explanation}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center justify-end gap-2 text-xs text-text-2">
        <Button
          size="sm"
          variant="ghost"
          disabled={page === 0}
          onClick={() => setPage((p) => p - 1)}
          aria-label="‹"
        >
          ‹
        </Button>
        <span className="tabular">
          {page + 1} / {pages}
        </span>
        <Button
          size="sm"
          variant="ghost"
          disabled={page >= pages - 1}
          onClick={() => setPage((p) => p + 1)}
          aria-label="›"
        >
          ›
        </Button>
      </div>
    </div>
  );
}
