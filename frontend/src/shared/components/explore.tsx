import { ArrowRight } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { firstWith } from "@/features/replay/catalog";
import { usePlayback } from "@/features/replay/store";
import { useMeta } from "@/shared/api/queries";
import { useTx } from "@/shared/domain/format";
import { Button } from "@/shared/ui/button";

import { ExploreHero } from "./page";

export type ExplorePage =
  | "overview"
  | "analytics"
  | "liveMap"
  | "simulation3d"
  | "scenarios"
  | "emergency"
  | "pedestrians"
  | "agents";

export interface ExploreLink {
  to: string;
  label: string;
  /** Opens the replay view on the first replay with this event (our candidate's first). */
  event?: string;
}

/**
 * The header of an exploration page: its title, what it shows, which data it reads (the
 * first study, or replays of simulations) and the three things to know to read it.
 */
export function ExploreHeader({
  page,
  scope,
  links,
}: {
  page: ExplorePage;
  scope: "study" | "replay";
  links?: ExploreLink[];
}) {
  const { t } = useTranslation();
  const tx = useTx();
  const replays = useMeta().data?.replays ?? [];
  const setReplay = usePlayback((s) => s.setReplay);
  const shown =
    links ??
    (scope === "study"
      ? [{ to: "/final-controller", label: t("explore.toFinal") }]
      : [{ to: "/scenarios", label: t("explore.toScenarios") }]);
  return (
    <ExploreHero
      title={tx(`pages.${page}.title`)}
      answer={tx(`explore.${page}.answer`)}
      scope={t(scope === "study" ? "explore.scopeStudy" : "explore.scopeReplay")}
      tips={(["t1", "t2", "t3"] as const).map((k) => tx(`explore.${page}.tips.${k}`))}
      actions={shown.map((l, i) => (
        <Button key={l.to} asChild size="sm" variant={i === 0 ? "secondary" : "outline"}>
          <Link
            to={l.to}
            onClick={() => {
              const replay = l.event ? firstWith(replays, l.event) : undefined;
              if (replay) setReplay(replay.id);
            }}
          >
            {l.label}
            <ArrowRight aria-hidden="true" className="rtl:-scale-x-100" />
          </Link>
        </Button>
      ))}
    />
  );
}
