import { Brain, Cpu, Play, Square, Timer, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  useCatalog,
  useLlmProviders,
  useRecipe,
  type RecipeResponse,
} from "@/shared/api/backend";
import {
  isActiveJob,
  useCancelJob,
  useJobStream,
  useJobs,
  useStartCompare,
  useStartTraining,
  useDeleteJob,
  type Job,
} from "@/shared/api/jobs";
import { QueryState, EmptyData } from "@/shared/components/QueryState";
import { Select } from "@/shared/components/pickers";
import { useFormat } from "@/shared/domain/format";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";
import { PageHeader } from "@/shared/ui/page-header";

import { useTrainingDraft } from "./store";

type Notice = { tone: "flow" | "jam"; text: string };
type Family = "rl" | "llm";

const STATUS_TONE: Record<
  Job["status"],
  "neutral" | "accent" | "flow" | "jam"
> = {
  queued: "neutral",
  running: "accent",
  done: "flow",
  failed: "jam",
  cancelled: "neutral",
};

const SITUATIONS = ["neighbours", "emergency", "pedestrians", "buses", "forecast"] as const;
const DEMAND_LEVELS = ["low", "medium", "peak", "rush_profile"] as const;
const TRAINING_SCENARIOS = ["emergency", "pedestrians", "buses", "incident"] as const;
const OVERLAYS = ["ev_preemption", "pedestrian_service", "mp_fallback"] as const;

type RecipeConfig = Record<string, unknown>;

/** The template defaults, used until the backend's rl.yaml arrives. */
function defaultTemplate(): RecipeConfig {
  return {
    name: "rl",
    algorithm: "ppo",
    observation: Object.fromEntries(SITUATIONS.map((key) => [key, false])),
    reward: { base: "wait", person_weighted: true, co2: 0.5, ev: 2, ped: 0.5, clip: 5 },
    runtime: { overlays: OVERLAYS.map((id) => ({ id })) },
    ppo: {
      learning_rate: 0.0003,
      n_steps: 256,
      batch_size: 64,
      n_epochs: 10,
      gamma: 0.99,
      gae_lambda: 0.95,
      clip_range: 0.2,
      ent_coef: 0,
      net_arch: [64, 64],
    },
    training: { scenarios: ["emergency", "pedestrians", "buses"] },
  };
}

function normalizeTemplate(recipe: RecipeResponse | undefined): RecipeConfig {
  if (!recipe?.config) return defaultTemplate();
  const config = recipe.config as RecipeConfig;
  // Strip identity/metadata fields: the profile name is recomputed server-side.
  const { name, label, description, source, extends: _extends, ...rest } =
    config as RecipeConfig & Record<string, unknown>;
  return rest;
}

function requestText(request: Record<string, unknown>, key: string): string | null {
  const value = request[key];
  return typeof value === "string" ? value : null;
}

