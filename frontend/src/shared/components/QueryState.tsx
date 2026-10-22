import type { UseQueryResult } from "@tanstack/react-query";
import { CircleOff, TriangleAlert } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { useSettings } from "@/features/settings/store";
import { DataError } from "@/shared/api/source";
import { Button } from "@/shared/ui/button";
import { Skeleton } from "@/shared/ui/skeleton";

/** Loading, error and empty states of a data query, then its content. */
export function QueryState<T>({
  query,
  children,
  height = 240,
  empty,
}: {
  query: UseQueryResult<T | null>;
  children: (data: T) => ReactNode;
  height?: number;
  empty?: ReactNode;
}) {
  const { t } = useTranslation();
  const source = useSettings((s) => s.dataSource);

  if (query.isPending) {
    return (
      <div role="status" aria-live="polite">
        <span className="sr-only">{t("common.loading")}</span>
        <Skeleton style={{ height }} />
      </div>
    );
  }
  if (query.isError) {
    return (
      <div
        role="alert"
        className="flex flex-col items-start gap-2 rounded-md border border-jam/40 bg-jam-soft p-4"
      >
        <p className="flex items-center gap-2 text-sm font-medium text-jam">
          <TriangleAlert aria-hidden="true" className="size-4" />
          {t("data.loadError")}
        </p>
        <p className="text-xs text-text-2">
          {source === "live" && query.error instanceof DataError && query.error.kind === "network"
            ? t("data.loadErrorLive")
            : query.error.message}
        </p>
        <Button variant="outline" size="sm" onClick={() => void query.refetch()}>
          {t("common.retry")}
        </Button>
      </div>
    );
  }
  if (query.data === null || query.data === undefined) {
    return empty ?? <EmptyData />;
  }
  return <>{children(query.data)}</>;
}

export function EmptyData({ title, text }: { title?: string; text?: string }) {
  const { t } = useTranslation();
  return (
    <div className="flex flex-col items-center gap-2 rounded-md border border-dashed border-border-strong px-4 py-10 text-center">
      <CircleOff aria-hidden="true" className="size-6 text-muted" />
      <p className="text-sm font-medium text-text">{title ?? t("data.noData")}</p>
      <p className="max-w-md text-xs text-text-2">{text ?? t("data.noDataText")}</p>
    </div>
  );
}
