import { useTranslation } from "react-i18next";

import { usePageTitle } from "@/shared/lib/use-page-title";
import { Card, CardContent } from "@/shared/ui/card";
import { PageHeader } from "@/shared/ui/page-header";

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
      <Card>
        <CardContent className="pt-4">
          <Chat />
        </CardContent>
      </Card>
    </div>
  );
}