export default function TrainingPage() {
  const { t } = useTranslation();
  const f = useFormat();
  const catalog = useCatalog();
  const jobs = useJobs();
  const start = useStartTraining();
  const startCompare = useStartCompare();
  const cancel = useCancelJob();
  const remove = useDeleteJob();
  const draft = useTrainingDraft();

  const [family, setFamily] = useState<Family>("rl");
  const [network, setNetwork] = useState("");
  const [timesteps, setTimesteps] = useState("5000");
  const [seedSet, setSeedSet] = useState<Set<number>>(new Set([1]));

  // RL editor state
  const [profileName, setProfileName] = useState("rl");
  const rlQuery = useRecipe(profileName);
  const [situations, setSituations] = useState<Set<string>>(new Set(["neighbours", "emergency", "pedestrians", "buses"]));
  const [demandLevels, setDemandLevels] = useState<Set<string>>(new Set(["medium", "peak"]));
  const [scenarios, setScenarios] = useState<Set<string>>(new Set(["emergency", "pedestrians", "buses"]));
  const [rewardBase, setRewardBase] = useState("wait");
  const [personWeighted, setPersonWeighted] = useState(true);
  const [evWeight, setEvWeight] = useState("2");
  const [pedWeight, setPedWeight] = useState("0.5");
  const [co2Weight, setCo2Weight] = useState("0.5");
  const [lr, setLr] = useState("0.0003");
  const [nSteps, setNSteps] = useState("256");
  const [batchSize, setBatchSize] = useState("64");
  const [gamma, setGamma] = useState("0.99");
  const [gaeLambda, setGaeLambda] = useState("0.95");
  const [clipRange, setClipRange] = useState("0.2");
  const [entCoef, setEntCoef] = useState("0");

  // LLM editor state
  const llmQuery = useRecipe("llm");
  const providersQuery = useLlmProviders();
  const [provider, setProvider] = useState("");
  const [model, setModel] = useState("");
  const [maxCalls, setMaxCalls] = useState("48");
  const [callInterval, setCallInterval] = useState("30");
  const [timeoutS, setTimeoutS] = useState("30");
  const [attempts, setAttempts] = useState("2");
  const [llmFallback, setLlmFallback] = useState("mp");
  const [benchmarkScenario, setBenchmarkScenario] = useState("emergency");
  const [benchmarkSeeds, setBenchmarkSeeds] = useState("3");

  const [notice, setNotice] = useState<Notice | null>(null);
  const [cancellingId, setCancellingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  const activeTrainJob =
    jobs.data?.find((job) => job.kind === "train" && isActiveJob(job)) ?? null;
  const activeCompareJob =
    jobs.data?.find((job) => job.kind === "compare" && isActiveJob(job)) ?? null;
  useJobStream(activeTrainJob?.id ?? activeCompareJob?.id ?? null);

  useEffect(() => {
    if (!draft.request) return;
    if (draft.network) setNetwork(draft.network);    if (typeof draft.recipe === "string" && draft.recipe) {
      const known = (catalog.data?.agentConfigs ?? []).some(
        (item) => item.name === draft.recipe && item.family === "rl",
      );
      if (known) setProfileName(draft.recipe);
    }
  }, [draft.network, draft.recipe, draft.request, catalog.data]);

  // Loading a saved profile (from the catalog or a scenario card) seeds the editor.
  useEffect(() => {
    const config = rlQuery.data?.config as RecipeConfig | undefined;
    if (!config) return;
    const observation = (config.observation ?? {}) as Record<string, boolean>;
    const reward = (config.reward ?? {}) as Record<string, unknown>;
    const ppo = (config.ppo ?? {}) as Record<string, unknown>;
    const training = (config.training ?? {}) as Record<string, unknown>;
    if (reward.base) setRewardBase(String(reward.base));
    if (typeof reward.person_weighted === "boolean") setPersonWeighted(reward.person_weighted);
    if (reward.ev !== undefined) setEvWeight(String(Number(reward.ev)));
    if (reward.ped !== undefined) setPedWeight(String(Number(reward.ped)));
    if (reward.co2 !== undefined) setCo2Weight(String(Number(reward.co2)));
    if (ppo.learning_rate !== undefined) setLr(String(Number(ppo.learning_rate)));
    if (ppo.n_steps !== undefined) setNSteps(String(Number(ppo.n_steps)));
    if (ppo.batch_size !== undefined) setBatchSize(String(Number(ppo.batch_size)));
    if (ppo.gamma !== undefined) setGamma(String(Number(ppo.gamma)));
    if (ppo.gae_lambda !== undefined) setGaeLambda(String(Number(ppo.gae_lambda)));
    if (ppo.clip_range !== undefined) setClipRange(String(Number(ppo.clip_range)));
    if (ppo.ent_coef !== undefined) setEntCoef(String(Number(ppo.ent_coef)));
    if (Array.isArray(config.observation)) {
      setSituations(new Set(config.observation as string[]));
    } else if (observation && typeof observation === "object") {
      setSituations(
        new Set(
          SITUATIONS.filter((key) => {
            const value = (observation as Record<string, unknown>)[key];
            if (typeof value === "boolean") return value;
            return (config.observation as unknown as string[]).includes(key);
          }),
        ),
      );
    }
    if (Array.isArray(training.demand_levels)) {
      setDemandLevels(new Set(training.demand_levels as string[]));
    }
    if (Array.isArray(training.scenarios)) {
      setScenarios(new Set(training.scenarios as string[]));
    }
  }, [rlQuery.data]);

  const rlRecipe = useMemo((): RecipeConfig => {
    const base = normalizeTemplate(rlQuery.data);
    const template = { ...base };
    template.observation = Object.fromEntries(
      SITUATIONS.map((key) => [key, situations.has(key)]),
    );
    template.reward = {
      base: rewardBase,
      person_weighted: personWeighted,
      co2: Number(co2Weight) || 0,
      ev: Number(evWeight) || 0,
      ped: Number(pedWeight) || 0,
      clip: 5,
    };
    template.runtime = { overlays: OVERLAYS.map((id) => ({ id })) };
    template.ppo = {
      ...(template.ppo as RecipeConfig),
      learning_rate: Number(lr) || 0.0003,
      n_steps: Number(nSteps) || 256,
      batch_size: Number(batchSize) || 64,
      gamma: Number(gamma) || 0.99,
      gae_lambda: Number(gaeLambda) || 0.95,
      clip_range: Number(clipRange) || 0.2,
      ent_coef: Number(entCoef) || 0,
    };
    template.training = {
      ...(template.training as RecipeConfig),
      demand_levels: [...demandLevels],
      scenarios: [...scenarios],
    };
    return template;
  }, [
    rlQuery.data,
    situations,
    rewardBase,
    personWeighted,
    co2Weight,
    evWeight,
    pedWeight,
    lr,
    nSteps,
    batchSize,
    gamma,
    gaeLambda,
    clipRange,
    entCoef,
    demandLevels,
    scenarios,
  ]);

  const llmRecipeConfig = useMemo((): RecipeConfig => {
    const base = normalizeTemplate(llmQuery.data);
    return {
      ...base,
      name: "llm",
      provider: provider || (base.provider as string) || "groq",
      model: model || null,
      max_calls: Number(maxCalls) || 48,
      call_interval_s: Number(callInterval) || 30,
      timeout_s: Number(timeoutS) || 30,
      attempts: Number(attempts) || 2,
      fallback: llmFallback,
    };
  }, [llmQuery.data, provider, model, maxCalls, callInterval, timeoutS, attempts, llmFallback]);

  const networks = catalog.data?.networks.filter((item) => item.runnable) ?? [];
  const selectedNetwork = networks.some((item) => item.network === network)
    ? network
    : (networks[0]?.network ?? "");
  const profiles = catalog.data?.agentConfigs.filter((item) => item.family === "rl") ?? [];
  const canSubmitRl = Boolean(selectedNetwork) && !activeTrainJob && !start.isPending;
  const canBenchmark = Boolean(selectedNetwork) && !activeCompareJob && !startCompare.isPending;
  const seedList = [...seedSet].length ? [...seedSet].sort((a, b) => a - b) : [1];

  const submitRl = () => {
    setNotice(null);
    start.mutate(
      {
        network: selectedNetwork,
        seeds: seedList,
        timesteps: Number(timesteps),
        recipe: rlRecipe,
      },
      {
        onSuccess: (job) =>
          setNotice({
            tone: "flow",
            text: t("training.started", {
              recipe: requestText(job.request, "recipe_id") ?? "rl",
              network: f.networkName(selectedNetwork),
            }),
          }),
        onError: (error) =>
          setNotice({
            tone: "jam",
            text: error instanceof Error ? error.message : t("training.startError"),
          }),
      },
    );
  };

  const submitBenchmark = () => {
    setNotice(null);
    const seeds = [Number(benchmarkSeeds) || 3];
    startCompare.mutate(
      {
        network: selectedNetwork,
        scenario: benchmarkScenario,
        demand: "medium",
        seeds,
        methods: ["llm", "mp"],
        quick: true,
        overrides: { llm: { llm: llmRecipeConfig } },
      },
      {
        onSuccess: (job) =>
          setNotice({
            tone: "flow",
            text: t("training.benchmarkStarted", {
              method: requestText(job.request, "anchor") ?? "LLM",
              network: f.networkName(selectedNetwork),
            }),
          }),
        onError: (error) =>
          setNotice({
            tone: "jam",
            text: error instanceof Error ? error.message : t("training.startError"),
          }),
      },
    );
  };

  const toggle = (set: Set<string>, value: string) => {
    const clone = new Set(set);
    if (clone.has(value)) {
      clone.delete(value);
    } else {
      clone.add(value);
    }
    return clone;
  };

  const toggleSeed = (value: number) =>
    setSeedSet((current) => {
      const clone = new Set(current);
      if (clone.has(value)) {
        if (clone.size > 1) clone.delete(value);
      } else {
        clone.add(value);
      }
      return clone;
    });

  const cancelJob = (jobId: string) => {
    setCancellingId(jobId);
    cancel.mutate(jobId, {
      onError: (error) =>
        setNotice({
          tone: "jam",
          text: error instanceof Error ? error.message : t("training.cancelError"),
        }),
      onSettled: () => setCancellingId(null),
    });
  };

  const deleteJob = (jobId: string) => {
    setDeletingId(jobId);
    remove.mutate(jobId, {
      onError: (error) =>
        setNotice({
          tone: "jam",
          text: error instanceof Error ? error.message : t("training.deleteError"),
        }),
      onSettled: () => setDeletingId(null),
    });
  };

  return (
    <div className="flex flex-col gap-4">
      <PageHeader title={t("training.title")} description={t("training.description")} />

      <div className="flex items-center gap-2" role="tablist">
        {(
          [
            ["rl", Cpu, t("training.familyRl")],
            ["llm", Brain, t("training.familyLlm")],
          ] as const
        ).map(([value, Icon, label]) => (
          <button
            key={value}
            type="button"
            role="tab"
            aria-selected={family === value}
            onClick={() => setFamily(value)}
            className={
              family === value
                ? "inline-flex items-center gap-2 border border-accent/40 bg-accent-soft px-3 py-2 text-sm text-accent"
                : "inline-flex items-center gap-2 border border-border bg-surface px-3 py-2 text-sm text-text-2 hover:bg-surface-3"
            }
          >
            <Icon aria-hidden="true" className="size-4" />
            {label}
          </button>
        ))}
      </div>

      {notice ? (
        <div
          role="status"
          className={
            notice.tone === "flow"
              ? "border border-flow/40 bg-flow-soft px-3 py-2 text-sm text-flow"
              : "border border-jam/40 bg-jam-soft px-3 py-2 text-sm text-jam"
          }
        >
          {notice.text}
        </div>
      ) : null}

      <QueryState query={catalog} height={280}>
        {(data) => {
          const activeJob = family === "rl" ? activeTrainJob : activeCompareJob;

          return (
            <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
              <Card>
                <CardHeader>
                  <CardTitle>{t("training.formTitle")}</CardTitle>
                  <CardDescription>
                    {family === "rl" ? t("training.formTextRl") : t("training.formTextLlm")}
                  </CardDescription>
                </CardHeader>
                <CardContent className="flex flex-col gap-3">
                  <Select
                    label={t("training.network")}
                    value={selectedNetwork}
                    options={data.networks
                      .filter((item) => item.runnable)
                      .map((item) => ({
                        value: item.network,
                        label: f.networkName(item.network),
                      }))}
                    onChange={setNetwork}
                  />

                  {family === "rl" ? (
                    <>
                      <Select
                        label={t("training.profile")}
                        value={profileName}
                        options={[
                          { value: "rl", label: t("training.profileNew") },
                          ...profiles
                            .filter((item) => item.name !== "rl")
                            .map((item) => ({
                              value: item.name,
                              label: item.label || item.name,
                            })),
                        ]}
                        onChange={setProfileName}
                      />
                      <Select
                        label={t("training.profile")}
                        value={profileName}
                        options={[
                          { value: "rl", label: t("training.profileNew") },
                          ...profiles
                            .filter((item) => item.name !== "rl")
                            .map((item) => ({
                              value: item.name,
                              label: item.label || item.name,
                            })),
                        ]}
                        onChange={setProfileName}
                      />
                      <FieldGroup label={t("training.situations")}>
                        {SITUATIONS.map((key) => (
                          <ChipButton
                            key={key}
                            on={situations.has(key)}
                            label={t(`training.situation_${key}`)}
                            onClick={() => setSituations(toggle(situations, key))}
                          />
                        ))}
                      </FieldGroup>

                      <FieldGroup label={t("training.demandProfile")}>
                        {DEMAND_LEVELS.map((key) => (
                          <ChipButton
                            key={key}
                            on={demandLevels.has(key)}
                            label={t(`training.demand_${key}`)}
                            onClick={() => setDemandLevels(toggle(demandLevels, key))}
                          />
                        ))}
                      </FieldGroup>

                      <FieldGroup label={t("training.scenarios")}>
                        {TRAINING_SCENARIOS.map((key) => (
                          <ChipButton
                            key={key}
                            on={scenarios.has(key)}
                            label={t(`training.scenario_${key}`)}
                            onClick={() => setScenarios(toggle(scenarios, key))}
                          />
                        ))}
                      </FieldGroup>

                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                        <Select
                          label={t("training.rewardBase")}
                          value={rewardBase}
                          options={["wait", "queue", "pressure"].map((value) => ({ value, label: t(`training.rewardBase_${value}`) }))}
                          onChange={setRewardBase}
                        />
                        <NumberField label={t("training.weightEv")} value={evWeight} onChange={setEvWeight} />
                        <NumberField label={t("training.weightPed")} value={pedWeight} onChange={setPedWeight} />
                        <NumberField label={t("training.weightCo2")} value={co2Weight} onChange={setCo2Weight} />
                      </div>

                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                        <NumberField label={t("training.hpLearningRate")} value={lr} onChange={setLr} />
                        <NumberField label={t("training.hpNSteps")} value={nSteps} onChange={setNSteps} />
                        <NumberField label={t("training.hpBatch")} value={batchSize} onChange={setBatchSize} />
                        <NumberField label={t("training.hpGamma")} value={gamma} onChange={setGamma} />
                        <NumberField label={t("training.hpGaeLambda")} value={gaeLambda} onChange={setGaeLambda} />
                        <NumberField label={t("training.hpClip")} value={clipRange} onChange={setClipRange} />
                        <NumberField label={t("training.hpEntCoef")} value={entCoef} onChange={setEntCoef} />
                        <Select
                          label={t("training.timesteps")}
                          value={timesteps}
                          options={["1000", "5000", "25000", "100000"].map((value) => ({
                            value,
                            label: f.number(Number(value)),
                          }))}
                          onChange={setTimesteps}
                        />
                      </div>

                      <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
                        <FieldGroup label={t("training.seedsMultiple")} className="flex flex-wrap gap-1">
                          {Array.from({ length: 8 }, (_, index) => index + 1).map((seed) => (
                            <ChipButton
                              key={seed}
                              on={seedSet.has(seed)}
                              label={String(seed)}
                              onClick={() => toggleSeed(seed)}
                            />
                          ))}
                        </FieldGroup>
                      </div>

                      {activeTrainJob ? (
                        <p className="border border-accent/30 bg-accent-soft px-3 py-2 text-xs text-accent">
                          {t("training.oneJob")}
                        </p>
                      ) : null}
                      <Button
                        type="button"
                        variant="primary"
                        disabled={!canSubmitRl}
                        onClick={submitRl}
                      >
                        <Play aria-hidden="true" />
                        {start.isPending ? t("training.starting") : t("training.submit")}
                      </Button>
                    </>
                  ) : (
                    <>
                      <div className="grid grid-cols-2 gap-3">
                        <Select
                          label={t("training.llmProvider")}
                          value={provider}
                          options={(providersQuery.data?.providers ?? []).map((entry) => ({
                            value: entry.id,
                            label: entry.label + (entry.available ? "" : " (API key missing)"),
                          }))}
                          onChange={(value) => {
                            setProvider(value);
                            const first =
                              providersQuery.data?.providers.find((entry) => entry.id === value)
                                ?.models?.[0]?.id ?? "";
                            setModel(first);
                          }}
                        />
                        <Select
                          label={t("training.llmModel")}
                          value={model}
                          options={(
                            providersQuery.data?.providers.find((entry) => entry.id === (provider || "groq"))
                              ?.models ?? []
                          ).map((entry) => ({ value: entry.id, label: entry.id }))}
                          onChange={setModel}
                        />
                      </div>
                      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                        <NumberField label={t("training.llmMaxCalls")} value={maxCalls} onChange={setMaxCalls} />
                        <NumberField label={t("training.llmInterval")} value={callInterval} onChange={setCallInterval} />
                        <NumberField label={t("training.llmTimeout")} value={timeoutS} onChange={setTimeoutS} />
                        <NumberField label={t("training.llmAttempts")} value={attempts} onChange={setAttempts} />
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <Select
                          label={t("training.llmFallback")}
                          value={llmFallback}
                          options={[
                            { value: "mp", label: t("training.fallbackMp") },
                            { value: "ft", label: t("training.fallbackFt") },
                          ]}
                          onChange={setLlmFallback}
                        />
                        <Select
                          label={t("training.benchmarkScenario")}
                          value={benchmarkScenario}
                          options={["normal", "emergency", "pedestrians", "buses", "incident"].map(
                            (value) => ({ value, label: t(`scenarioPage.event_${value}`, { defaultValue: value }) }),
                          )}
                          onChange={setBenchmarkScenario}
                        />
                      </div>
                      <div className="grid grid-cols-2 gap-3">
                        <NumberField label={t("training.seeds")} value={benchmarkSeeds} onChange={setBenchmarkSeeds} />
                      </div>
                      {activeCompareJob ? (
                        <p className="border border-accent/30 bg-accent-soft px-3 py-2 text-xs text-accent">
                          {t("training.oneBenchmark")}
                        </p>
                      ) : null}
                      <Button
                        type="button"
                        variant="primary"
                        disabled={!canBenchmark}
                        onClick={submitBenchmark}
                      >
                        <Play aria-hidden="true" />
                        {startCompare.isPending ? t("training.starting") : t("training.submitBenchmark")}
                      </Button>
                    </>
                  )}
                </CardContent>
              </Card>

              <Card>
                <CardHeader className="flex-row items-center justify-between gap-2">
                  <div className="flex flex-col gap-1">
                    <CardTitle>
                      {family === "rl" ? t("training.queue") : t("training.benchmarkQueue")}
                    </CardTitle>
                    <CardDescription>
                      {family === "rl" ? t("training.queueText") : t("training.benchmarkQueueText")}
                    </CardDescription>
                  </div>
                  {activeJob ? <Badge tone="accent">{t("training.live")}</Badge> : null}
                </CardHeader>
                <CardContent>
                  <QueryState query={jobs} height={220}>
                    {(items) => {
                      const kind = family === "rl" ? "train" : "compare";
                      const familyJobs = items.filter((job) => job.kind === kind);
                      if (!familyJobs.length) {
                        return (
                          <EmptyData
                            title={t("training.empty")}
                            text={t("training.emptyText")}
                          />
                        );
                      }
                      return (
                        <ul className="flex flex-col divide-y divide-border">
                          {familyJobs.map((job) => (
                            <JobRow
                              key={job.id}
                              job={job}
                              cancelling={cancellingId === job.id}
                              deleting={deletingId === job.id}
                              onCancel={() => cancelJob(job.id)}
                              onDelete={() => deleteJob(job.id)}
                            />
                          ))}
                        </ul>
                      );
                    }}
                  </QueryState>
                </CardContent>
              </Card>
            </div>
          );
        }}
      </QueryState>
    </div>
  );
}

function ChipButton({
  on,
  label,
  onClick,
}: {
  on: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={
        on
          ? "border border-accent/40 bg-accent-soft px-2.5 py-1.5 text-xs font-medium text-accent"
          : "border border-border bg-surface px-2.5 py-1.5 text-xs text-text-2 hover:bg-surface-3"
      }
    >
      {label}
    </button>
  );
}

function FieldGroup({
  label,
  className = "flex flex-wrap gap-1",
  children,
}: {
  label: string;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1 text-[11px] text-muted">
      <span>{label}</span>
      <span className={className}>{children}</span>
    </label>
  );
}

function NumberField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-[11px] text-muted">
      <span>{label}</span>
      <input
        type="number"
        step="any"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="border border-border bg-surface px-2 py-1.5 text-sm text-text"
      />
    </label>
  );
}

