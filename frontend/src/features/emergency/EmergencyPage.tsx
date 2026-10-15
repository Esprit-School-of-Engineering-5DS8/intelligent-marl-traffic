import { useTranslation } from "react-i18next";

import { ComingSoonPage } from "@/shared/ui/coming-soon";

export default function EmergencyPage() {
  const { t } = useTranslation();
  return (
    <ComingSoonPage
      title={t("pages.emergency.title")}
      description={t("pages.emergency.description")}
      step={5}
    />
  );
}
