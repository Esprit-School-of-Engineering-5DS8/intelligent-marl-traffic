import { useTranslation } from "react-i18next";

import { ComingSoonPage } from "@/shared/ui/coming-soon";

export default function PedestriansPage() {
  const { t } = useTranslation();
  return (
    <ComingSoonPage
      title={t("pages.pedestrians.title")}
      description={t("pages.pedestrians.description")}
      step={5}
    />
  );
}
