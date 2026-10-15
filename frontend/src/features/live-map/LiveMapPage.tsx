import { useTranslation } from "react-i18next";

import { ComingSoonPage } from "@/shared/ui/coming-soon";

export default function LiveMapPage() {
  const { t } = useTranslation();
  return (
    <ComingSoonPage
      title={t("pages.liveMap.title")}
      description={t("pages.liveMap.description")}
      step={4}
    />
  );
}
