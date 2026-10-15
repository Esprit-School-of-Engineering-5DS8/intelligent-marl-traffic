import { useTranslation } from "react-i18next";

import { useUi } from "@/app/ui-store";
import { Sheet } from "@/shared/ui/sheet";

import { Chat } from "./Chat";

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
      <Chat compact />
    </Sheet>
  );
}
