import { useTranslation } from "react-i18next";

import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";

/** What the shapes and colours of the map mean (colour is never the only cue: see labels). */
export function Legend() {
  const { t } = useTranslation();
  const vehicles = [
    { label: t("replay.flowing"), className: "bg-flow" },
    { label: t("replay.slow"), className: "bg-dense" },
    { label: t("replay.stopped"), className: "bg-jam" },
  ];
  const kinds = [
    { label: t("replay.bus"), style: { background: "#f5c451", width: 22 } },
    {
      label: t("replay.emergencyVehicle"),
      style: { background: "var(--emergency)", outline: "1px solid #fff", width: 14 },
    },
    { label: t("replay.incidentVehicle"), style: { background: "#d946ef", width: 10 } },
  ];
  const signals = [
    { label: t("replay.signalGreen"), color: "#22c55e" },
    { label: t("replay.signalYellow"), color: "#facc15" },
    { label: t("replay.signalRed"), color: "#ef4444" },
  ];
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("replay.legend")}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 text-xs text-text-2">
        <p className="text-[11px] text-muted">{t("replay.colorBy")}</p>
        <ul className="flex flex-col gap-1.5">
          {vehicles.map((v) => (
            <li key={v.label} className="flex items-center gap-2">
              <span aria-hidden="true" className={`h-2 w-3.5 rounded-sm ${v.className}`} />
              {t("replay.car")} · {v.label}
            </li>
          ))}
          {kinds.map((k) => (
            <li key={k.label} className="flex items-center gap-2">
              <span aria-hidden="true" className="h-2 rounded-sm" style={k.style} />
              {k.label}
            </li>
          ))}
          <li className="flex items-center gap-2">
            <span aria-hidden="true" className="size-2 rounded-full bg-[#93c5fd]" />
            {t("replay.pedestrian")}
          </li>
        </ul>
        <ul className="flex flex-col gap-1.5">
          {signals.map((s) => (
            <li key={s.label} className="flex items-center gap-2">
              <span
                aria-hidden="true"
                className="size-2.5 rounded-full"
                style={{ background: s.color }}
              />
              {s.label}
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
