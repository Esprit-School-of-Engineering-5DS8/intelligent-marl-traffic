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
import { cn } from "@/shared/lib/cn";
import { usePageTitle } from "@/shared/lib/use-page-title";
import type { NetworkGeometry, Replay } from "@/shared/schemas";
import { Button } from "@/shared/ui/button";
import { Card, CardContent } from "@/shared/ui/card";
import { EmptyState } from "@/shared/ui/empty-state";
import { PageHeader } from "@/shared/ui/page-header";

import { Scene3D } from "./Scene3D";
import { ALL_VISIBLE, type Visibility } from "./visibility";

/** Only the 2x2 and 3x3 grids are supported here: their geometry is small enough to read
 *  side by side. The SF mission grids are the 2x2/3x3 networks the trained policies were
 *  benchmarked on, so their saved models can be played here too. */
const SUPPORTED = /^(grid|sf_mission)(2x2|3x3)__/;
const RECORD_HINT =
  "python scripts/record_replay.py --net sf_mission_2x2 --scenarios emergency pedestrians buses --demand peak --left model:generalist-shortpilot --right model:rl-shortpilot (then the same with --net sf_mission_3x3), and re-export the dashboard data.";

/** The road users drawn by the 3D scene, in the order of the legend. */
const LEGEND = [
  { key: "car", color: "#38c980" },
  { key: "bus", color: "#f5c451" },
  { key: "emergencyVehicle", color: "#ff4d6d" },
  { key: "incidentVehicle", color: "#d946ef" },
  { key: "pedestrian", color: "#93c5fd" },
] as const;

/** "emergencyVehicle" → "emergency": the legend keys are the translated labels, the
 *  visibility keys are the scene's road-user kinds. */
function kindOf(key: (typeof LEGEND)[number]["key"]): keyof Visibility {
  return key === "emergencyVehicle"
    ? "emergency"
    : key === "incidentVehicle"
      ? "incident"
      : key;
}

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
  // Shared by both panels: isolating a road-user type has to apply to the pair, otherwise
  // the two sides stop being comparable.
  const [visible, setVisible] = useState<Visibility>(ALL_VISIBLE);

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
          {(all) => {
            const m = { ...all, replays: all.replays.filter((r) => SUPPORTED.test(r.id)) };
            return m.replays.length ? (
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
                      {(net) => (
                        <View
                          net={net}
                          replay={r}
                          visible={visible}
                          onToggle={(kind) =>
                            setVisible((v) => ({ ...v, [kind]: !v[kind] }))
                          }
                        />
                      )}
                    </QueryState>
                  )}
                </QueryState>
              </>
            ) : (
              <EmptyState icon={Film} title={t("pages.simulation3d.empty")}>
                {RECORD_HINT}
              </EmptyState>
            );
          }}
        </QueryState>
      )}
    </div>
  );
}

function View({
  net,
  replay,
  visible,
  onToggle,
}: {
  net: NetworkGeometry;
  replay: Replay;
  visible: Visibility;
  onToggle: (kind: keyof Visibility) => void;
}) {
  const { t } = useTranslation();
  const split = usePlayback((s) => s.split);
  const side = usePlayback((s) => s.side);
  const sides = split ? (["left", "right"] as const) : ([side] as const);
  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 lg:grid-cols-2">
        {sides.map((s) => (
          <Panel key={s} net={net} replay={replay} side={s} visible={visible} />
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-text-2">
        <span className="me-1 font-medium">{t("replay.legend")}</span>
        {LEGEND.map(({ key, color }) => {
          const kind = kindOf(key);
          const on = visible[kind];
          return (
            <button
              key={key}
              type="button"
              aria-pressed={on}
              title={t(`replay.${key}`)}
              onClick={() => onToggle(kind)}
              className={cn(
                "flex items-center gap-1.5 rounded-full border px-2 py-0.5 transition-colors",
                on
                  ? "border-border-strong bg-surface text-text"
                  : "border-border bg-transparent text-muted opacity-55",
              )}
            >
              <span
                aria-hidden="true"
                className="size-2 rounded-full"
                style={{ background: on ? color : "transparent", border: `1px solid ${color}` }}
              />
              {t(`replay.${key}`)}
            </button>
          );
        })}
        <span className="ms-1 text-muted">{t("replay.controls3d")}</span>
      </div>
    </div>
  );
}

/** One controller in its own scene: separate canvas, camera and controls, so each side can be
 *  inspected on its own without moving the other. */
function Panel({
  net,
  replay,
  side,
  visible,
}: {
  net: NetworkGeometry;
  replay: Replay;
  side: "left" | "right";
  visible: Visibility;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const [resetKey, setResetKey] = useState(0);
  const method = replay.sides[side].method;
  // A side recorded from the model registry carries its name; a controller id is translated.
  const name = replay.sides[side].label ?? f.methodName(method);
  return (
    <Card className="overflow-hidden">
      <div
        className="flex items-center justify-between gap-2 border-b border-border px-3 py-2"
        style={{ borderTopColor: methodColor(method), borderTopWidth: 3 }}
      >
        <h3 className="flex items-center gap-2 text-sm font-semibold text-text">
          <span
            aria-hidden="true"
            className="size-2 rounded-full"
            style={{ background: methodColor(method) }}
          />
          {name}
        </h3>
        <Button size="sm" variant="ghost" onClick={() => setResetKey((k) => k + 1)}>
          <Locate aria-hidden="true" />
          {t("replay.resetView")}
        </Button>
      </div>
      <div className="h-[440px]">
        <Scene3D
          net={net}
          replay={replay}
          sides={[side]}
          resetKey={resetKey}
          visible={visible}
          label={`${t("pages.simulation3d.title")} · ${name}`}
        />
      </div>
      <div className="border-t border-border p-3">
        <ReplayStats replay={replay} sides={[side]} />
      </div>
    </Card>
  );
}
