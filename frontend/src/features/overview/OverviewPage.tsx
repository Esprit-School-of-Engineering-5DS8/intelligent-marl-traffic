import { useTranslation } from "react-i18next";

import { ComingSoonPage } from "@/shared/ui/coming-soon";

export default function OverviewPage() {
  const { t } = useTranslation();
  return (
    <ComingSoonPage
      title={t("pages.overview.title")}
      description={t("pages.overview.description")}
      step={3}
    />
  );
}
