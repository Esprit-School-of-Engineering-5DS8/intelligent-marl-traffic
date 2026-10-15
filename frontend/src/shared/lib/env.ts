const DATA_SOURCES = ["mock", "live"] as const;
type DataSourceEnv = (typeof DATA_SOURCES)[number];

function dataSource(value: unknown): DataSourceEnv {
  if (value === undefined || value === "") return "mock";
  if (DATA_SOURCES.includes(value as DataSourceEnv)) return value as DataSourceEnv;
  throw new Error(`VITE_DATA_SOURCE must be "mock" or "live", got "${String(value)}"`);
}

/**
 * Build-time settings, checked once; an invalid value fails loudly at start-up. Plain code
 * rather than a schema so the validation library stays out of the first download.
 */
export const env = {
  VITE_DATA_SOURCE: dataSource(import.meta.env.VITE_DATA_SOURCE),
};
