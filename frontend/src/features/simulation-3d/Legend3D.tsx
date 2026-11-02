import { useTranslation } from "react-i18next";

import { AMBULANCE_COLOR, BUS_COLOR, CAR_COLORS } from "./models";

const hex = (c: { getHexString: () => string }) => `#${c.getHexString()}`;

/** What each shape and colour of the 3D city means (the colour is never the only cue). */
export function Legend3D() {
  const { t } = useTranslation();
  return (
    <ul
      aria-label={t("scene3d.legend")}
      className="flex flex-wrap items-center gap-x-5 gap-y-2 rounded-lg border border-border bg-surface px-4 py-3 text-xs text-text-2"
    >
      <li className="flex items-center gap-2">
        <span aria-hidden="true" className="flex gap-0.5">
          {CAR_COLORS.slice(0, 5).map((c) => (
            <span key={hex(c)} className="h-2.5 w-4 rounded-[2px]" style={{ background: hex(c) }} />
          ))}
        </span>
        {t("scene3d.cars")}
      </li>
      <li className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="h-2.5 w-7 rounded-[2px]"
          style={{ background: hex(BUS_COLOR) }}
        />
        {t("scene3d.bus")}
      </li>
      <li className="flex items-center gap-2">
        <span
          aria-hidden="true"
          className="relative h-2.5 w-5 rounded-[2px] border border-border-strong"
          style={{ background: hex(AMBULANCE_COLOR) }}
        >
          <span className="absolute inset-x-0 top-[3px] h-[3px] bg-[#1d4ed8]" />
        </span>
        {t("scene3d.ambulance")}
      </li>
      <li className="flex items-center gap-2">
        <span aria-hidden="true" className="h-2.5 w-1.5 rounded-[2px] bg-[#ff2a1a]" />
        {t("scene3d.brakes")}
      </li>
      <li className="flex items-center gap-2">
        <span aria-hidden="true" className="flex flex-col gap-0.5 rounded-[3px] bg-[#14181e] p-0.5">
          <span className="size-1.5 rounded-full bg-[#ff3b30]" />
          <span className="size-1.5 rounded-full bg-[#3a3110]" />
          <span className="size-1.5 rounded-full bg-[#10301c]" />
        </span>
        {t("scene3d.signals")}
      </li>
      <li className="flex items-center gap-2">
        <span aria-hidden="true" className="size-2.5 rounded-full bg-[#3b5b92]" />
        {t("scene3d.pedestrians")}
      </li>
    </ul>
  );
}
