import { Film, Locate, MonitorX } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ReplayControls, ReplayPicker } from "@/features/replay/ReplayControls";
import { ReplayStats } from "@/features/replay/ReplayStats";
import { usePlayback, usePlaybackClock } from "@/features/replay/store";
import { useMeta, useNetwork, useReplay } from "@/shared/api/queries";
import { QueryState } from "@/shared/components/QueryState";
import { useFormat } from "@/shared/domain/format";
import { methodColor } from "@/shared/domain/methods";
import { usePageTitle } from "@/shared/lib/use-page-title";
import type { NetworkGeometry, Replay } from "@/shared/schemas";
import { Button } from "@/shared/ui/button";
import { Card, CardContent } from "@/shared/ui/card";
import { EmptyState } from "@/shared/ui/empty-state";
import { PageHeader } from "@/shared/ui/page-header";

import { Scene3D } from "./Scene3D";

function hasWebGL(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

export default function Simulation3dPage() {
  const { t } = useTranslation();
  usePageTitle(t("pages.simulation3d.title"));
  usePlaybackClock();
  const meta = useMeta();
  const replayId = usePlayback((s) => s.replayId);
  const replay = useReplay(replayId);
  const network = useNetwork(replay.data?.network ?? null);
  const [webgl] = useState(hasWebGL);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        title={t("pages.simulation3d.title")}
        description={t("pages.simulation3d.description")}
      />
      {!webgl ? (
        <EmptyState icon={MonitorX} title={t("replay.webglMissing")} />
      ) : (
        <QueryState query={meta} height={60}>
          {(m) =>
            m.replays.length ? (
              <>
                <Card>
                  <CardContent className="flex flex-col gap-3 pt-4">
                    <ReplayPicker meta={m} />
                    {replay.data ? <ReplayControls replay={replay.data} /> : null}
                  </CardContent>
                </Card>
                <QueryState query={replay} height={560}>
                  {(r) => (
                    <QueryState query={network} height={560}>
                      {(net) => <View net={net} replay={r} />}
                    </QueryState>
                  )}
                </QueryState>
              </>
            ) : (
              <EmptyState icon={Film} title={t("replay.noReplay")}>
                {t("replay.noReplayText")}
              </EmptyState>
            )
          }
        </QueryState>
      )}
    </div>
  );
}

function View({ net, replay }: { net: NetworkGeometry; replay: Replay }) {
  const { t } = useTranslation();
  const f = useFormat();
  const split = usePlayback((s) => s.split);
  const side = usePlayback((s) => s.side);
  const [resetKey, setResetKey] = useState(0);
  const sides = split ? (["left", "right"] as const) : ([side] as const);
  return (
    <div className="flex flex-col gap-4">
      <div className="relative h-[600px] overflow-hidden rounded-lg border border-border">
        <Scene3D
          net={net}
          replay={replay}
          sides={sides}
          resetKey={resetKey}
          label={`${t("pages.simulation3d.title")} · ${sides.map((s) => f.methodName(replay.sides[s].method)).join(" / ")}`}
        />
        <div className="pointer-events-none absolute inset-x-3 top-3 flex justify-around gap-2">
          {sides.map((s) => (
            <span
              key={s}
              className="rounded-md bg-surface/90 px-2 py-1 text-xs font-semibold text-text shadow"
              style={{ borderInlineStart: `3px solid ${methodColor(replay.sides[s].method)}` }}
            >
              {f.methodName(replay.sides[s].method)}
            </span>
          ))}
        </div>
        <div className="pointer-events-none absolute inset-x-3 bottom-3 flex flex-wrap items-end justify-between gap-2">
          <p className="rounded-md bg-surface/90 px-2 py-1 text-[11px] text-text-2 shadow">
            {t("replay.controls3d")}
          </p>
          <Button
            className="pointer-events-auto"
            size="sm"
            variant="secondary"
            onClick={() => setResetKey((k) => k + 1)}
          >
            <Locate aria-hidden="true" />
            {t("replay.resetView")}
          </Button>
        </div>
      </div>
      <ReplayStats replay={replay} sides={[...sides]} />
    </div>
  );
}
