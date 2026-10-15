import { Compass } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { usePageTitle } from "@/shared/lib/use-page-title";
import { Button } from "@/shared/ui/button";
import { EmptyState } from "@/shared/ui/empty-state";

export function NotFound() {
  const { t } = useTranslation();
  usePageTitle(t("common.notFoundTitle"));
  return (
    <EmptyState
      icon={Compass}
      title={t("common.notFoundTitle")}
      action={
        <Button asChild variant="primary">
          <Link to="/">{t("common.backHome")}</Link>
        </Button>
      }
    >
      {t("common.notFoundText")}
    </EmptyState>
  );
}
