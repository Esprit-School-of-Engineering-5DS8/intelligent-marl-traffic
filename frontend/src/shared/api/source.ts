import type { ZodType } from "zod";

import type { DataSource } from "@/features/settings/store";

export class DataError extends Error {
  constructor(
    message: string,
    readonly status?: number,
  ) {
    super(message);
    this.name = "DataError";
  }
}

/**
 * Where a result file lives. Both sources serve the same exported files:
 * - mock: the static export bundled with the dashboard (public/data), no backend needed;
 * - live: the FastAPI backend, which also runs scenarios and the assistant.
 */
export function dataUrl(source: DataSource, path: string): string {
  return source === "live" ? `/api/data/${path}` : `${import.meta.env.BASE_URL}data/${path}.json`;
}

/** Fetches and validates one file; `optional` files that do not exist resolve to null. */
export async function fetchData<T>(
  source: DataSource,
  path: string,
  schema: ZodType<T>,
  { signal, optional = false }: { signal?: AbortSignal; optional?: boolean } = {},
): Promise<T | null> {
  let response: Response;
  try {
    response = await fetch(dataUrl(source, path), { signal });
  } catch (err) {
    if (signal?.aborted) throw err;
    throw new DataError(
      source === "live" ? `backend unreachable (${path})` : `cannot load ${path}`,
    );
  }
  // a static server answers unknown paths with the app's index.html
  const isJson = response.headers.get("content-type")?.includes("json") ?? false;
  if (response.status === 404 || (response.ok && !isJson)) {
    if (optional) return null;
    throw new DataError(`${path} not found`, 404);
  }
  if (!response.ok) throw new DataError(`${path}: HTTP ${response.status}`, response.status);
  const parsed = schema.safeParse(await response.json());
  if (!parsed.success) {
    const issue = parsed.error.issues[0];
    throw new DataError(`${path}: unexpected data at ${issue?.path.join(".")} (${issue?.message})`);
  }
  return parsed.data;
}
