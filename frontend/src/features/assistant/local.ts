/**
 * The assistant without a backend: reads the question with keywords (controllers, metric,
 * network, demand, scenario, intent), computes the answer from the exported results and
 * writes it from templates. Every number comes from the result files; nothing is
 * generated. The backend's language model, when available, words answers better but
 * follows the same rule (numbers checked against the results).
 */
import type { Format } from "@/shared/domain/format";
import { METHOD_LABELS } from "@/shared/domain/methods";
import { gainPct, metricInfo } from "@/shared/domain/metrics";
import { findComparison, indexSummary } from "@/shared/domain/results";
import type {
  Cell,
  ChatEvent,
  Comparison,
  Meta,
  PageContext,
  SummaryRow,
  ToolCall,
} from "@/shared/schemas";

type Translate = (key: string, options?: Record<string, unknown>) => string;

const norm = (s: string) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

const METRIC_WORDS: [string, string[]][] = [
  ["ev_delay", ["urgence", "ambulance", "emergency", "pompier", "طوارئ", "اسعاف", "إسعاف"]],
  ["ped_mean_waiting_time", ["pieton", "pedestrian", "passage", "مشاة", "المشاة"]],
  ["co2_total_kg", ["co2", "carbone", "emission", "pollution", "كربون", "انبعاث"]],
  ["mean_travel_time", ["trajet", "travel", "parcours", "duree", "رحلة", "الرحلة"]],
  ["throughput_per_h", ["debit", "throughput", "تدفق"]],
  ["person_weighted_delay", ["personne", "person", "passager", "اشخاص", "أشخاص"]],
  ["stops_per_vehicle", ["arret", "stop", "توقف"]],
  ["mean_waiting_time", ["attente", "waiting", "wait", "attend", "انتظار", "الانتظار"]],
];
const SCENARIO_WORDS: [string, string[]][] = [
  ["emergency", ["urgence", "ambulance", "emergency", "طوارئ"]],
  ["pedestrians", ["pieton", "pedestrian", "مشاة"]],
  ["incident", ["accident", "incident", "bloque", "حادث"]],
  ["buses", ["bus", "حافل"]],
];
const NETWORK_WORDS: [string, string[]][] = [
  ["real_district", ["quartier", "district", "reel", "real", "osm", "ville", "حي"]],
  ["grid8x8", ["8x8"]],
  ["grid4x4", ["grille", "grid", "4x4", "شبكة"]],
];
const DEMAND_WORDS: [string, string[]][] = [
  ["rush_profile", ["profil", "profile", "rush"]],
  ["peak", ["pointe", "peak", "ذروة", "الذروة"]],
  ["medium", ["moyenne", "medium", "متوسط"]],
  ["low", ["faible", "low", "creuse", "منخفض"]],
];
const CHART_WORDS = [
  "graphique",
  "graph",
  "chart",
  "courbe",
  "montre",
  "affiche",
  "show",
  "plot",
  "مخطط",
  "رسم",
  "اعرض",
];
const RUN_WORDS = ["lance", "lancer", "simule", "simuler", "run ", "execute", "شغل", "شغّل"];
const BEST_WORDS = ["meilleur", "best", "classement", "rank", "افضل", "أفضل"];

function pick<T extends string>(q: string, table: [T, string[]][]): T | undefined {
  return table.find(([, words]) => words.some((w) => q.includes(norm(w))))?.[0];
}

/** Controllers named in the question, longest names first ("coop-full" before "coop"). */
function controllers(q: string): string[] {
  const names = Object.entries(METHOD_LABELS)
    .flatMap(([id, label]) => [
      [id, norm(label)],
      [id, id.replace(/_/g, "-")],
      [id, id.replace(/_/g, " ")],
    ])
    .sort((a, b) => b[1]!.length - a[1]!.length);
  const found: { id: string; at: number }[] = [];
  let rest = ` ${q} `;
  for (const [id, name] of names) {
    const re = new RegExp(
      `(^|[^a-z0-9-])${name!.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?=[^a-z0-9-]|$)`,
    );
    const m = re.exec(rest);
    if (m && !found.some((f) => f.id === id)) {
      found.push({ id: id!, at: m.index });
      rest = rest.slice(0, m.index) + " ".repeat(m[0].length) + rest.slice(m.index + m[0].length);
    }
  }
  return found.sort((a, b) => a.at - b.at).map((f) => f.id);
}

export interface LocalData {
  meta: Meta;
  summary: SummaryRow[];
  comparisons: Comparison[];
}

