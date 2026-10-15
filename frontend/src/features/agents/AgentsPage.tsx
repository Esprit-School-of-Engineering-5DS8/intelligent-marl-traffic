import { useTranslation } from "react-i18next";

import { ComingSoonPage } from "@/shared/ui/coming-soon";

export default function AgentsPage() {
  const { t } = useTranslation();
  return (
    <ComingSoonPage
      title={t("pages.agents.title")}
      description={t("pages.agents.description")}
      step={5}
    />
  );
}
