import { useTranslation } from "react-i18next";

import { ComingSoonPage } from "@/shared/ui/coming-soon";

export default function AnalyticsPage() {
  const { t } = useTranslation();
  return (
    <ComingSoonPage
      title={t("pages.analytics.title")}
      description={t("pages.analytics.description")}
      step={5}
    />
  );
}
