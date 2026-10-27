import { Play, Square } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { useCatalog, type CatalogNetwork } from "@/shared/api/backend";
import { usePolicy, useUpdatePolicy } from "@/shared/api/policy";
import { simulationScenario, useStartSimulation } from "@/shared/api/simulation";
import { useFormat } from "@/shared/domain/format";
import { cn } from "@/shared/lib/cn";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { SelectControl } from "@/shared/ui/select";

type Notice = { text: string; error: boolean };

/** Launches the backend live run with the selected active policy: the checkpoint the
 *  Entraînement tab trained, Max-Pressure, or the LLM controller (it degrades to MP
 *  without a key, and the catalog says so). */
export default function LiveControl() {
  const { t } = useTranslation();
  const f = useFormat();
  const catalog = useCatalog();
  const policy = usePolicy();
  const updatePolicy = useUpdatePolicy();
  const startSimulation = useStartSimulation();
  const [launching, setLaunching] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  const networks = (catalog.data?.networks ?? []).filter((n) => n.runnable);
  const network = networks.find((n) => n.network === policy.data?.network) ?? networks[0] ?? null;
  const methods = Object.entries(network?.controllers ?? {}).filter(
    ([, c]) => c.available,
  );
  const active = policy.data?.method ?? null;

  const launch = async (networkEntry: CatalogNetwork, method: string) => {
    setLaunching(true);
    setNotice(null);
    try {
      if (policy.data?.method !== method || policy.data?.network !== networkEntry.network) {
        await updatePolicy.mutateAsync({ method, network: networkEntry.network });
      }
      const state = await startSimulation.mutateAsync({
        network: networkEntry.network,
      });
      document.dispatchEvent(
        new CustomEvent("sumo:launch-scenario", {
          detail: { scenario: simulationScenario(networkEntry.network), state },
        }),
      );
      setNotice({
        text: t("pages.liveMap.live.launchNotice", {
          method: f.methodName(method),
          network: f.networkName(networkEntry.network),
        }),
        error: false,
      });
    } catch (error) {
      setNotice({
        text: error instanceof Error ? error.message : String(error),
        error: true,
      });
    } finally {
      setLaunching(false);
    }
  };

  const stop = async () => {
    try {
      await fetch("/api/simulation/stop", { method: "POST" });
      setNotice({ text: t("pages.liveMap.live.stopNotice"), error: false });
    } catch {
      setNotice({ text: t("pages.liveMap.live.stopFailed"), error: true });
    }
  };

  if (!catalog.data || !policy.data) return null;
  return (
    <CardShell>
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-xs text-text-2">{t("pages.liveMap.live.title")}</span>
        <SelectControl
          ariaLabel={t("filters.network")}
          className="max-w-44 text-xs"
          value={network?.network ?? ""}
          options={networks.map((n) => ({ value: n.network, label: n.title }))}
          onChange={(next) =>
            updatePolicy.mutate({
              method: active && network?.controllers[active]?.available ? active : "mp",
              network: next,
            })
          }
        />
        {methods.slice(0, 6).map(([method, c]) => (
          <button
            key={method}
            type="button"
            disabled={launching}
            onClick={() => network && launch(network, method)}
            className={cn(
              "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs",
              active === method && network && policy.data.network === network.network
                ? "border-flow bg-flow/10 text-flow"
                : "border-border text-text-2 hover:bg-surface-2",
            )}
            title={c.reason ?? undefined}
          >
            {c.label}
            {c.reason ? " ⚠" : ""}
          </button>
        ))}
        <Button
          size="sm"
          disabled={launching || !network}
          onClick={() => network && active && launch(network, active)}
        >
          <Play aria-hidden="true" className="size-3" />
          {t("pages.liveMap.live.run")}
        </Button>
        <Button variant="outline" size="sm" onClick={stop}>
          <Square aria-hidden="true" className="size-3" />
          {t("pages.liveMap.live.stop")}
        </Button>
        {policy.data.degraded ? (
          <Badge tone="caution">{policy.data.reason}</Badge>
        ) : null}
      </div>
      {notice ? (
        <p className={cn("text-xs", notice.error ? "text-jam" : "text-muted")}>{notice.text}</p>
      ) : null}
    </CardShell>
  );
}

function CardShell({ children }: { children: React.ReactNode }) {
  return <div className="rounded-lg border border-border p-3 bg-surface">{children}</div>;
}
