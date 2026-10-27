import { useMemo } from "react";

import { useLlmRuns } from "@/shared/api/queries";
import { EmptyData, QueryState } from "@/shared/components/QueryState";
import { useFormat } from "@/shared/domain/format";
import { methodColor } from "@/shared/domain/methods";
import { usePageTitle } from "@/shared/lib/use-page-title";
import type { LlmRun } from "@/shared/schemas";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { PageHeader } from "@/shared/ui/page-header";

const sum = (rows: LlmRun[], key: keyof LlmRun) =>
  rows.reduce((total, row) => total + (Number(row[key]) || 0), 0);

export default function LlmMonitorPage() {
  usePageTitle("LLM monitor");
  const runs = useLlmRuns();
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="LLM monitor"
        description="Operational cost and call behaviour of the single-call LLM and the three-role team."
      />
      <QueryState query={runs} height={420}>
        {(rows) => <Monitor rows={rows} />}
      </QueryState>
    </div>
  );
}

function Monitor({ rows }: { rows: LlmRun[] }) {
  const f = useFormat();
  const team = useMemo(() => rows.filter((row) => row.method === "llm_team"), [rows]);
  const latency = team.filter((row) => row.latencyS != null);
  const cards = [
    { label: "Runs", value: f.number(rows.length, 0) },
    { label: "Team calls", value: f.number(sum(team, "calls"), 0) },
    { label: "Fallbacks", value: f.number(sum(team, "fallbacks"), 0) },
    { label: "Retries", value: f.number(sum(team, "retries"), 0) },
    { label: "Input tokens", value: f.number(sum(team, "tokensIn"), 0) },
    { label: "Output tokens", value: f.number(sum(team, "tokensOut"), 0) },
    {
      label: "Mean latency",
      value: latency.length
        ? `${f.number(sum(latency, "latencyS") / latency.length, 2)} s`
        : "–",
    },
    { label: "Estimated cost", value: `${f.number(sum(team, "costUsd"), 3)} USD` },
  ];

  if (!rows.length) return <EmptyData />;

  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card) => (
          <Card key={card.label}>
            <CardContent className="pt-4">
              <p className="text-xs font-medium text-text-2">{card.label}</p>
              <p className="mt-1 text-2xl font-semibold tabular text-text">{card.value}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Per-run calls and cost</CardTitle>
          <p className="text-xs text-muted">
            Cost uses the configured peak list price. Latency is per model call.
          </p>
        </CardHeader>
        <CardContent className="overflow-auto">
          <table className="w-full min-w-[860px] text-xs">
            <thead className="text-text-2">
              <tr className="border-b border-border">
                {[
                  "Scenario",
                  "Seed",
                  "Controller",
                  "Calls",
                  "Fallbacks",
                  "Retries",
                  "Tokens in",
                  "Tokens out",
                  "Latency",
                  "Cost",
                  "Wall",
                ].map((label) => (
                  <th key={label} className="px-2 py-2 text-start font-medium">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="tabular">
              {rows.map((row) => (
                <tr key={row.runId} className="border-b border-border/60">
                  <td className="px-2 py-2">{f.scenarioName(row.scenario)}</td>
                  <td className="px-2 py-2">{row.seed}</td>
                  <td className="px-2 py-2">
                    <span className="inline-flex items-center gap-1.5">
                      <span
                        className="size-2 rounded-full"
                        style={{ background: methodColor(row.method) }}
                      />
                      {f.methodName(row.method)}
                    </span>
                  </td>
                  <td className="px-2 py-2">{f.number(row.calls, 0)}</td>
                  <td className="px-2 py-2">{f.number(row.fallbacks, 0)}</td>
                  <td className="px-2 py-2">{f.number(row.retries, 0)}</td>
                  <td className="px-2 py-2">{f.number(row.tokensIn, 0)}</td>
                  <td className="px-2 py-2">{f.number(row.tokensOut, 0)}</td>
                  <td className="px-2 py-2">{f.number(row.latencyS, 2)} s</td>
                  <td className="px-2 py-2">{f.number(row.costUsd, 4)} USD</td>
                  <td className="px-2 py-2">{f.number(row.wallS, 1)} s</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </>
  );
}
