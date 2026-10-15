import { Bot } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useUi } from "@/app/ui-store";
import { Sheet } from "@/shared/ui/sheet";

/** Side panel reachable from every page (button in the top bar or Ctrl+K). */
export function AssistantPanel() {
  const { t } = useTranslation();
  const open = useUi((s) => s.assistantOpen);
  const setOpen = useUi((s) => s.setAssistantOpen);

  return (
    <Sheet
      open={open}
      onOpenChange={setOpen}
      title={t("assistant.title")}
      description={t("assistant.description")}
      closeLabel={t("common.close")}
    >
      <div className="flex flex-col items-center gap-3 py-10 text-center">
        <Bot aria-hidden="true" className="size-8 text-muted" />
        <p className="max-w-xs text-sm text-text-2">{t("assistant.placeholder")}</p>
      </div>
    </Sheet>
  );
}
