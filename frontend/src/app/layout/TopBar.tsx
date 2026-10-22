import { Bot, Database, Moon, Radio, Sun } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useResolvedTheme } from "@/app/theme";
import { useUi } from "@/app/ui-store";
import { useSettings, type Language } from "@/features/settings/store";
import { useConnection, type ConnectionStatus } from "@/shared/api/connection";
import { LANGUAGES } from "@/shared/i18n";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Kbd } from "@/shared/ui/kbd";

const STATUS_TONE: Record<ConnectionStatus, "neutral" | "dense" | "flow"> = {
  offline: "neutral",
  connecting: "dense",
  online: "flow",
};

export function TopBar() {
  const { t } = useTranslation();
  const dataSource = useSettings((s) => s.dataSource);
  const language = useSettings((s) => s.language);
  const update = useSettings((s) => s.update);
  const theme = useResolvedTheme();
  const status = useConnection((s) => s.status);
  const openAssistant = useUi((s) => s.setAssistantOpen);

  return (
    <header className="flex h-14 shrink-0 items-center gap-3 border-b border-border bg-surface px-4">
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
        <Badge tone="accent" title={t("topbar.dataSource")}>
          <Database aria-hidden="true" />
          <span className="sr-only">{t("topbar.dataSource")} : </span>
          {dataSource === "mock" ? t("topbar.sourceMock") : t("topbar.sourceLive")}
        </Badge>
        {/* polite live region: announces stream changes without stealing focus */}
        <Badge tone={STATUS_TONE[status]} role="status" aria-live="polite">
          <Radio aria-hidden="true" />
          {t(`topbar.status.${status}`)}
        </Badge>
      </div>

      <label htmlFor="topbar-language" className="sr-only">
        {t("topbar.language")}
      </label>
      <select
        id="topbar-language"
        value={language}
        onChange={(e) => update({ language: e.target.value as Language })}
        className="h-9 rounded-md border border-border bg-surface-2 px-2 text-sm text-text"
      >
        {Object.entries(LANGUAGES).map(([code, { label }]) => (
          <option key={code} value={code} lang={code}>
            {label}
          </option>
        ))}
      </select>

      <Button
        variant="ghost"
        size="icon"
        onClick={() => update({ theme: theme === "dark" ? "light" : "dark" })}
        aria-label={theme === "dark" ? t("topbar.toLight") : t("topbar.toDark")}
        title={theme === "dark" ? t("topbar.toLight") : t("topbar.toDark")}
      >
        {theme === "dark" ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
      </Button>

      <Button
        variant="secondary"
        onClick={() => openAssistant(true)}
        title={t("topbar.openAssistant")}
        aria-keyshortcuts="Control+K"
      >
        <Bot aria-hidden="true" />
        <span className="sr-only sm:not-sr-only">{t("topbar.assistant")}</span>
        <Kbd aria-hidden="true" className="hidden md:inline">
          Ctrl K
        </Kbd>
      </Button>
    </header>
  );
}
