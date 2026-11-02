import { EVENTS, NETWORKS, type Meta, type ScenarioRequest } from "@/shared/schemas";

export type Network = (typeof NETWORKS)[number];
export type ScenarioEvent = (typeof EVENTS)[number];

/** What the form offers on one network (from meta.creation, cotraffic/scenario_catalog.py). */
export interface NetworkOption {
  network: Network;
  events: ScenarioEvent[];
  methods: string[];
  /** Demand factor: 1 except on the large cities, played at reduced demand. */
  scale: number;
  window: number;
  bigCity: boolean;
}

export interface CreationOptions {
  networks: NetworkOption[];
  candidate: string;
  llm: string;
}

const isNetwork = (n: string): n is Network => (NETWORKS as readonly string[]).includes(n);
const isEvent = (e: string): e is ScenarioEvent => (EVENTS as readonly string[]).includes(e);

/**
 * The form's options. Older exports have no catalog: the two networks of the first study,
 * every event and the study's controllers.
 */
export function creationOptions(meta: Meta): CreationOptions {
  const c = meta.creation;
  if (c)
    return {
      networks: c.networks
        .filter((n) => isNetwork(n.network))
        .map((n) => ({
          ...n,
          network: n.network as Network,
          events: n.events.filter(isEvent),
        })),
      candidate: c.candidate,
      llm: c.llm,
    };
  const methods = meta.methods.filter((m) => !m.includes("_ev"));
  return {
    networks: (["grid4x4", "real_district"] as const).map((network) => ({
      network,
      events: [...EVENTS],
      methods,
      scale: 1,
      window: 480,
      bigCity: false,
    })),
    candidate: "hybrid_h2",
    llm: "hybrid_h2_llmstrat",
  };
}

/** A ready-made duel: our candidate against a reference, or against its LLM version. */
export interface Preset {
  key: "vsMp" | "vsFt" | "vsLlm";
  left: string;
  right: string;
}

export function presets(option: NetworkOption, o: CreationOptions): Preset[] {
  const all: Preset[] = [
    { key: "vsMp", left: "mp", right: o.candidate },
    { key: "vsFt", left: "ft", right: o.candidate },
    { key: "vsLlm", left: o.candidate, right: o.llm },
  ];
  return all.filter((p) => option.methods.includes(p.left) && option.methods.includes(p.right));
}

/**
 * The request adjusted to a network: events it cannot generate are dropped, controllers it
 * does not offer are replaced (by our candidate and its first reference).
 */
export function fitRequest(
  request: ScenarioRequest,
  option: NetworkOption,
  o: CreationOptions,
): ScenarioRequest {
  const events = request.events.filter((e) => option.events.includes(e));
  const offered = (m: string) => option.methods.includes(m);
  const first = presets(option, o)[0];
  const right = offered(request.right) ? request.right : (first?.right ?? option.methods[0] ?? "");
  let left = offered(request.left) ? request.left : (first?.left ?? option.methods[1] ?? "");
  if (left === right) left = option.methods.find((m) => m !== right) ?? left;
  return { ...request, network: option.network, events, left, right };
}

/** The default request: our candidate against Max-Pressure, with ambulances and pedestrians. */
export function defaultRequest(o: CreationOptions): ScenarioRequest {
  const option = o.networks.find((n) => n.network === "grid4x4") ?? o.networks[0];
  const base: ScenarioRequest = {
    network: option?.network ?? "grid4x4",
    demand: "peak",
    events: ["emergency", "pedestrians"],
    seed: 3,
    left: "mp",
    right: o.candidate,
  };
  return option ? fitRequest(base, option, o) : base;
}
