import { Crosshair, Film } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { ReplayControls, ReplayPicker } from "@/features/replay/ReplayControls";
import { ReplayStats } from "@/features/replay/ReplayStats";
import { sceneAt, type Side } from "@/features/replay/scene";
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

import { Events } from "./Events";
import { JunctionPanel } from "./JunctionPanel";
import { Legend } from "./Legend";
import { NetworkMap } from "./NetworkMap";
import { fitView, sameView, type MapViewState } from "./view";

export default function LiveMapPage() {
  const { t } = useTranslation();
  usePageTitle(t("pages.liveMap.title"));
  usePlaybackClock();
  const meta = useMeta();
  const replayId = usePlayback((s) => s.replayId);
  const replay = useReplay(replayId);
  const network = useNetwork(replay.data?.network ?? null);

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("pages.liveMap.title")} description={t("pages.liveMap.description")} />
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
              <QueryState query={replay} height={520}>
                {(r) => (
                  <QueryState query={network} height={520}>
                    {(net) => <MapArea net={net} replay={r} />}
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
    </div>
  );
}

function MapArea({ net, replay }: { net: NetworkGeometry; replay: Replay }) {
  const { t } = useTranslation();
  const f = useFormat();
  const split = usePlayback((s) => s.split);
  const side = usePlayback((s) => s.side);
  const box = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<MapViewState | null>(null);
  const [follow, setFollow] = useState(false);
  const hasEv = replay.sides.left.events.some((e) => e.type === "emergency");

  // fit the network to the map box when the network or the layout changes
  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const width = split ? el.clientWidth / 2 : el.clientWidth;
    setView(fitView(net, Math.max(200, width), Math.max(200, el.clientHeight)));
  }, [net, split]);

  const sides = split ? (["left", "right"] as const) : ([side] as const);

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_280px]">
      <div className="flex min-w-0 flex-col gap-4">
        <div
          ref={box}
          className="grid h-[560px] overflow-hidden rounded-lg border border-border bg-bg"
          style={{ gridTemplateColumns: `repeat(${sides.length}, minmax(0, 1fr))` }}
        >
          {view
            ? sides.map((s) => {
                const method = replay.sides[s].method;
                return (
                  <div key={s} className="relative min-w-0 border-border not-last:border-e">
                    <NetworkMap
                      net={net}
                      replay={replay}
                      side={s}
                      viewState={view}
                      onViewState={setView}
                      label={`${f.methodName(method)} · ${f.networkName(replay.network)}`}
                    />
                    <span
                      className="pointer-events-none absolute start-3 top-3 rounded-md bg-surface/90 px-2 py-1 text-xs font-semibold text-text shadow"
                      style={{ borderInlineStart: `3px solid ${methodColor(method)}` }}
                    >
                      {f.methodName(method)}
                    </span>
                  </div>
                );
              })
            : null}
        </div>
        {hasEv ? (
          <div className="flex items-center gap-2">
            <Button
              variant={follow ? "primary" : "outline"}
              size="sm"
              aria-pressed={follow}
              onClick={() => setFollow((v) => !v)}
            >
              <Crosshair aria-hidden="true" />
              {t("replay.followEv")}
            </Button>
            {follow ? <FollowEmergency replay={replay} side={sides[0]} onView={setView} /> : null}
          </div>
        ) : null}
        <ReplayStats replay={replay} sides={[...sides]} />
      </div>
      <aside aria-label={t("replay.legend")} className="flex flex-col gap-4">
        <JunctionPanel net={net} replay={replay} sides={[...sides]} />
        <Events replay={replay} />
        <Legend />
      </aside>
    </div>
  );
}

/** Keeps the camera on the emergency vehicle currently in the network. */
function FollowEmergency({
  replay,
  side,
  onView,
}: {
  replay: Replay;
  side: Side;
  onView: (update: (v: MapViewState | null) => MapViewState | null) => void;
}) {
  const time = usePlayback((s) => s.time);
  useEffect(() => {
    const ev = sceneAt(replay, side, time).vehicles.find((v) => v.kind === "emergency");
    if (!ev) return;
    onView((v) => {
      const next: MapViewState = { target: [ev.x, ev.y, 0], zoom: Math.max(v?.zoom ?? 2, 2) };
      return sameView(next, v) ? v : next; // unchanged camera: no re-render
    });
  }, [replay, side, time, onView]);
  return null;
}
