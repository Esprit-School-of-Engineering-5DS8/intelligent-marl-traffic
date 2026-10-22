import { MousePointerClick } from "lucide-react";
import { useTranslation } from "react-i18next";

import { sceneAt, signalColor, type Side } from "@/features/replay/scene";
import { usePlayback } from "@/features/replay/store";
import { useFormat } from "@/shared/domain/format";
import type { NetworkGeometry, Replay } from "@/shared/schemas";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";

const DOT: Record<ReturnType<typeof signalColor>, string> = {
  green: "#22c55e",
  yellow: "#facc15",
  red: "#ef4444",
  off: "#64748b",
};
const RADIUS = 60;

/** State of the selected junction's signal and the traffic around it, per controller. */
export function JunctionPanel({
  net,
  replay,
  sides,
}: {
  net: NetworkGeometry;
  replay: Replay;
  sides: Side[];
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const selected = usePlayback((s) => s.selectedJunction);
  const time = usePlayback((s) => Math.floor(s.time));
  const junction = net.junctions.find((j) => j.id === selected);
  const slot = selected ? replay.signals.indexOf(selected) : -1;

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {junction ? t("replay.junction", { id: junction.id }) : t("replay.junctionState")}
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3" aria-live="polite">
        {!junction || slot === -1 ? (
          <p className="flex items-start gap-2 text-xs text-text-2">
            <MousePointerClick aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-muted" />
            {t("replay.clickJunction")}
          </p>
        ) : (
          sides.map((side) => {
            const scene = sceneAt(replay, side, time);
            const state = scene.signals[slot] ?? "";
            const [jx, jy] = junction.position;
            const near = scene.vehicles.filter((v) => Math.hypot(v.x - jx, v.y - jy) < RADIUS);
            const halted = near.filter((v) => v.speed < 0.1).length;
            const greens = [...state].filter((c) => signalColor(c) === "green").length;
            return (
              <section key={side} className="flex flex-col gap-1.5">
                <h3 className="text-xs font-semibold text-text">
                  {f.methodName(replay.sides[side].method)}
                </h3>
                <div
                  className="flex flex-wrap gap-0.5"
                  role="img"
                  aria-label={`${t("replay.junctionState")}: ${greens}/${state.length} ${t("replay.signalGreen").toLowerCase()}`}
                >
                  {[...state].map((c, i) => (
                    <span
                      key={i}
                      className="h-3 w-2 rounded-[2px]"
                      style={{ background: DOT[signalColor(c)] }}
                    />
                  ))}
                </div>
                <p className="tabular text-xs text-text-2">
                  {t("replay.nearby")} : <b className="text-text">{near.length}</b> ·{" "}
                  {t("replay.nearbyHalted")}{" "}
                  <b className={halted > 8 ? "text-jam" : "text-text"}>{halted}</b>
                </p>
              </section>
            );
          })
        )}
      </CardContent>
    </Card>
  );
}
