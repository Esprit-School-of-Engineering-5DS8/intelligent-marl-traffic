import type { Format } from "@/shared/domain/format";

/** "4x4 grid · Emergency vehicles · Peak · s3" for a replay id. */
export function replayTitle(id: string, f: Format): string {
  const [network = "", scenario = "", demand = "", seed = ""] = id.split("__");
  return `${f.networkName(network)} · ${scenario.split("+").map(f.scenarioName).join(" + ")} · ${f.demandName(demand)} · ${seed}`;
}
