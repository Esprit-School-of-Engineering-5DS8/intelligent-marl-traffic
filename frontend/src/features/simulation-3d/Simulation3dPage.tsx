import { useTranslation } from "react-i18next";

import { ComingSoonPage } from "@/shared/ui/coming-soon";

export default function Simulation3dPage() {
  const { t } = useTranslation();
  return (
    <ComingSoonPage
      title={t("pages.simulation3d.title")}
      description={t("pages.simulation3d.description")}
      step={4}
    />
  );
}
