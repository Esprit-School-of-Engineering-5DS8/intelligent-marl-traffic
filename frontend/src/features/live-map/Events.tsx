import { Siren } from "lucide-react";
import { useTranslation } from "react-i18next";

import { usePlayback } from "@/features/replay/store";
import { useFormat } from "@/shared/domain/format";
import type { Replay } from "@/shared/schemas";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";

/** Emergency vehicles entering the network during the window; a click jumps there. */
export function Events({ replay }: { replay: Replay }) {
  const { t } = useTranslation();
  const f = useFormat();
  const seek = usePlayback((s) => s.seek);
  const events = replay.sides.left.events;
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("replay.events")}</CardTitle>
      </CardHeader>
      <CardContent>
        {events.length ? (
          <ul className="flex flex-col gap-1">
            {events.map((e) => (
              <li key={`${e.id}-${e.t}`}>
                <button
                  type="button"
                  onClick={() => seek(Math.max(0, e.t - 4))}
                  className="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-start text-xs text-text-2 hover:bg-surface-2 hover:text-text"
                  aria-label={`${t("replay.evAppears", { id: e.id })} · ${t("replay.jumpTo", { time: f.clock(e.t) })}`}
                >
                  <Siren aria-hidden="true" className="size-3.5 text-emergency" />
                  <span className="tabular text-muted">{f.clock(e.t)}</span>
                  {t("replay.evAppears", { id: e.id })}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-xs text-muted">{t("replay.noEvents")}</p>
        )}
      </CardContent>
    </Card>
  );
}
