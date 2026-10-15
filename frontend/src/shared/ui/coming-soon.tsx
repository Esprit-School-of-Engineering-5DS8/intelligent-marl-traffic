import { Construction } from "lucide-react";
import { useTranslation } from "react-i18next";

import { usePageTitle } from "@/shared/lib/use-page-title";
import { EmptyState } from "@/shared/ui/empty-state";
import { PageHeader } from "@/shared/ui/page-header";

/** Stand-in for a page that a later development step delivers. */
export function ComingSoonPage({
  title,
  description,
  step,
}: {
  title: string;
  description: string;
  step: number;
}) {
  const { t } = useTranslation();
  usePageTitle(title);
  return (
    <div className="flex flex-col gap-6">
      <PageHeader title={title} description={description} />
      <EmptyState icon={Construction} title={t("common.comingSoon")}>
        {t("common.comingSoonText", { step })}
      </EmptyState>
    </div>
  );
}
