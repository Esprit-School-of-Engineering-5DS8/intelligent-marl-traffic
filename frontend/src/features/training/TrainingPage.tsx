import React, { useState, useEffect } from "react";
import {
  Cpu,
  GitFork,
  Sparkles,
  Check,
  ChevronRight,
  Sliders,
  ShieldCheck,
  Zap,
  Play,
  RotateCcw,
  Layers,
  Terminal,
  Activity,
  AlertTriangle,
  Info,
  Tag,
  Dna,
  Key,
  CheckCircle2,
  XCircle,
  ExternalLink,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useCatalog } from "@/shared/api/backend";
import { useStartCompare, useStartTraining, useJobs, isActiveJob } from "@/shared/api/jobs";
import { useFormat } from "@/shared/domain/format";
import { NumberField } from "@/shared/ui/number-field";
import { RangeInput } from "@/shared/ui/range-input";
import { SelectControl } from "@/shared/ui/select";

export type TrainingArchetype = "rl" | "hybrid" | "llm";

interface LLMProviderInfo {
  id: string;
  label: string;
  available: boolean;
  models: { id: string; context_window: number }[];
}

interface ProvidersResponse {
  providers: LLMProviderInfo[];
  default: { provider: string; model: string };
  // "mock" and "replay" answer without a provider key.
  backend?: string;
  keyless?: boolean;
}

interface ArchetypeCard {
  id: TrainingArchetype;
  title: string;
  subtitle: string;
  badge: string;
  badgeTone: string;
  icon: React.ElementType;
  description: string;
  highlights: string[];
}

const ARCHETYPES: ArchetypeCard[] = [
  {
    id: "rl",
    title: "RL Model",
    subtitle: "High-frequency closed-loop policy",
    badge: "Fast & Autonomous",
    badgeTone: "border-accent/40 text-accent bg-accent/10",
    icon: Cpu,
    description:
      "End-to-end Reinforcement Learning (PPO) trained directly against SUMO simulator reward functions. Sub-second actuation at edge intersections with minimal compute overhead.",
    highlights: [
      "Microsecond phase switching latency",
      "PPO policy optimization across seeds",
      "Dense reward shaping (delay, queue, halting)",
    ],
  },
  {
    id: "hybrid",
    title: "Hybrid Model",
    subtitle: "RL + LLM Hierarchical Orchestrator",
    badge: "Recommended",
    badgeTone: "border-accent/40 text-accent bg-accent/10",
    icon: GitFork,
    description:
      "Hierarchical dual-tier controller: local RL policies execute reactive signal timing, while LLM reasoning analyzes regional corridors, incidents, and congestion anomalies to adapt policy objectives.",
    highlights: [
      "Dual-layer macro/micro coordination",
      "LLM dynamic reward reweighting",
      "Resilient fallback to pure RL during API timeouts",
    ],
  },
  {
    id: "llm",
    title: "Full LLM Option",
    subtitle: "Context-aware reasoning agent",
    badge: "Semantic & Adaptive",
    badgeTone: "border-accent/40 text-accent bg-accent/10",
    icon: Sparkles,
    description:
      "Direct chain-of-thought and tool-assisted language models orchestrating multi-junction corridors with natural-language explainability, incident response, and zero-shot scenario handling.",
    highlights: [
      "Zero-shot emergency priority routing",
      "Natural language strategy explanations",
      "Dynamic prompt conditioning on lane telemetry",
    ],
  },
];

const AVAILABLE_SEEDS = [1, 2, 3, 7, 21, 42, 100, 1337];

// The demand profiles that exist in configs/demand/. `emergency` is an event scenario,
// not a demand level, and the backend rejects it as one.
const DEMAND_LEVELS = [
  { value: "low", label: "Low", hint: "45% of the calibrated peak rate" },
  { value: "medium", label: "Medium", hint: "70% of the calibrated peak rate" },
  { value: "peak", label: "Peak", hint: "100% of the calibrated peak rate" },
  { value: "rush_profile", label: "Rush", hint: "ramp up, hold, ramp down over the hour" },
];
const ALL_DEMAND_LEVELS = DEMAND_LEVELS.map((level) => level.value);
// Every event the simulator can inject, so one policy covers all situations.
const TRAINING_SCENARIOS = ["normal", "emergency", "pedestrians", "buses", "incident"];

const GEMINI_MODELS = [
  { value: "gemini-2.5-flash", label: "gemini-2.5-flash (Ultra-fast / Low latency)" },
  { value: "gemini-2.5-pro", label: "gemini-2.5-pro (Deep corridor reasoning)" },
  { value: "gemini-1.5-flash", label: "gemini-1.5-flash (Balanced)" },
  { value: "gemini-1.5-pro", label: "gemini-1.5-pro (High context window)" },
];

const GROQ_MODELS = [
  { value: "qwen/qwen3.8-27b", label: "qwen/qwen3.8-27b (Fast Reasoning)" },
  { value: "llama-3.3-70b-versatile", label: "llama-3.3-70b-versatile (Flagship)" },
  { value: "llama-3.1-8b-instant", label: "llama-3.1-8b-instant (Sub-100ms)" },
  { value: "openai/gpt-oss-120b", label: "openai/gpt-oss-120b (Complex multi-agent)" },
  { value: "openai/gpt-oss-20b", label: "openai/gpt-oss-20b (Default)" },
];

const BASE_POLICIES = [
  { value: "sf_mission_2x2", label: "sf_mission_2x2_ppo_checkpoint_100k.pt" },
  { value: "sf_mission_3x3", label: "sf_mission_3x3_ppo_checkpoint_100k.pt" },
  { value: "monaco", label: "monaco_ppo_checkpoint_100k.pt" },
  { value: "tunis", label: "tunis_ppo_checkpoint_100k.pt" },
  { value: "train_fresh", label: "Train fresh alongside supervisor" },
];

