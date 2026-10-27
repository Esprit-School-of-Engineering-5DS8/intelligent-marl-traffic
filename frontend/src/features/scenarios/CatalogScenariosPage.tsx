import { CircleAlert, GraduationCap, Play, Route, Signal, Timer, Waypoints } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { useTrainingDraft } from "@/features/training/store";
import { useCatalog, type CatalogNetwork } from "@/shared/api/backend";
import { usePolicy, useUpdatePolicy } from "@/shared/api/policy";
import { simulationScenario, useStartSimulation } from "@/shared/api/simulation";
import { QueryState } from "@/shared/components/QueryState";
import { useFormat } from "@/shared/domain/format";
import { isPrimaryMethod, methodColor, sortMethods } from "@/shared/domain/methods";
import { cn } from "@/shared/lib/cn";
import { usePageTitle } from "@/shared/lib/use-page-title";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";
import { PageHeader } from "@/shared/ui/page-header";

type Notice = { text: string; error: boolean };

export default function CatalogScenariosPage() {
  const { t } = useTranslation();
  usePageTitle(t("pages.scenarios.title"));
  const f = useFormat();
  const catalog = useCatalog();
  const policy = usePolicy();
  const updatePolicy = useUpdatePolicy();
  const startSimulation = useStartSimulation();
  const [launching, setLaunching] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);

  const select = (network: string, method: string) => {
    updatePolicy.mutate(
      { method, network },
      {
        onSuccess: (data) =>
          setNotice({
            text: `${data.label} · ${f.networkName(data.network)}`,
            error: false,
          }),
        onError: (error) =>
          setNotice({
            text: error instanceof Error ? error.message : String(error),
            error: true,
          }),
      },
    );
  };

  const launch = async (network: CatalogNetwork, method: string) => {
    setLaunching(network.network);
    setNotice(null);
    try {
      if (policy.data?.method !== method || policy.data?.network !== network.network) {
        await updatePolicy.mutateAsync({ method, network: network.network });
      }
      const state = await startSimulation.mutateAsync({ network: network.network });
      document.dispatchEvent(
        new CustomEvent("sumo:launch-scenario", {
          detail: { scenario: simulationScenario(network.network), state },
        }),
      );
      setNotice({
        text: t("catalog.launched", {
          method: f.methodName(method),
          network: f.networkName(network.network),
        }),
        error: false,
      });
    } catch (error) {
      setNotice({
        text:
          error instanceof Error && error.message
            ? `${t("catalog.launchError")} ${error.message}`
            : t("catalog.launchError"),
        error: true,
      });
    } finally {
      setLaunching(null);
    }
  };

  const trainHere = (network: CatalogNetwork, method: string | null) => {
    const trainable = Boolean(
      method &&
        catalog.data?.agentConfigs.some(
          (item) => item.name === method && item.trainable && !item.error,
        ),
    );
    useTrainingDraft.getState().setDraft({
      network: network.network,
      recipe: trainable ? method : null,
    });
    document.dispatchEvent(new CustomEvent("sumo:open-training"));
  };

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title={t("pages.scenarios.title")}
        description={t("catalog.description")}
        actions={
          catalog.data ? (
            <div className="flex flex-wrap gap-2">
              <Badge tone="neutral">
                {t("catalog.networks", { count: catalog.data.networks.length })}
              </Badge>
              <Badge tone="accent">
                {t("catalog.recipes", { count: catalog.data.agentConfigs.length })}
              </Badge>
            </div>
          ) : null
        }
      />

      <QueryState query={catalog} height={320}>
        {(data) => (
          <>
            <div className="grid gap-4 xl:grid-cols-2">
              {data.networks.map((network) => (
                <NetworkCard
                  key={network.network}
                  network={network}
                  activeMethod={
                    policy.data?.network === network.network ? policy.data.method : null
                  }
                  busy={updatePolicy.isPending || launching !== null}
                  launching={launching === network.network}
                  onSelect={(method) => select(network.network, method)}
                  onLaunch={(method) => void launch(network, method)}
                  onTrain={(method) => trainHere(network, method)}
                />
              ))}
            </div>
            <p
              role="status"
              aria-live="polite"
              className={cn("min-h-5 text-xs", notice?.error ? "text-jam" : "text-muted")}
            >
              {notice?.text}
            </p>
          </>
        )}
      </QueryState>
    </div>
  );
}

