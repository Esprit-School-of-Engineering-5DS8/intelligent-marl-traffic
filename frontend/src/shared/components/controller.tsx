import { useTranslation } from "react-i18next";

import { methodColorVar, methodLabel } from "@/shared/domain/methods";
import { cn } from "@/shared/lib/cn";

/** The swatch of a controller: its fixed colour; the oracle is a dashed neutral line. */
export function ControllerSwatch({ controller }: { controller: string }) {
  if (controller === "oracle")
    return (
      <span
        aria-hidden="true"
        className="inline-block w-3.5 shrink-0 border-t-2 border-dashed"
        style={{ borderColor: methodColorVar("oracle") }}
      />
    );
  return (
    <span
      aria-hidden="true"
      className="inline-block size-2.5 shrink-0 rounded-[3px]"
      style={{ background: methodColorVar(controller) }}
    />
  );
}

/** A controller's name with its swatch; the teammate's controller says whose work it is. */
export function ControllerName({
  controller,
  className,
  detail = false,
}: {
  controller: string;
  className?: string;
  /** add who designed it (TEAM-RULES: our teammate's work) */
  detail?: boolean;
}) {
  const { t } = useTranslation();
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap", className)}>
      <ControllerSwatch controller={controller} />
      <span>{methodLabel(controller)}</span>
      {detail && controller === "team_rules" ? (
        <span className="text-muted">({t("ui.teammate")})</span>
      ) : null}
    </span>
  );
}