function JobRow({
  job,
  cancelling,
  deleting,
  onCancel,
  onDelete,
}: {
  job: Job;
  cancelling: boolean;
  deleting: boolean;
  onCancel: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const f = useFormat();
  const recipe = requestText(job.request, "label") ?? requestText(job.request, "recipe_id");
  const network = requestText(job.request, "network");
  const percent =
    job.totalSteps > 0
      ? Math.min(100, (job.step / job.totalSteps) * 100)
      : job.status === "done"
        ? 100
        : 0;
  const canCancel = job.status === "queued" || job.status === "running";
  const canDelete = !canCancel;
  const checkpoint = job.checkpointPath?.split(/[\\/]/).pop() ?? null;
  const lastLog = job.log.at(-1) ?? null;
  const methods = Array.isArray((job.request as Record<string, unknown>).methods)
    ? ((job.request as { methods: string[] }).methods ?? []).join(" vs ")
    : null;

  return (
    <li className="flex flex-col gap-2 py-3 first:pt-0 last:pb-0">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-text">
            {recipe ?? methods ?? t("training.title")}
            {network ? <span className="text-muted"> · {f.networkName(network)}</span> : null}
          </p>
          <p className="text-[11px] text-muted">{f.date(job.createdAt)}</p>
        </div>
        <div className="flex items-center gap-2">
          <Badge tone={STATUS_TONE[job.status]}>{t(`training.${job.status}`)}</Badge>
          {canCancel ? (
            <Button
              type="button"
              variant="outline"
              size="sm"
              disabled={cancelling}
              onClick={onCancel}
            >
              <Square aria-hidden="true" />
              {cancelling ? t("training.cancelling") : t("training.cancel")}
            </Button>
          ) : null}
          {canDelete ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              aria-label={t("training.delete")}
              disabled={deleting}
              onClick={onDelete}
            >
              <Trash2 aria-hidden="true" />
            </Button>
          ) : null}
        </div>
      </div>

      <div className="h-2 w-full bg-surface-3" aria-hidden="true">
        <div
          className={
            job.status === "failed"
              ? "h-full bg-jam transition-[width]"
              : job.status === "done"
                ? "h-full bg-flow transition-[width]"
                : "h-full bg-accent transition-[width]"
          }
          style={{ width: `${percent}%` }}
        />
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-text-2">
        {job.kind === "train" ? (
          <span>
            {t("training.progress", {
              step: f.number(job.step),
              total: f.number(job.totalSteps),
            })}
          </span>
        ) : (
          <span>
            {t("training.stepOf", { step: job.step, total: f.number(job.totalSteps) })}
          </span>
        )}
        {job.status === "running" ? (
          <>
            <span>{t("training.rate", { rate: f.number(job.stepsPerS, 1) })}</span>
            <span className="inline-flex items-center gap-1">
              <Timer aria-hidden="true" className="size-3" />
              {t("training.eta", { eta: f.number(job.etaS, 0) })}
            </span>
          </>
        ) : null}
        {job.reward !== null ? (
          <span>{t("training.reward", { reward: f.number(job.reward, 2) })}</span>
        ) : null}
        {job.meanHalting !== null ? (
          <span>{t("training.halting", { halting: f.number(job.meanHalting, 2) })}</span>
        ) : null}
        {checkpoint ? (
          <span className="truncate" title={job.checkpointPath ?? undefined}>
            {t("training.checkpoint", { name: checkpoint })}
          </span>
        ) : null}
      </div>

      {job.error ? <p className="text-xs text-jam">{job.error}</p> : null}
      {!job.error && job.status === "running" && lastLog ? (
        <p className="truncate text-[11px] text-muted" title={lastLog}>
          {lastLog}
        </p>
      ) : null}
    </li>
  );
}
