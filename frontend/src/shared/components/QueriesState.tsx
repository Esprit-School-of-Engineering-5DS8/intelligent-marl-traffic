import type { UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { EmptyData, QueryState } from "./QueryState";

type Data<Q> = Q extends UseQueryResult<infer T> ? NonNullable<T> : never;

/**
 * Several data files at once: the content appears when all of them are there; otherwise
 * the state of the first one that is loading, failed or not exported yet.
 */
export function QueriesState<Q extends Record<string, UseQueryResult<unknown>>>({
  queries,
  children,
  height = 240,
}: {
  queries: Q;
  children: (data: { [K in keyof Q]: Data<Q[K]> }) => ReactNode;
  height?: number;
}) {
  const { t } = useTranslation();
  const blocking = Object.values(queries).find(
    (q) => q.isPending || q.isError || q.data === null || q.data === undefined,
  );
  if (blocking)
    return (
      <QueryState
        query={blocking}
        height={height}
        empty={<EmptyData title={t("data.pending")} text={t("data.pendingText")} />}
      >
        {() => null}
      </QueryState>
    );
  const data = Object.fromEntries(Object.entries(queries).map(([k, q]) => [k, q.data]));
  return <>{children(data as { [K in keyof Q]: Data<Q[K]> })}</>;
}
