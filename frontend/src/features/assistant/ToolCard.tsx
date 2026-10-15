import { MapPinned, Play } from "lucide-react";
import { useCallback, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { usePlayback } from "@/features/replay/store";
import { useUi } from "@/app/ui-store";
import { useCreateRun } from "@/shared/api/backend";
import { useMeta, useSummary } from "@/shared/api/queries";
import { barsWithCi } from "@/shared/charts/builders";
import { EChart } from "@/shared/charts/EChart";
import type { ChartTokens } from "@/shared/charts/tokens";
import { useFormat } from "@/shared/domain/format";
import { methodColor, sortMethods } from "@/shared/domain/methods";
import { indexSummary } from "@/shared/domain/results";
import { useRtl } from "@/shared/lib/use-rtl";
import { MUTATING_TOOLS, type ToolCall } from "@/shared/schemas";
import { Button } from "@/shared/ui/button";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";

import { useChat, type ToolState } from "./store";

/**
 * What a tool call proposes, shown as an interface element. Calls are data: reading ones
 * (chart, comparison) render at once; navigation waits for a click; state-changing ones
 * (launching a simulation) need an explicit confirmation.
 */
export function ToolCard({ messageId, tool }: { messageId: string; tool: ToolState }) {
  const { call } = tool;
  switch (call.name) {
    case "generateChart":
      return <ChartTool call={call} />;
    case "compareControllers":
      return <CompareTool call={call} />;
    case "focusIntersection":
      return <FocusTool call={call} />;
    case "runScenario":
      return <RunTool messageId={messageId} tool={tool} call={call} />;
    case "getKpis":
      return null;
  }
}

function Frame({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="rounded-md border border-border bg-surface-2 p-2">
      <p className="mb-1 text-[11px] font-medium text-muted">{title}</p>
      {children}
    </div>
  );
}

function ChartTool({ call }: { call: Extract<ToolCall, { name: "generateChart" }> }) {
  const { t } = useTranslation();
  const f = useFormat();
  const rtl = useRtl();
  const summary = useSummary();
  const { cell, metric } = call.args;
  const index = summary.data ? indexSummary(summary.data) : null;
  const methods = sortMethods(call.args.controllers);
  const rows = methods
    .map((m) => ({ m, row: index?.get(cell, m, metric) }))
    .filter((d) => d.row && d.row.mean !== null);
  const build = useCallback(
    (tk: ChartTokens) =>
      barsWithCi(tk, {
        categories: rows.map((d) => f.methodName(d.m)),
        values: rows.map((d) => f.metricValue(d.row?.mean, metric)),
        lo: rows.map((d) => f.metricValue(d.row?.ciLo, metric)),
        hi: rows.map((d) => f.metricValue(d.row?.ciHi, metric)),
        colors: rows.map((d) => methodColor(d.m)),
        axisName: f.metricUnit(metric),
        format: (v) => `${f.number(v)} ${f.metricUnit(metric)}`,
        rtl,
      }),
    [rows, f, metric, rtl],
  );
  return (
    <Frame
      title={`${t("assistantChat.toolChart")} · ${f.metricName(metric)} · ${f.cellName(cell)}`}
    >
      {rows.length ? (
        <EChart
          build={build}
          height={220}
          label={`${f.metricName(metric)} · ${f.cellName(cell)}`}
        />
      ) : null}
    </Frame>
  );
}

function CompareTool({ call }: { call: Extract<ToolCall, { name: "compareControllers" }> }) {
  const { t } = useTranslation();
  const f = useFormat();
  const summary = useSummary();
  const { cell, a, b, metric } = call.args;
  const index = summary.data ? indexSummary(summary.data) : null;
  return (
    <Frame title={t("assistantChat.toolCompare")}>
      <table className="w-full text-xs">
        <caption className="sr-only">{t("assistantChat.toolCompare")}</caption>
        <thead>
          <tr className="text-muted">
            <th scope="col" className="text-start font-medium">
              {t("filters.controller")}
            </th>
            <th scope="col" className="text-start font-medium">
              {f.metricName(metric)}
            </th>
            <th scope="col" className="text-start font-medium">
              {t("kpi.ci")}
            </th>
          </tr>
        </thead>
        <tbody className="tabular">
          {[a, b].map((m) => {
            const r = index?.get(cell, m, metric);
            return (
              <tr key={m}>
                <td className="py-0.5">
                  <span className="inline-flex items-center gap-1.5">
                    <span
                      aria-hidden="true"
                      className="size-2 rounded-full"
                      style={{ background: methodColor(m) }}
                    />
                    {f.methodName(m)}
                  </span>
                </td>
                <td>{f.metric(r?.mean, metric)}</td>
                <td className="text-muted">
                  {f.metric(r?.ciLo, metric)} – {f.metric(r?.ciHi, metric)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </Frame>
  );
}

function FocusTool({ call }: { call: Extract<ToolCall, { name: "focusIntersection" }> }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const meta = useMeta();
  const { setReplay, selectJunction, setSplit } = usePlayback();
  const closePanel = useUi((s) => s.setAssistantOpen);
  const replay = meta.data?.replays.find((r) => r.id.startsWith(`${call.args.network}__`));
  return (
    <Frame title={t("assistantChat.proposed")}>
      <Button
        size="sm"
        variant="secondary"
        disabled={!replay}
        onClick={() => {
          if (!replay) return;
          setReplay(replay.id);
          setSplit(true);
          selectJunction(call.args.junction);
          closePanel(false);
          void navigate("/live-map");
        }}
      >
        <MapPinned aria-hidden="true" />
        {t("assistantChat.toolFocus", { junction: call.args.junction })}
      </Button>
    </Frame>
  );
}

function RunTool({
  messageId,
  tool,
  call,
}: {
  messageId: string;
  tool: ToolState;
  call: Extract<ToolCall, { name: "runScenario" }>;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const create = useCreateRun();
  const update = useChat((s) => s.update);
  const [asking, setAsking] = useState(false);
  const confirmed = useRef(false);
  const args = call.args;
  const setStatus = (status: ToolState["status"]) =>
    update(messageId, (m) => ({
      ...m,
      tools: m.tools.map((x) => (x.id === tool.id ? { ...x, status } : x)),
    }));
  const summary = `${f.networkName(args.network)} · ${f.demandName(args.demand)} · ${args.events.map(f.scenarioName).join(", ")} · s${args.seed} — ${f.methodName(args.left)} / ${f.methodName(args.right)}`;

  return (
    <Frame title={t("assistantChat.proposed")}>
      <p className="mb-2 text-xs text-text-2">{summary}</p>
      {tool.status === "proposed" && MUTATING_TOOLS.has(call.name) ? (
        <Button size="sm" variant="primary" onClick={() => setAsking(true)}>
          <Play aria-hidden="true" className="rtl:-scale-x-100" />
          {t("assistantChat.confirmRun")}
        </Button>
      ) : tool.status === "cancelled" ? (
        <p className="text-xs text-muted">{t("assistantChat.cancelled")}</p>
      ) : (
        <p role="status" className={create.isError ? "text-xs text-jam" : "text-xs text-flow"}>
          {create.isError ? create.error.message : t("assistantChat.launched")}
        </p>
      )}
      <ConfirmDialog
        open={asking}
        onOpenChange={(open) => {
          if (!open && !confirmed.current) setStatus("cancelled");
          setAsking(open);
        }}
        title={t("scenarioPage.confirmTitle")}
        description={t("scenarioPage.confirmText")}
        confirmLabel={t("scenarioPage.confirm")}
        cancelLabel={t("scenarioPage.cancel")}
        onConfirm={() => {
          confirmed.current = true;
          setStatus("confirmed");
          create.mutate(args);
        }}
      >
        <p className="rounded-md bg-surface-2 p-2 text-xs text-text-2">{summary}</p>
      </ConfirmDialog>
    </Frame>
  );
}
