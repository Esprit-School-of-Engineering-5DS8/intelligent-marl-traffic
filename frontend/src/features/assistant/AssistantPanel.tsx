import { lazy, Suspense } from "react";
import { useTranslation } from "react-i18next";

import { useUi } from "@/app/ui-store";
import { Sheet } from "@/shared/ui/sheet";
import { Skeleton } from "@/shared/ui/skeleton";

// loaded when the panel first opens: keeps charts and markdown out of the first download
const Chat = lazy(() => import("./Chat").then((m) => ({ default: m.Chat })));

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
      <Suspense fallback={<Skeleton className="h-40" />}>
        <Chat compact />
      </Suspense>
    </Sheet>
  );
}
