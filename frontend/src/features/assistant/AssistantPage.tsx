import { useTranslation } from "react-i18next";

import { usePageTitle } from "@/shared/lib/use-page-title";
import { PageHeader } from "@/shared/ui/page-header";
import { Panel } from "@/shared/ui/panel";

import { Chat } from "./Chat";

export default function AssistantPage() {
  const { t } = useTranslation();
  usePageTitle(t("pages.assistant.title"));
  return (
    <div className="flex max-w-4xl flex-col gap-4">
      <PageHeader
        title={t("pages.assistant.title")}
        description={t("pages.assistant.description")}
      />
      <Panel>
        <div className="p-4">
          <Chat />
        </div>
      </Panel>
    </div>
  );
}