function NetworkCard({
  network,
  activeMethod,
  busy,
  launching,
  onSelect,
  onLaunch,
  onTrain,
}: {
  network: CatalogNetwork;
  activeMethod: string | null;
  busy: boolean;
  launching: boolean;
  onSelect: (method: string) => void;
  onLaunch: (method: string) => void;
  onTrain: (method: string | null) => void;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const [showAll, setShowAll] = useState(false);
  const controllers = sortMethods(Object.keys(network.controllers));
  const primary = controllers.filter(isPrimaryMethod);
  const extra = controllers.filter((method) => !isPrimaryMethod(method));
  const visible = showAll ? controllers : primary;
  const learned = Object.values(network.controllers).filter((c) => c.learned);
  const trained = learned.filter((c) => c.trained).length;
  const runnable = (method: string) => network.controllers[method]?.available;
  const preferred =
    ["mp", "ft", "act"].find(runnable) ??
    controllers.find((method) => !network.controllers[method].learned && runnable(method)) ??
    controllers.find(runnable) ??
    null;
  const selected = activeMethod ?? preferred;
  const canLaunch = Boolean(network.runnable && selected && network.controllers[selected]?.available);

  return (
    <Card className="flex h-full flex-col">
      <CardHeader className="gap-2">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <CardTitle className="text-base">{f.networkName(network.network)}</CardTitle>
          <Badge tone={network.runnable ? "flow" : "jam"}>
            {t(network.runnable ? "catalog.runnable" : "catalog.disabled")}
          </Badge>
        </div>
        <CardDescription>{network.description}</CardDescription>
      </CardHeader>

      <CardContent className="flex flex-1 flex-col gap-4">
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Fact
            icon={<Signal aria-hidden="true" />}
            label={t("catalog.signals")}
            value={f.number(network.tlsCount)}
          />
          <Fact
            icon={<Waypoints aria-hidden="true" />}
            label={t("catalog.edges")}
            value={f.number(network.edgeCount)}
          />
          <Fact
            icon={<Route aria-hidden="true" />}
            label={t("catalog.junctions")}
            value={f.number(network.junctionCount)}
          />
          <Fact
            icon={<Timer aria-hidden="true" />}
            label={t("catalog.wallTime")}
            value={`${f.number(network.measuredWallTimeS)} s`}
          />
        </dl>

        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-between gap-2">
            <h3 className="text-xs font-semibold text-text">{t("catalog.controllers")}</h3>
            <span className="text-[11px] text-muted">
              {t("catalog.checkpoints", { trained, total: learned.length })}
            </span>
          </div>
          <div className="flex flex-wrap gap-1.5">
            {visible.map((method) => {
              const controller = network.controllers[method];
              const active = activeMethod === method;
              return (
                <button
                  key={method}
                  type="button"
                  disabled={!controller.available || busy}
                  aria-pressed={active}
                  title={controller.reason ?? controller.label}
                  onClick={() => onSelect(method)}
                  className={cn(
                    "inline-flex items-center gap-1.5 border px-2 py-1 text-[11px] transition-colors",
                    active
                      ? "border-accent bg-accent-soft text-accent"
                      : "border-border bg-surface/70 text-text-2 hover:border-border-strong hover:text-text",
                    !controller.available && "cursor-not-allowed opacity-45",
                  )}
                >
                  <span
                    aria-hidden="true"
                    className="size-1.5 rounded-full"
                    style={{ background: methodColor(method) }}
                  />
                  <span className="font-medium">{f.methodName(method)}</span>
                  {controller.learned ? (
                    <span
                      className={cn(
                        "px-1 py-px text-[9px] font-semibold uppercase tracking-wide",
                        controller.trained
                          ? "bg-flow-soft text-flow"
                          : "bg-jam-soft text-jam",
                      )}
                    >
                      {t(controller.trained ? "catalog.trained" : "catalog.missing")}
                    </span>
                  ) : null}
                </button>
              );
            })}
            {extra.length > 0 ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                aria-expanded={showAll}
                onClick={() => setShowAll((value) => !value)}
                className="h-6 px-1.5 text-[10px]"
              >
                {showAll ? t("catalog.less") : t("catalog.more", { count: extra.length })}
              </Button>
            ) : null}
          </div>
        </div>

        {!network.runnable && network.disabledReason ? (
          <p className="flex items-start gap-1.5 text-[11px] text-jam">
            <CircleAlert aria-hidden="true" className="mt-px size-3.5 shrink-0" />
            {network.disabledReason}
          </p>
        ) : null}

        <div className="mt-auto flex flex-wrap items-center justify-between gap-2 border-t border-border pt-3">
          <span className="min-w-0 text-[11px] text-muted">
            {t("catalog.launchHint")}
            {selected ? ` · ${f.methodName(selected)}` : ""}
          </span>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={!network.runnable || busy}
              title={t("catalog.trainHint")}
              onClick={() => onTrain(selected)}
            >
              <GraduationCap aria-hidden="true" />
              {t("catalog.train")}
            </Button>
            <Button
              type="button"
              variant="primary"
              size="sm"
              disabled={!canLaunch || busy}
              title={selected ? f.methodName(selected) : undefined}
              onClick={() => {
                if (selected) onLaunch(selected);
              }}
            >
              <Play aria-hidden="true" />
              {launching ? t("catalog.launching") : t("catalog.launch")}
            </Button>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function Fact({
  icon,
  label,
  value,
}: {
  icon: ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="flex items-center gap-2 border border-border bg-surface-2/60 px-2 py-1.5">
      <span className="text-muted [&_svg]:size-3.5">{icon}</span>
      <div className="min-w-0">
        <dt className="truncate text-[10px] uppercase tracking-wide text-muted">{label}</dt>
        <dd className="tabular text-xs font-semibold text-text">{value}</dd>
      </div>
    </div>
  );
}