export function* answerLocally(
  question: string,
  context: PageContext,
  data: LocalData,
  t: Translate,
  f: Format,
  live: boolean,
): Generator<ChatEvent> {
  const q = norm(question);
  const index = indexSummary(data.summary);
  const named = controllers(q);
  const metric = pick(q, METRIC_WORDS) ?? "mean_waiting_time";
  const scenarioHint =
    pick(q, SCENARIO_WORDS) ??
    (metric === "ev_delay"
      ? "emergency"
      : metric === "ped_mean_waiting_time"
        ? "pedestrians"
        : undefined);
  const network = pick(q, NETWORK_WORDS) ?? context.cell?.network ?? "grid4x4";
  const demand = pick(q, DEMAND_WORDS) ?? context.cell?.demand ?? "peak";
  const scenario = scenarioHint ?? context.cell?.scenario ?? "normal";

  // the closest evaluated cell to what was asked
  const cells = data.meta.cells;
  const cell: Cell | undefined =
    cells.find((c) => c.network === network && c.scenario === scenario && c.demand === demand) ??
    cells.find((c) => c.network === network && c.scenario === scenario) ??
    cells.find((c) => c.scenario === scenario && c.demand === demand) ??
    cells.find((c) => c.network === network && c.demand === demand);

  const junction = /\b([a-z]\d{1,2})\b/i.exec(question)?.[1];
  if (junction && /carrefour|junction|intersection|feu|تقاطع/.test(q)) {
    const call: ToolCall = {
      name: "focusIntersection",
      args: { network: cell?.network ?? network, junction: junction.toUpperCase() },
    };
    yield {
      type: "token",
      text: t("assistantChat.answers.focus", { junction: junction.toUpperCase() }),
    };
    yield { type: "tool_call", id: "focus", call };
    yield { type: "done", writtenBy: "code" };
    return;
  }

  if (RUN_WORDS.some((w) => q.includes(norm(w)))) {
    if (!live) {
      yield { type: "token", text: t("assistantChat.answers.runOffline") };
      yield { type: "done", writtenBy: "code" };
      return;
    }
    const events = (["emergency", "pedestrians", "incident", "buses"] as const).filter((e) =>
      SCENARIO_WORDS.find(([s]) => s === e)?.[1].some((w) => q.includes(norm(w))),
    );
    const net = network === "real_district" ? "real_district" : "grid4x4";
    const dem = demand === "rush_profile" ? "peak" : (demand as "low" | "medium" | "peak");
    const call: ToolCall = {
      name: "runScenario",
      args: {
        network: net,
        demand: dem,
        events: events.length ? events : ["emergency"],
        seed: 3,
        left: named[0] ?? "ft",
        right: named[1] ?? "coop_full",
      },
    };
    yield {
      type: "token",
      text: t("assistantChat.answers.run", {
        left: f.methodName(call.args.left),
        right: f.methodName(call.args.right),
        network: f.networkName(net),
        events: call.args.events.map(f.scenarioName).join(", "),
        demand: f.demandName(dem).toLowerCase(),
      }),
    };
    yield { type: "tool_call", id: "run", call };
    yield { type: "done", writtenBy: "code" };
    return;
  }

  if (!cell) {
    yield { type: "token", text: t("assistantChat.notUnderstood") };
    yield { type: "done", writtenBy: "code" };
    return;
  }
  const cellName = f.cellName(cell);
  const methods = index.methods(cell, metric);

  if (CHART_WORDS.some((w) => q.includes(norm(w)))) {
    const shown = named.length ? named.filter((m) => methods.includes(m)) : methods;
    yield {
      type: "token",
      text: t("assistantChat.answers.chart", {
        metric: f.metricInSentence(metric),
        cell: cellName,
      }),
    };
    yield {
      type: "tool_call",
      id: "chart",
      call: {
        name: "generateChart",
        args: { cell, metric, controllers: shown.length ? shown : methods },
      },
    };
    yield { type: "source", file: "results/summary/summary.csv" };
    yield { type: "done", writtenBy: "code" };
    return;
  }

  if (named.length < 2 && (BEST_WORDS.some((w) => q.includes(norm(w))) || named.length === 0)) {
    const better = metricInfo(metric).better === "higher" ? -1 : 1;
    const ranked = methods
      .map((m) => ({ m, v: index.get(cell, m, metric)?.mean }))
      .filter((x): x is { m: string; v: number } => typeof x.v === "number")
      .sort((a, b) => better * (a.v - b.v));
    const [first, second] = ranked;
    if (first && second) {
      yield {
        type: "token",
        text: t("assistantChat.answers.best", {
          metric: f.metricInSentence(metric),
          cell: cellName,
          best: f.methodName(first.m),
          value: f.metric(first.v, metric),
          second: f.methodName(second.m),
          value2: f.metric(second.v, metric),
        }),
      };
      yield { type: "source", file: "results/summary/summary.csv" };
      yield { type: "done", writtenBy: "code" };
      return;
    }
  }

  const a = named[0] ?? "coop_full";
  const b = named[1] ?? (a === "ft" ? "coop_full" : "ft");
  const ra = index.get(cell, a, metric);
  const rb = index.get(cell, b, metric);
  if (!ra || ra.mean === null || !rb || rb.mean === null) {
    yield {
      type: "token",
      text: t("assistantChat.answers.missing", {
        a: f.methodName(!ra ? a : b),
        cell: cellName,
        metric: f.metricInSentence(metric),
      }),
    };
    yield { type: "done", writtenBy: "code" };
    return;
  }
  const test = findComparison(data.comparisons, cell, a, b, metric);
  const gain = test?.pairedImprovementPct ?? gainPct(metric, ra.mean, rb.mean) ?? 0;
  const params = {
    a: f.methodName(a),
    b: f.methodName(b),
    metric: f.metricInSentence(metric),
    cell: cellName,
    va: f.metric(ra.mean, metric),
    vb: f.metric(rb.mean, metric),
    gain: f.pct(Math.abs(gain), 1, false),
    dir: gain >= 0 ? t("assistantChat.answers.better") : t("assistantChat.answers.worse"),
  };
  if (test && test.pairedCiLo !== null && test.pairedCiHi !== null) {
    yield {
      type: "token",
      text: t("assistantChat.answers.compare", {
        ...params,
        lo: f.pct(test.pairedCiLo),
        hi: f.pct(test.pairedCiHi),
        p: f.number(test.pHolm, 3),
        sig: test.significant ? t("kpi.significant") : t("kpi.notSignificant"),
      }),
    };
    yield { type: "source", file: `results/summary/comparisons_${metric}.csv` };
  } else {
    yield { type: "token", text: t("assistantChat.answers.compareMeans", params) };
  }
  yield { type: "source", file: "results/summary/summary.csv" };
  yield {
    type: "tool_call",
    id: "compare",
    call: { name: "compareControllers", args: { cell, a, b, metric } },
  };
  yield { type: "done", writtenBy: "code" };
}
