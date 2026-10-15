import { useTranslation } from "react-i18next";

import { ComingSoonPage } from "@/shared/ui/coming-soon";

export default function ScenariosPage() {
  const { t } = useTranslation();
  return (
    <ComingSoonPage
      title={t("pages.scenarios.title")}
      description={t("pages.scenarios.description")}
      step={5}
    />
  );
}