export default function TrainingPage() {
  const [selected, setSelected] = useState<TrainingArchetype | null>("hybrid");
  const catalog = useCatalog();
  const jobs = useJobs();
  const startTraining = useStartTraining();
  const startCompare = useStartCompare();
  const f = useFormat();

  // Query live LLM providers and API key readiness from backend
  const { data: providersData, isLoading: providersLoading } = useQuery<ProvidersResponse>({
    queryKey: ["llm-providers"],
    queryFn: async () => {
      const res = await fetch("/api/llm/providers");
      if (!res.ok) throw new Error("Failed to fetch LLM providers status");
      return res.json();
    },
    refetchInterval: 10000,
  });

  const groqProvider = providersData?.providers.find((p) => p.id === "groq");
  const geminiProvider = providersData?.providers.find((p) => p.id === "gemini");

  const groqReady = Boolean(groqProvider?.available);
  const geminiReady = Boolean(geminiProvider?.available);

  // Active training job indicator
  const activeJob = jobs.data?.find((j) => j.kind === "train" && isActiveJob(j));
  // The LLM arms are evaluated, never trained, so their "run" is a compare job.
  const activeCompare = jobs.data?.find((j) => j.kind === "compare" && isActiveJob(j));

  // --- Common Settings ---
  const [network, setNetwork] = useState("sf_mission_2x2");
  // Coverage, not one setting: every selected level is drawn by a training episode, so the
  // policy learns the whole range instead of a single congestion regime.
  const [demandLevels, setDemandLevels] = useState<string[]>([...ALL_DEMAND_LEVELS]);
  const [modelCustomName, setModelCustomName] = useState("Kemetra-SF-Mission-Supervisor-v1");
  const [runTag, setRunTag] = useState("exp_sf_mission_rush");
  const [selectedSeeds, setSelectedSeeds] = useState<number[]>([1, 2, 3]);

  // --- Shared RL Core Parameters ---
  const [rlAlgo, setRlAlgo] = useState<"ippo" | "mappo">("mappo");
  const [rlPreset, setRlPreset] = useState("standard");
  const [timesteps, setTimesteps] = useState(100000);
  const [checkpointEvery, setCheckpointEvery] = useState(25000);
  // reward.base is the objective (envs/rewards.py); co2/ev/ped are additive weights.
  const [rewardBase, setRewardBase] = useState<"wait" | "queue" | "pressure">("wait");
  const [rewardEmergency, setRewardEmergency] = useState(2.0);
  const [minGreen, setMinGreen] = useState(10);
  const [maxGreen, setMaxGreen] = useState(60);

  // --- Hybrid-Specific State ---
  const [hybridSubTab, setHybridSubTab] = useState<"orchestrator" | "rl_core">("orchestrator");
  const [hybridCoupling, setHybridCoupling] = useState<"supervisory" | "gating" | "greenwave">(
    "supervisory"
  );
  const [hybridLlmProvider, setHybridLlmProvider] = useState<"gemini" | "groq">("gemini");
  const [hybridLlmModel, setHybridLlmModel] = useState("gemini-2.5-flash");
  const [hybridUpdateInterval, setHybridUpdateInterval] = useState(30);
  const [hybridBasePolicy, setHybridBasePolicy] = useState("pretrained_best");
  const [hybridFallback, setHybridFallback] = useState(true);
  const [hybridCoT, setHybridCoT] = useState(true);
  const [hybridIncidentOverride, setHybridIncidentOverride] = useState(true);

  // --- Option 3: Full LLM State ---
  const [llmProviderChoice, setLlmProviderChoice] = useState<"gemini" | "groq">("gemini");
  const [llmModel, setLlmModel] = useState("gemini-2.5-flash");
  const [llmTemperature, setLlmTemperature] = useState(0.1);
  const [llmDecisionCycle, setLlmDecisionCycle] = useState(10);
  const [llmPersona, setLlmPersona] = useState("arterial_throughput");
  const [llmExplainability, setLlmExplainability] = useState(true);
  const [llmSafetyGuardrails, setLlmSafetyGuardrails] = useState(true);
  const [llmSystemPrompt, setLlmSystemPrompt] = useState(
    "You are KEMETRA's urban traffic signal coordinator. Analyze lane queues, approach speeds, and incident telemetry. Optimize for corridor throughput while strictly adhering to safety clearances."
  );

  // Sync default models when provider changes
  useEffect(() => {
    if (hybridLlmProvider === "gemini") {
      setHybridLlmModel("gemini-2.5-flash");
    } else {
      setHybridLlmModel("qwen/qwen3.8-27b");
    }
  }, [hybridLlmProvider]);

  useEffect(() => {
    if (llmProviderChoice === "gemini") {
      setLlmModel("gemini-2.5-flash");
    } else {
      setLlmModel("qwen/qwen3.8-27b");
    }
  }, [llmProviderChoice]);

  // Toggle seed selection
  const toggleSeed = (seed: number) => {
    setSelectedSeeds((prev) => {
      if (prev.includes(seed)) {
        if (prev.length === 1) return prev;
        return prev.filter((s) => s !== seed);
      }
      return [...prev, seed].sort((a, b) => a - b);
    });
  };

  const selectSeedPreset = (mode: "single" | "trio" | "five" | "all") => {
    if (mode === "single") setSelectedSeeds([1]);
    else if (mode === "trio") setSelectedSeeds([1, 2, 3]);
    else if (mode === "five") setSelectedSeeds([1, 2, 3, 7, 42]);
    else if (mode === "all") setSelectedSeeds([...AVAILABLE_SEEDS]);
  };

  const toggleDemandLevel = (level: string) => {
    setDemandLevels((prev) => {
      if (!prev.includes(level)) return [...prev, level];
      if (prev.length === 1) return prev; // never send an empty coverage
      return prev.filter((l) => l !== level);
    });
  };

  const handleLlmCompare = () => {
    // llm = single-call baseline, llm_team = Operator/Emergency/Pedestrian team. Both are
    // runtime controllers, so a paired quick compare is the honest run - not training.
    startCompare.mutate({
      network,
      scenario: "normal",
      demand: demandLevels.includes("medium") ? "medium" : demandLevels[0],
      seeds: selectedSeeds,
      methods: ["llm", "llm_team"],
      quick: true,
      // The panel's conditioning travels with the job; the backend applies it to the
      // llm_team arm and leaves every other controller on its config-file defaults.
      llm_settings: {
        persona: llmPersona,
        system_prompt: llmSystemPrompt,
        temperature: llmTemperature,
        cadence_s: llmDecisionCycle,
        safety_guardrails: llmSafetyGuardrails,
        explainability: llmExplainability,
      },
    });
  };

  // Network list from catalog fallback
  const networkOptions =
    catalog.data?.networks && catalog.data.networks.length > 0
      ? catalog.data.networks
      : [
          { network: "sf_mission_2x2", name: "SF Mission 2×2 Corridor" },
          { network: "sf_mission_3x3", name: "SF Mission 3×3 Grid" },
        ];

  // Validation: Check if the required API key for the chosen LLM is ready
  const isHybridKeyReady = hybridLlmProvider === "gemini" ? geminiReady : groqReady;
  // Mock and replay backends need no key, so requiring one would block a free run.
  const isFullLlmKeyReady =
    Boolean(providersData?.keyless) ||
    (llmProviderChoice === "gemini" ? geminiReady : groqReady);

  const handleLaunch = () => {
    // Only the RL card trains a policy: "hybrid" has no recipe file and "llm" is a runtime
    // controller, so POST /api/train refuses both. Their launch buttons are disabled.
    if (selected !== "rl") return;
    // Send only keys cotraffic.recipes.normalize_recipe accepts. An unknown reward key
    // (e.g. "delay") makes the backend reject the job before it starts.
    startTraining.mutate({
      network,
      seeds: selectedSeeds,
      timesteps,
      recipe_id: "generalist",
      overrides: {
        ...(modelCustomName.trim() ? { label: modelCustomName.trim() } : {}),
        training: {
          demand_levels: [...demandLevels].sort(),
          scenarios: TRAINING_SCENARIOS,
          checkpoint_every: checkpointEvery,
        },
        reward: { base: rewardBase, ev: rewardEmergency },
        runtime: { shield: { min_green: minGreen, max_green: maxGreen } },
      },
    });
  };

  return (
    <div className="flex flex-col gap-6 w-full pb-16 pt-2 px-4">
      {/* Header section */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-border/70 pb-4">
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="h-2.5 w-2.5 rounded-full bg-accent animate-pulse" />
            <h1 className="text-xl sm:text-2xl font-semibold tracking-tight text-text">
              Training & Model Orchestration
            </h1>
          </div>
          <p className="text-xs sm:text-sm text-text-2">
            Configure reinforcement learning workloads, hybrid supervisors, or direct LLM signal control.
          </p>
        </div>

        {/* Global Network & Demand Toolbar */}
        <div className="flex flex-wrap items-center gap-2.5 bg-surface-2 p-1.5 rounded-lg border border-border">
          <div className="flex items-center gap-1.5 px-2">
            <span className="text-[11px] font-medium text-muted uppercase tracking-wider">Network:</span>
            <SelectControl
              ariaLabel="Network"
              value={network}
              options={networkOptions.map((net) => ({
                value: net.network,
                label: "name" in net ? net.name : f.networkName(net.network),
              }))}
              onChange={setNetwork}
              className="text-xs font-medium"
              style={{ minWidth: 180 }}
            />
          </div>

          <div className="h-4 w-px bg-border" />

          <div className="flex items-center gap-1.5 px-2">
            <span className="text-[11px] font-medium text-muted uppercase tracking-wider">Demand:</span>
            <div className="flex items-center gap-1" role="group" aria-label="Training demand levels">
              {DEMAND_LEVELS.map((level) => {
                const active = demandLevels.includes(level.value);
                return (
                  <button
                    key={level.value}
                    type="button"
                    aria-pressed={active}
                    title={`${level.label}: ${level.hint}`}
                    onClick={() => toggleDemandLevel(level.value)}
                    className={`px-2 py-1 rounded-md border text-[11px] font-medium transition-colors ${
                      active
                        ? "border-accent bg-accent/15 text-accent"
                        : "border-border bg-surface text-muted hover:text-text"
                    }`}
                  >
                    {level.label}
                  </button>
                );
              })}
            </div>
            <span className="text-[10px] font-mono text-muted">
              {demandLevels.length}/{ALL_DEMAND_LEVELS.length}
            </span>
          </div>
        </div>
      </div>

      {/* 3 Choice Cards Layout with Expand / Blur effect */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 items-stretch transition-all duration-300">
        {ARCHETYPES.map((arch) => {
          const isSelected = selected === arch.id;
          const isDimmed = selected !== null && !isSelected;
          const Icon = arch.icon;

          return (
            <div
              key={arch.id}
              role="button"
              tabIndex={0}
              onClick={() => setSelected(isSelected ? null : arch.id)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  setSelected(isSelected ? null : arch.id);
                }
              }}
              className={`
                group relative flex flex-col rounded-xl border p-5 text-left cursor-pointer
                transition-all duration-300 ease-out select-none
                ${
                  isSelected
                    ? "border-accent bg-surface md:scale-[1.02] z-10 ring-2 ring-accent/40"
                    : isDimmed
                    ? "border-border/40 bg-surface-2/40 opacity-40 blur-[1px] grayscale-[50%] hover:opacity-60 hover:blur-none hover:grayscale-0"
                    : "border-border bg-surface hover:border-accent/50 hover:bg-surface-2"
                }
              `}
            >
              {/* Top Row: Icon + Badge */}
              <div className="flex items-center justify-between gap-3 mb-3">
                <div
                  className={`
                    p-2.5 rounded-lg border transition-colors
                    ${
                      isSelected
                        ? "border-accent/40 bg-accent/15 text-accent"
                        : "border-border bg-surface-2 text-text-2 group-hover:text-accent group-hover:border-accent/30"
                    }
                  `}
                >
                  <Icon className="w-5 h-5" />
                </div>
                <span
                  className={`text-[11px] px-2.5 py-0.5 rounded-full font-medium border ${arch.badgeTone}`}
                >
                  {arch.badge}
                </span>
              </div>

              {/* Title & Subtitle */}
              <div className="mb-2">
                <h3 className="text-base font-bold text-text group-hover:text-accent transition-colors">
                  {arch.title}
                </h3>
                <p className="text-[11px] font-mono text-muted tracking-tight mt-0.5">
                  {arch.subtitle}
                </p>
              </div>

              {/* Description */}
              <p className="text-xs leading-relaxed text-text-2 mb-4 flex-1">
                {arch.description}
              </p>

              {/* Highlights */}
              <div className="border-t border-border/60 pt-3 flex flex-col gap-1.5 mb-4">
                {arch.highlights.map((item, idx) => (
                  <div key={idx} className="flex items-start gap-1.5 text-[11px] text-text-2">
                    <Check
                      className={`w-3.5 h-3.5 mt-0.5 shrink-0 ${
                        isSelected ? "text-accent" : "text-muted"
                      }`}
                    />
                    <span>{item}</span>
                  </div>
                ))}
              </div>

              {/* Selection Status Button/Indicator */}
              <div className="mt-auto pt-1">
                <div
                  className={`
                    w-full py-1.5 px-3 rounded-lg text-xs font-medium flex items-center justify-center gap-1.5 transition-all
                    ${
                      isSelected
                        ? "bg-accent text-accent-ink shadow-sm font-semibold"
                        : "bg-surface-2 text-text-2 group-hover:bg-surface-3 group-hover:text-accent border border-border"
                    }
                  `}
                >
                  {isSelected ? (
                    <>
                      <span>Configuring</span>
                      <Check className="w-3.5 h-3.5" />
                    </>
                  ) : (
                    <>
                      <span>Configure</span>
                      <ChevronRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                    </>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Expanded Detailed Workspace */}
      {selected && (
        <div className="p-6 rounded-none border border-accent/40 bg-surface animate-in fade-in slide-in-from-top-2 duration-300">
          {/* Header of Workspace */}
          <div className="flex flex-wrap items-center justify-between gap-4 border-b border-border/70 pb-4 mb-6">
            <div className="flex items-center gap-3">
              <span className="p-2.5 rounded-lg bg-accent/15 text-accent border border-accent/30">
                {selected === "rl" && <Cpu className="w-6 h-6" />}
                {selected === "hybrid" && <GitFork className="w-6 h-6" />}
                {selected === "llm" && <Sparkles className="w-6 h-6" />}
              </span>
              <div>
                <h3 className="text-lg font-bold text-text">
                  {selected === "rl" && "Reinforcement Learning (PPO) Setup"}
                  {selected === "hybrid" && "Hierarchical Hybrid (RL + LLM) Setup"}
                  {selected === "llm" && "Full LLM Reasoning Agent Setup"}
                </h3>
                <p className="text-xs text-muted">
                  {selected === "rl" && "Formulate reward signals, network actor-critics, and simulation training budgets."}
                  {selected === "hybrid" && "Configure both tiers: High-level LLM supervisor coordination AND local RL policy weights."}
                  {selected === "llm" && "Tune context prompts, decision cadences, zero-shot rules, and SUMO safety enforcers."}
                </p>
              </div>
            </div>

            <button
              type="button"
              onClick={() => setSelected(null)}
              className="text-xs px-3 py-1.5 rounded-md border border-border hover:bg-surface-2 text-text-2 hover:text-text transition-colors"
            >
              Close Panel
            </button>
          </div>

          {/* User-Defined Naming Bar (Model Name & Run Name) */}
          <div className="mb-6 p-4 rounded-lg border border-border bg-surface-2/40 grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-text flex items-center gap-1.5">
                <Tag className="w-3.5 h-3.5 text-accent" /> Custom Model Name
              </label>
              <input
                type="text"
                value={modelCustomName}
                onChange={(e) => setModelCustomName(e.target.value)}
                placeholder="e.g. Bourguiba-Adaptive-PPO-v2"
                className="input-control text-xs font-medium"
              />
              <span className="text-[10px] text-muted">
                Will be registered in the Models table and checkpoint catalog.
              </span>
            </div>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-semibold text-text flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5 text-accent" /> Experiment / Run Tag
              </label>
              <input
                type="text"
                value={runTag}
                onChange={(e) => setRunTag(e.target.value)}
                placeholder="e.g. exp_peak_hours_tuning"
                className="input-control text-xs font-mono"
              />
              <span className="text-[10px] text-muted">
                Group and filter run metrics in the Runs and Analytics views.
              </span>
            </div>
          </div>

          {/* ======================= OPTION 1: RL CONFIGURATION ======================= */}
          {selected === "rl" && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Left Column: Algorithm & Reward Shaping (7 cols) */}
              <div className="lg:col-span-7 flex flex-col gap-6">
                {/* Algorithm Selection */}
                <div className="flex flex-col gap-3 p-4 rounded-lg border border-border bg-surface-2/40">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-1.5">
                      <Layers className="w-4 h-4 text-accent" /> Policy Architecture
                    </span>
                    <span className="text-[11px] text-muted font-mono">PPO (Proximal Policy Optimization)</span>
                  </div>

                  <div className="grid grid-cols-2 gap-3">
                    <label
                      className={`flex flex-col p-3 rounded-lg border cursor-pointer transition-all ${
                        rlAlgo === "mappo"
                          ? "border-accent bg-accent/10 text-text"
                          : "border-border bg-surface text-muted hover:border-border-2"
                      }`}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-text">MAPPO (Centralized Critic)</span>
                        <input
                          type="radio"
                          name="rl-algo"
                          className="radio-control"
                          checked={rlAlgo === "mappo"}
                          onChange={() => setRlAlgo("mappo")}
                        />
                      </span>
                      <span className="text-[11px] text-muted mt-1 leading-snug">
                        Shared state representation across neighboring junctions for coordinated flow.
                      </span>
                    </label>

                    <label
                      className={`flex flex-col p-3 rounded-lg border cursor-pointer transition-all ${
                        rlAlgo === "ippo"
                          ? "border-accent bg-accent/10 text-text"
                          : "border-border bg-surface text-muted hover:border-border-2"
                      }`}
                    >
                      <span className="flex items-center justify-between gap-2">
                        <span className="text-xs font-semibold text-text">IPPO (Decentralized Agents)</span>
                        <input
                          type="radio"
                          name="rl-algo"
                          className="radio-control"
                          checked={rlAlgo === "ippo"}
                          onChange={() => setRlAlgo("ippo")}
                        />
                      </span>
                      <span className="text-[11px] text-muted mt-1 leading-snug">
                        Independent local actors at each intersection observing strictly local lanes.
                      </span>
                    </label>
                  </div>
                </div>

                {/* Reward Shaping Knobs */}
                <div className="flex flex-col gap-4 p-4 rounded-lg border border-border bg-surface-2/40">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-1.5">
                      <Sliders className="w-4 h-4 text-accent" /> Reward Function Shaping
                    </span>
                    <span className="text-[11px] text-muted">SUMO TraCI Feedback Sliders</span>
                  </div>

                  <div className="flex flex-col gap-2">
                    <span className="text-xs text-text font-medium">Reward Objective</span>
                    <div className="grid grid-cols-3 gap-2">
                      {(
                        [
                          { id: "wait", name: "Delay", desc: "Minimise waiting time." },
                          { id: "queue", name: "Queue", desc: "Minimise halting vehicles." },
                          { id: "pressure", name: "Pressure", desc: "Balance inflow against exit capacity." },
                        ] as const
                      ).map((term) => (
                        <button
                          key={term.id}
                          type="button"
                          aria-pressed={rewardBase === term.id}
                          onClick={() => setRewardBase(term.id)}
                          className={`px-2 py-1.5 rounded-lg border text-start transition-colors ${
                            rewardBase === term.id
                              ? "border-accent bg-accent/10 text-text"
                              : "border-border bg-surface text-muted hover:text-text"
                          }`}
                        >
                          <span className="block text-xs font-semibold">{term.name}</span>
                          <span className="block text-[10px] leading-snug">{term.desc}</span>
                        </button>
                      ))}
                    </div>
                    <span className="text-[10px] text-muted">
                      Training covers every selected demand level and all five event scenarios
                      (normal, emergency, pedestrians, buses, incident).
                    </span>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="text-text font-medium">Emergency Vehicle Wait Weight</span>
                      <span className="font-mono text-accent">{rewardEmergency.toFixed(1)}</span>
                    </div>
                    <RangeInput
                      ariaLabel="Emergency vehicle wait weight"
                      min={0}
                      max={5.0}
                      step={0.5}
                      value={rewardEmergency}
                      onChange={setRewardEmergency}
                    />
                    <span className="text-[10px] text-muted">Weight of the EV waiting term (reward.ev).</span>
                  </div>
                </div>
              </div>

              {/* Right Column: Training Budget, Selectable Seeds & Launch (5 cols) */}
              <div className="lg:col-span-5 flex flex-col gap-6">
                <div className="flex flex-col gap-3 p-4 rounded-lg border border-border bg-surface-2/40">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-1.5">
                      <Dna className="w-4 h-4 text-accent" /> Simulation Seeds Selection
                    </span>
                    <span className="text-[11px] font-mono text-accent font-semibold">
                      {selectedSeeds.length} Selected
                    </span>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    {AVAILABLE_SEEDS.map((seed) => {
                      const isChosen = selectedSeeds.includes(seed);
                      return (
                        <button
                          key={seed}
                          type="button"
                          onClick={() => toggleSeed(seed)}
                          className={`px-3 py-1.5 rounded-lg border text-xs font-mono font-medium transition-all flex items-center gap-1.5 ${
                            isChosen
                              ? "border-accent bg-accent text-accent-ink shadow-sm"
                              : "border-border bg-surface text-muted hover:border-border-2 hover:text-text"
                          }`}
                        >
                          <span>Seed {seed}</span>
                          {isChosen && <Check className="w-3 h-3 stroke-[3]" />}
                        </button>
                      );
                    })}
                  </div>

                  <div className="flex items-center gap-1.5 pt-2 border-t border-border/60 text-[11px]">
                    <span className="text-muted">Quick presets:</span>
                    <button
                      type="button"
                      onClick={() => selectSeedPreset("single")}
                      className="text-text hover:text-accent font-medium underline px-1"
                    >
                      Single (1)
                    </button>
                    <span>·</span>
                    <button
                      type="button"
                      onClick={() => selectSeedPreset("trio")}
                      className="text-text hover:text-accent font-medium underline px-1"
                    >
                      Trio (3)
                    </button>
                    <span>·</span>
                    <button
                      type="button"
                      onClick={() => selectSeedPreset("five")}
                      className="text-text hover:text-accent font-medium underline px-1"
                    >
                      Five (5)
                    </button>
                    <span>·</span>
                    <button
                      type="button"
                      onClick={() => selectSeedPreset("all")}
                      className="text-text hover:text-accent font-medium underline px-1"
                    >
                      All
                    </button>
                  </div>
                </div>

                <div className="flex flex-col gap-4 p-4 rounded-lg border border-border bg-surface-2/40">
                  <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-1.5">
                    <Activity className="w-4 h-4 text-accent" /> Compute & Simulation Budget
                  </span>

                  <div className="grid grid-cols-3 gap-2">
                    {[
                      { id: "pilot", label: "Pilot", steps: 25000 },
                      { id: "standard", label: "Standard", steps: 100000 },
                      { id: "full", label: "Full Conv.", steps: 500000 },
                    ].map((p) => (
                      <button
                        key={p.id}
                        type="button"
                        onClick={() => {
                          setRlPreset(p.id);
                          setTimesteps(p.steps);
                        }}
                        className={`py-1.5 px-2 rounded border text-xs font-medium transition-all ${
                          rlPreset === p.id
                            ? "border-accent bg-accent/15 text-accent"
                            : "border-border bg-surface text-muted hover:text-text"
                        }`}
                      >
                        {p.label}
                      </button>
                    ))}
                  </div>

                  <div className="flex flex-col gap-1">
                    <span className="text-xs text-muted">Total Steps:</span>
                    <NumberField
                      ariaLabel="Total training steps"
                      value={timesteps}
                      onChange={setTimesteps}
                      min={1000}
                      step={1000}
                    />
                  </div>

                  <div className="flex flex-col gap-1">
                    <span className="text-xs text-muted">Checkpoint Every (steps):</span>
                    <NumberField
                      ariaLabel="Checkpoint interval in steps"
                      value={checkpointEvery}
                      onChange={setCheckpointEvery}
                      min={1000}
                      step={1000}
                    />
                  </div>
                </div>

                <div className="flex flex-col gap-3 p-4 rounded-lg border border-border bg-surface-2/40">
                  <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-accent" /> Actuation Safety Boundaries
                  </span>

                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div>
                      <span className="text-muted block mb-1">Min Green Time</span>
                      <div className="flex items-center gap-1.5">
                        <NumberField
                          ariaLabel="Minimum green time in seconds"
                          value={minGreen}
                          onChange={setMinGreen}
                          min={1}
                          max={120}
                        />
                        <span className="text-muted">sec</span>
                      </div>
                    </div>

                    <div>
                      <span className="text-muted block mb-1">Max Green Time</span>
                      <div className="flex items-center gap-1.5">
                        <NumberField
                          ariaLabel="Maximum green time in seconds"
                          value={maxGreen}
                          onChange={setMaxGreen}
                          min={1}
                          max={180}
                        />
                        <span className="text-muted">sec</span>
                      </div>
                    </div>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleLaunch}
                  disabled={startTraining.isPending || !!activeJob}
                  className="w-full py-3 px-4 rounded-xl bg-accent text-accent-ink font-semibold flex items-center justify-center gap-2 hover:brightness-105 active:scale-[0.99] transition-all shadow-md disabled:opacity-50"
                >
                  <Play className="w-4 h-4 fill-current" />
                  <span>{activeJob ? "Job in Progress..." : "Launch RL Policy Training"}</span>
                </button>
              </div>
            </div>
          )}

          {/* ======================= OPTION 2: HYBRID CONFIGURATION ======================= */}
          {selected === "hybrid" && (
            <div className="flex flex-col gap-6">
              {/* Hybrid Dual-Tier Navigation Bar */}
              <div className="flex items-center justify-between border-b border-border/80 pb-3">
                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setHybridSubTab("orchestrator")}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                      hybridSubTab === "orchestrator"
                        ? "bg-accent text-accent-ink shadow-sm"
                        : "bg-surface-2 text-text-2 hover:text-text hover:bg-surface-3"
                    }`}
                  >
                    <GitFork className="w-3.5 h-3.5" />
                    <span>Tier 1: LLM Macro Supervisor</span>
                  </button>

                  <button
                    type="button"
                    onClick={() => setHybridSubTab("rl_core")}
                    className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${
                      hybridSubTab === "rl_core"
                        ? "bg-accent text-accent-ink shadow-sm"
                        : "bg-surface-2 text-text-2 hover:text-text hover:bg-surface-3"
                    }`}
                  >
                    <Cpu className="w-3.5 h-3.5" />
                    <span>Tier 2: Micro-RL Policy & Rewards</span>
                  </button>
                </div>

                <span className="text-[11px] font-mono text-muted">
                  {hybridSubTab === "orchestrator"
                    ? "Configuring high-level supervision & arbitration"
                    : "Configuring edge intersection RL execution & reward shaping"}
                </span>
              </div>

              {/* TIER 1: LLM Macro Supervisor View */}
              {hybridSubTab === "orchestrator" && (
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                  {/* Left Column: Hierarchical Orchestration (7 cols) */}
                  <div className="lg:col-span-7 flex flex-col gap-6">
                    {/* Coupling Mode */}
                    <div className="flex flex-col gap-3 p-4 rounded-lg border border-border bg-surface-2/40">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-1.5">
                          <GitFork className="w-4 h-4 text-accent" /> Hierarchical Coupling Mode
                        </span>
                        <span className="text-[11px] text-muted">Macro vs Micro Division</span>
                      </div>

                      <div className="grid grid-cols-1 gap-2.5">
                        {[
                          {
                            id: "supervisory",
                            name: "Supervisory Dynamic Reward Reweighting",
                            desc: "LLM monitors multi-junction congestion every K seconds and dynamically updates the reward targets of the local RL policy.",
                          },
                          {
                            id: "gating",
                            name: "Gating & Incident Arbiter",
                            desc: "RL proposes high-frequency signal phase changes; LLM can veto or force green-wave overrides when regional bottlenecks appear.",
                          },
                          {
                            id: "greenwave",
                            name: "Corridor Green-Wave Arterial Offset",
                            desc: "LLM calculates progression speed bands and offsets across the corridor, leaving local queue optimization to RL.",
                          },
                        ].map((mode) => (
                          <label
                            key={mode.id}
                            className={`p-3 rounded-lg border cursor-pointer transition-all flex flex-col ${
                              hybridCoupling === mode.id
                                ? "border-accent bg-accent/10"
                                : "border-border bg-surface hover:border-border-2"
                            }`}
                          >
                            <span className="flex items-center justify-between gap-2">
                              <span className="text-xs font-semibold text-text">{mode.name}</span>
                              <input
                                type="radio"
                                name="hybrid-coupling"
                                className="radio-control"
                                checked={hybridCoupling === mode.id}
                                onChange={() => setHybridCoupling(mode.id as any)}
                              />
                            </span>
                            <span className="text-[11px] text-muted mt-1 leading-snug">{mode.desc}</span>
                          </label>
                        ))}
                      </div>
                    </div>

                    {/* Macro Cadence & Context */}
                    <div className="flex flex-col gap-4 p-4 rounded-lg border border-border bg-surface-2/40">
                      <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-1.5">
                        <Activity className="w-4 h-4 text-accent" /> Macro Supervisor Decision Cadence
                      </span>

                      <div className="flex flex-col gap-1.5">
                        <div className="flex justify-between text-xs">
                          <span className="text-text font-medium">LLM Reasoning Interval</span>
                          <span className="font-mono text-accent">Every {hybridUpdateInterval} seconds</span>
                        </div>
                        <RangeInput
                          ariaLabel="LLM reasoning interval in seconds"
                          min={10}
                          max={120}
                          step={5}
                          value={hybridUpdateInterval}
                          onChange={setHybridUpdateInterval}
                        />
                        <div className="flex justify-between text-[10px] text-muted">
                          <span>10s (High reactivity)</span>
                          <span>30s (Recommended)</span>
                          <span>120s (Corridor macro shifts)</span>
                        </div>
                      </div>

                      <div className="border-t border-border/60 pt-3 flex flex-col gap-2">
                        <label className="flex items-center gap-2 cursor-pointer text-xs text-text">
                          <input
                            type="checkbox"
                            checked={hybridIncidentOverride}
                            onChange={(e) => setHybridIncidentOverride(e.target.checked)}
                            className="check-control"
                          />
                          <span>Trigger instant LLM re-evaluation upon Emergency / Stalled vehicle detection</span>
                        </label>

                        <label className="flex items-center gap-2 cursor-pointer text-xs text-text">
                          <input
                            type="checkbox"
                            checked={hybridCoT}
                            onChange={(e) => setHybridCoT(e.target.checked)}
                            className="check-control"
                          />
                          <span>Enable Chain-of-Thought corridor diagnostics in telemetry log</span>
                        </label>
                      </div>
                    </div>
                  </div>

                  {/* Right Column: LLM Engine with API Readiness Check & Launch (5 cols) */}
                  <div className="lg:col-span-5 flex flex-col gap-6">
                    {/* LLM Engine Selection */}
                    <div className="flex flex-col gap-4 p-4 rounded-lg border border-border bg-surface-2/40">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-1.5">
                          <Sparkles className="w-4 h-4 text-accent" /> Supervisor LLM Engine
                        </span>
                        {/* API Key Status Badge */}
                        <div
                          className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium border ${
                            isHybridKeyReady
                              ? "bg-accent/15 border-accent/40 text-accent"
                              : "bg-jam-soft border-jam/40 text-jam"
                          }`}
                        >
                          {isHybridKeyReady ? (
                            <>
                              <CheckCircle2 className="w-3 h-3 text-accent" />
                              <span>API Key Active</span>
                            </>
                          ) : (
                            <>
                              <XCircle className="w-3 h-3 text-jam" />
                              <span>Missing API Key</span>
                            </>
                          )}
                        </div>
                      </div>

                      {/* Provider Selector Tabs */}
                      <div className="grid grid-cols-2 gap-2">
                        <button
                          type="button"
                          onClick={() => setHybridLlmProvider("gemini")}
                          className={`p-2.5 rounded-lg border text-left transition-all flex flex-col ${
                            hybridLlmProvider === "gemini"
                              ? "border-accent bg-accent/10"
                              : "border-border bg-surface hover:border-border-2"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <span
                                className="radio-mark"
                                data-checked={hybridLlmProvider === "gemini"}
                                aria-hidden="true"
                              />
                              <span className="text-xs font-bold text-text">Google Gemini</span>
                            </div>
                            <span
                              className={`h-2 w-2 rounded-full ${
                                geminiReady ? "bg-accent" : "bg-jam"
                              }`}
                              title={geminiReady ? "GEMINI_API_KEY Configured" : "GEMINI_API_KEY Not Found"}
                            />
                          </div>
                          <span className="text-[10px] text-muted mt-0.5 pl-6">Google AI Studio</span>
                        </button>

                        <button
                          type="button"
                          onClick={() => setHybridLlmProvider("groq")}
                          className={`p-2.5 rounded-lg border text-left transition-all flex flex-col ${
                            hybridLlmProvider === "groq"
                              ? "border-accent bg-accent/10"
                              : "border-border bg-surface hover:border-border-2"
                          }`}
                        >
                          <div className="flex items-center justify-between gap-2">
                            <div className="flex items-center gap-2">
                              <span
                                className="radio-mark"
                                data-checked={hybridLlmProvider === "groq"}
                                aria-hidden="true"
                              />
                              <span className="text-xs font-bold text-text">Groq Cloud</span>
                            </div>
                            <span
                              className={`h-2 w-2 rounded-full ${
                                groqReady ? "bg-accent" : "bg-jam"
                              }`}
                              title={groqReady ? "GROQ_API_KEY Configured" : "GROQ_API_KEY Not Found"}
                            />
                          </div>
                          <span className="text-[10px] text-muted mt-0.5 pl-6">LPU High-Speed Inference</span>
                        </button>
                      </div>

                      {/* Model Selector based on provider */}
                      <div className="flex flex-col gap-1">
                        <span className="text-xs text-muted">
                          {hybridLlmProvider === "gemini" ? "Gemini Model:" : "Groq Model:"}
                        </span>
                        <SelectControl
                          ariaLabel="Supervisor model"
                          value={hybridLlmModel}
                          options={hybridLlmProvider === "gemini" ? GEMINI_MODELS : GROQ_MODELS}
                          onChange={setHybridLlmModel}
                          className="text-xs font-mono"
                        />
                      </div>

                      {/* Missing API Key Warning Box */}
                      {!isHybridKeyReady && (
                        <div className="p-2.5 rounded-lg border border-jam/40 bg-jam-soft/60 flex items-start gap-2 text-xs text-jam">
                          <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                          <div className="leading-snug">
                            <span className="font-semibold block">
                              {hybridLlmProvider === "gemini" ? "GEMINI_API_KEY" : "GROQ_API_KEY"} is not configured
                            </span>
                            Add it to your <code className="font-mono text-[11px]">.env</code> file or Settings to enable live inference.
                          </div>
                        </div>
                      )}

                      <div className="flex flex-col gap-1">
                        <span className="text-xs text-muted">Base Micro-RL Policy Checkpoint:</span>
                        <SelectControl
                          ariaLabel="Base micro-RL policy checkpoint"
                          value={hybridBasePolicy}
                          options={BASE_POLICIES}
                          onChange={setHybridBasePolicy}
                          className="text-xs font-mono"
                        />
                      </div>
                    </div>

                    {/* Resilient Fallback Safeguard */}
                    <div className="flex flex-col gap-3 p-4 rounded-lg border border-border bg-surface-2/40">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-1.5">
                          <ShieldCheck className="w-4 h-4 text-accent" /> High-Availability Fail-Safe
                        </span>
                        <span className="text-[10px] text-accent font-mono font-medium">Zero-Drop SLA</span>
                      </div>

                      <label className="flex items-start gap-2 cursor-pointer text-xs text-text">
                        <input
                          type="checkbox"
                          checked={hybridFallback}
                          onChange={(e) => setHybridFallback(e.target.checked)}
                          className="check-control mt-0.5"
                        />
                        <span className="leading-snug">
                          Automatic Fallback: If LLM API exceeds 1500ms latency or errors, smoothly switch
                          actuation to the pure local RL policy without disrupting green splits.
                        </span>
                      </label>
                    </div>

                    {/* Launch Action */}
                    <button
                      type="button"
                      onClick={handleLaunch}
                      disabled
                      className="w-full py-3 px-4 rounded-xl bg-accent text-accent-ink font-semibold flex items-center justify-center gap-2 hover:brightness-105 active:scale-[0.99] transition-all shadow-md disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
                    >
                      <Play className="w-4 h-4 fill-current" />
                      <span>
                        {activeJob
                          ? "Job in Progress..."
                          : !isHybridKeyReady
                          ? "API Key Required to Launch"
                          : "Hybrid orchestration is not implemented yet"}
                      </span>
                    </button>
                  </div>
                </div>
              )}

              {/* TIER 2: Micro-RL Policy & Reward Shaping View */}
              {hybridSubTab === "rl_core" && (
                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 animate-in fade-in duration-200">
                  <div className="lg:col-span-7 flex flex-col gap-6">
                    <div className="flex flex-col gap-3 p-4 rounded-lg border border-border bg-surface-2/40">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-1.5">
                          <Layers className="w-4 h-4 text-accent" /> Local Edge RL Architecture
                        </span>
                        <span className="text-[11px] text-muted font-mono">Microsecond Phase Actuation</span>
                      </div>

                      <div className="grid grid-cols-2 gap-3">
                        <label
                          className={`flex flex-col p-3 rounded-lg border cursor-pointer transition-all ${
                            rlAlgo === "mappo"
                              ? "border-accent bg-accent/10 text-text"
                              : "border-border bg-surface text-muted hover:border-border-2"
                          }`}
                        >
                          <span className="flex items-center justify-between gap-2">
                            <span className="text-xs font-semibold text-text">MAPPO (Centralized Critic)</span>
                            <input
                              type="radio"
                              name="rl-algo-tier2"
                              className="radio-control"
                              checked={rlAlgo === "mappo"}
                              onChange={() => setRlAlgo("mappo")}
                            />
                          </span>
                          <span className="text-[11px] text-muted mt-1 leading-snug">
                            Shared critic with neighborhood coordination under LLM corridor guidance.
                          </span>
                        </label>

                        <label
                          className={`flex flex-col p-3 rounded-lg border cursor-pointer transition-all ${
                            rlAlgo === "ippo"
                              ? "border-accent bg-accent/10 text-text"
                              : "border-border bg-surface text-muted hover:border-border-2"
                          }`}
                        >
                          <span className="flex items-center justify-between gap-2">
                            <span className="text-xs font-semibold text-text">IPPO (Decentralized Local Actors)</span>
                            <input
                              type="radio"
                              name="rl-algo-tier2"
                              className="radio-control"
                              checked={rlAlgo === "ippo"}
                              onChange={() => setRlAlgo("ippo")}
                            />
                          </span>
                          <span className="text-[11px] text-muted mt-1 leading-snug">
                            Independent local actors per intersection receiving LLM target objectives.
                          </span>
                        </label>
                      </div>
                    </div>

                    <div className="flex flex-col gap-4 p-4 rounded-lg border border-border bg-surface-2/40">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-1.5">
                          <Sliders className="w-4 h-4 text-accent" /> Baseline RL Reward Functions
                        </span>
                        <span className="text-[11px] text-muted">Dynamically reweighted by LLM</span>
                      </div>

                      <div className="flex flex-col gap-1.5">
                        <span className="text-xs text-text font-medium">
                          Reward Objective (shared with the RL tier)
                        </span>
                        <span className="text-[11px] text-muted leading-snug">
                          Base term: <code className="text-text-2">{rewardBase}</code> · EV wait weight:{" "}
                          <code className="text-text-2">{rewardEmergency.toFixed(1)}</code>. Both are configured in
                          the RL panel and sent with every training job.
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="lg:col-span-5 flex flex-col gap-6">
                    <div className="flex flex-col gap-3 p-4 rounded-lg border border-border bg-surface-2/40">
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-1.5">
                          <Dna className="w-4 h-4 text-accent" /> Evaluation Simulation Seeds
                        </span>
                        <span className="text-[11px] font-mono text-accent font-semibold">
                          {selectedSeeds.length} Selected
                        </span>
                      </div>

                      <div className="flex flex-wrap gap-2">
                        {AVAILABLE_SEEDS.map((seed) => {
                          const isChosen = selectedSeeds.includes(seed);
                          return (
                            <button
                              key={seed}
                              type="button"
                              onClick={() => toggleSeed(seed)}
                              className={`px-3 py-1.5 rounded-lg border text-xs font-mono font-medium transition-all flex items-center gap-1.5 ${
                                isChosen
                                  ? "border-accent bg-accent text-accent-ink shadow-sm"
                                  : "border-border bg-surface text-muted hover:border-border-2 hover:text-text"
                              }`}
                            >
                              <span>Seed {seed}</span>
                              {isChosen && <Check className="w-3 h-3 stroke-[3]" />}
                            </button>
                          );
                        })}
                      </div>
                    </div>

                    <div className="flex flex-col gap-3 p-4 rounded-lg border border-border bg-surface-2/40">
                      <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-1.5">
                        <ShieldCheck className="w-4 h-4 text-accent" /> Local Edge Green Bounds
                      </span>

                      <div className="grid grid-cols-2 gap-3 text-xs">
                        <div>
                          <span className="text-muted block mb-1">Min Green Time</span>
                          <div className="flex items-center gap-1.5">
                            <NumberField
                              ariaLabel="Minimum green time in seconds"
                              value={minGreen}
                              onChange={setMinGreen}
                              min={1}
                              max={120}
                            />
                            <span className="text-muted">sec</span>
                          </div>
                        </div>

                        <div>
                          <span className="text-muted block mb-1">Max Green Time</span>
                          <div className="flex items-center gap-1.5">
                            <NumberField
                              ariaLabel="Maximum green time in seconds"
                              value={maxGreen}
                              onChange={setMaxGreen}
                              min={1}
                              max={180}
                            />
                            <span className="text-muted">sec</span>
                          </div>
                        </div>
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={handleLaunch}
                      disabled
                      className="w-full py-3 px-4 rounded-xl bg-accent text-accent-ink font-semibold flex items-center justify-center gap-2 hover:brightness-105 active:scale-[0.99] transition-all shadow-md disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
                    >
                      <Play className="w-4 h-4 fill-current" />
                      <span>
                        {activeJob
                          ? "Job in Progress..."
                          : !isHybridKeyReady
                          ? "API Key Required to Launch"
                          : "Hybrid orchestration is not implemented yet"}
                      </span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ======================= OPTION 3: FULL LLM CONFIGURATION ======================= */}
          {selected === "llm" && (
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
              {/* Left Column: Model Settings, Persona & Prompting (7 cols) */}
              <div className="lg:col-span-7 flex flex-col gap-6">
                {/* Persona & Behavioral Strategy */}
                <div className="flex flex-col gap-3 p-4 rounded-lg border border-border bg-surface-2/40">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-1.5">
                      <Sparkles className="w-4 h-4 text-accent" /> Control Persona & Objective
                    </span>
                    <span className="text-[11px] text-muted">Behavioral Prioritization</span>
                  </div>

                  <div className="grid grid-cols-2 gap-2.5">
                    {[
                      {
                        id: "arterial_throughput",
                        name: "Arterial Corridor Focus",
                        desc: "Maximizes main avenue vehicle progression; holds side streets for platoons.",
                      },
                      {
                        id: "equi_delay",
                        name: "Fairness & Equi-Delay",
                        desc: "Minimizes maximum waiting time variance across all approaches.",
                      },
                      {
                        id: "transit_pedestrian",
                        name: "Transit & Pedestrian First",
                        desc: "Prioritizes bus priority corridors and crosswalk clearance windows.",
                      },
                      {
                        id: "emergency_resilience",
                        name: "Emergency Incident Corridor",
                        desc: "Aggressive clearance of buffer zones ahead of first responders.",
                      },
                    ].map((persona) => (
                      <label
                        key={persona.id}
                        className={`p-3 rounded-lg border cursor-pointer transition-all flex flex-col ${
                          llmPersona === persona.id
                            ? "border-accent bg-accent/10"
                            : "border-border bg-surface hover:border-border-2"
                        }`}
                      >
                        <span className="flex items-center justify-between gap-2">
                          <span className="text-xs font-semibold text-text">{persona.name}</span>
                          <input
                            type="radio"
                            name="llm-persona"
                            className="radio-control"
                            checked={llmPersona === persona.id}
                            onChange={() => setLlmPersona(persona.id)}
                          />
                        </span>
                        <span className="text-[11px] text-muted mt-1 leading-snug">{persona.desc}</span>
                      </label>
                    ))}
                  </div>
                </div>

                {/* System Prompt Customizer */}
                <div className="flex flex-col gap-2 p-4 rounded-lg border border-border bg-surface-2/40">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-1.5">
                      <Terminal className="w-4 h-4 text-accent" /> System Instructions Conditioning
                    </span>
                    <button
                      type="button"
                      onClick={() =>
                        setLlmSystemPrompt(
                          "You are KEMETRA's urban traffic signal coordinator. Analyze lane queues, approach speeds, and incident telemetry. Optimize for corridor throughput while strictly adhering to safety clearances."
                        )
                      }
                      className="text-[10px] text-muted hover:text-accent flex items-center gap-1"
                    >
                      <RotateCcw className="w-3 h-3" /> Reset Default
                    </button>
                  </div>

                  <textarea
                    rows={4}
                    value={llmSystemPrompt}
                    onChange={(e) => setLlmSystemPrompt(e.target.value)}
                    className="input-control h-auto w-full py-2.5 text-xs font-mono leading-relaxed"
                  />
                  <span className="text-[10px] text-muted">
                    Variables injected at runtime: <code className="text-text-2">&#123;&#123;network&#125;&#125;</code>,{" "}
                    <code className="text-text-2">&#123;&#123;active_queues&#125;&#125;</code>,{" "}
                    <code className="text-text-2">&#123;&#123;emergency_lanes&#125;&#125;</code>.
                  </span>
                </div>
              </div>

              {/* Right Column: Reasoning Parameters, Provider Selection & Safety (5 cols) */}
              <div className="lg:col-span-5 flex flex-col gap-6">
                {/* Model Engine & Temperature */}
                <div className="flex flex-col gap-4 p-4 rounded-lg border border-border bg-surface-2/40">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-1.5">
                      <Cpu className="w-4 h-4 text-accent" /> Reasoning Engine & Studio
                    </span>
                    {/* API Key Status Badge */}
                    <div
                      className={`flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-medium border ${
                        isFullLlmKeyReady
                          ? "bg-accent/15 border-accent/40 text-accent"
                          : "bg-jam-soft border-jam/40 text-jam"
                      }`}
                    >
                      {isFullLlmKeyReady ? (
                        <>
                          <CheckCircle2 className="w-3 h-3 text-accent" />
                          <span>API Ready</span>
                        </>
                      ) : (
                        <>
                          <XCircle className="w-3 h-3 text-jam" />
                          <span>Missing Key</span>
                        </>
                      )}
                    </div>
                  </div>

                  {/* Provider Selection Tabs */}
                  <div className="grid grid-cols-2 gap-2">
                    <button
                      type="button"
                      onClick={() => setLlmProviderChoice("gemini")}
                      className={`p-2.5 rounded-lg border text-left transition-all flex flex-col ${
                        llmProviderChoice === "gemini"
                          ? "border-accent bg-accent/10"
                          : "border-border bg-surface hover:border-border-2"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span
                            className="radio-mark"
                            data-checked={llmProviderChoice === "gemini"}
                            aria-hidden="true"
                          />
                          <span className="text-xs font-bold text-text">Google Gemini</span>
                        </div>
                        <span
                          className={`h-2 w-2 rounded-full ${
                            geminiReady ? "bg-accent" : "bg-jam"
                          }`}
                          title={geminiReady ? "GEMINI_API_KEY Configured" : "GEMINI_API_KEY Missing"}
                        />
                      </div>
                      <span className="text-[10px] text-muted mt-0.5 pl-6">AI Studio Direct API</span>
                    </button>

                    <button
                      type="button"
                      onClick={() => setLlmProviderChoice("groq")}
                      className={`p-2.5 rounded-lg border text-left transition-all flex flex-col ${
                        llmProviderChoice === "groq"
                          ? "border-accent bg-accent/10"
                          : "border-border bg-surface hover:border-border-2"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <div className="flex items-center gap-2">
                          <span
                            className="radio-mark"
                            data-checked={llmProviderChoice === "groq"}
                            aria-hidden="true"
                          />
                          <span className="text-xs font-bold text-text">Groq Cloud</span>
                        </div>
                        <span
                          className={`h-2 w-2 rounded-full ${
                            groqReady ? "bg-accent" : "bg-jam"
                          }`}
                          title={groqReady ? "GROQ_API_KEY Configured" : "GROQ_API_KEY Missing"}
                        />
                      </div>
                      <span className="text-[10px] text-muted mt-0.5 pl-6">High-Speed LPU Engine</span>
                    </button>
                  </div>

                  <p className="text-[10px] text-muted leading-snug">
                    The multi-role team (<code className="text-text-2">llm_team</code>) runs on this
                    provider too. OpenCode Go is enabled by{" "}
                    <code className="text-text-2">COTRAFFIC_LLM_API_KEY</code>; the mock and replay
                    backends need no key at all.
                  </p>

                  {/* Model Picker */}
                  <div className="flex flex-col gap-1">
                    <span className="text-xs text-muted">
                      {llmProviderChoice === "gemini" ? "Gemini Model:" : "Groq Model:"}
                    </span>
                    <SelectControl
                      ariaLabel="Reasoning model"
                      value={llmModel}
                      options={llmProviderChoice === "gemini" ? GEMINI_MODELS : GROQ_MODELS}
                      onChange={setLlmModel}
                      className="text-xs font-mono"
                    />
                  </div>

                  {/* Missing API Key Warning Box */}
                  {!isFullLlmKeyReady && (
                    <div className="p-2.5 rounded-lg border border-jam/40 bg-jam-soft/60 flex items-start gap-2 text-xs text-jam">
                      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
                      <div className="leading-snug">
                        <span className="font-semibold block">
                          {llmProviderChoice === "gemini" ? "GEMINI_API_KEY" : "GROQ_API_KEY"} is not configured
                        </span>
                        Add the key to your backend environment or Settings to execute live inferences.
                      </div>
                    </div>
                  )}

                  <div className="flex flex-col gap-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="text-text font-medium">Temperature (Stochasticity)</span>
                      <span className="font-mono text-accent">{llmTemperature.toFixed(2)}</span>
                    </div>
                    <RangeInput
                      ariaLabel="LLM temperature"
                      min={0.0}
                      max={0.7}
                      step={0.05}
                      value={llmTemperature}
                      onChange={setLlmTemperature}
                    />
                    <div className="flex justify-between text-[10px] text-muted">
                      <span>0.0 (Deterministic)</span>
                      <span>0.1 (Recommended)</span>
                      <span>0.7 (Exploration)</span>
                    </div>
                  </div>

                  <div className="flex flex-col gap-1.5">
                    <div className="flex justify-between text-xs">
                      <span className="text-text font-medium">Decision Actuation Frequency</span>
                      <span className="font-mono text-accent">Every {llmDecisionCycle}s</span>
                    </div>
                    <RangeInput
                      ariaLabel="LLM decision actuation frequency in seconds"
                      min={5}
                      max={30}
                      step={5}
                      value={llmDecisionCycle}
                      onChange={setLlmDecisionCycle}
                    />
                  </div>
                </div>

                {/* Guardrails & TraCI Safety Checks */}
                <div className="flex flex-col gap-3 p-4 rounded-lg border border-border bg-surface-2/40">
                  <span className="text-xs font-bold uppercase tracking-wider text-text flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-accent" /> Strict Safety Enforcer
                  </span>

                  <label className="flex items-start gap-2 cursor-pointer text-xs text-text">
                    <input
                      type="checkbox"
                      checked={llmSafetyGuardrails}
                      onChange={(e) => setLlmSafetyGuardrails(e.target.checked)}
                      className="check-control mt-0.5"
                    />
                    <span className="leading-snug">
                      Hard Deterministic Bounds: Enforce minimum green (7s), yellow clearance (3s), and
                      immediate interlock against conflicting phase transitions.
                    </span>
                  </label>

                  <label className="flex items-start gap-2 cursor-pointer text-xs text-text">
                    <input
                      type="checkbox"
                      checked={llmExplainability}
                      onChange={(e) => setLlmExplainability(e.target.checked)}
                      className="check-control mt-0.5"
                    />
                    <span className="leading-snug">
                      Stream Natural Language Reasoning Rationale to Operator Console & Benchmark Log.
                    </span>
                  </label>
                </div>

                {/* Launch Action: evaluate, never train */}
                <button
                  type="button"
                  onClick={handleLlmCompare}
                  disabled={startCompare.isPending || !!activeCompare || !isFullLlmKeyReady}
                  className="w-full py-3 px-4 rounded-xl bg-accent text-accent-ink font-semibold flex items-center justify-center gap-2 hover:brightness-105 active:scale-[0.99] transition-all shadow-md disabled:opacity-50 cursor-pointer disabled:cursor-not-allowed"
                >
                  <Play className="w-4 h-4 fill-current" />
                  <span>
                    {activeCompare
                      ? "Comparison running..."
                      : !isFullLlmKeyReady
                      ? "API Key Required to Launch"
                      : "Run LLM vs LLM-team comparison"}
                  </span>
                </button>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
