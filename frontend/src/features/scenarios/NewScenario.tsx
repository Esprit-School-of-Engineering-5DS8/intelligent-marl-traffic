import { zodResolver } from "@hookform/resolvers/zod";
import {
  Building2,
  Bus,
  Footprints,
  Grid2x2,
  Grid3x3,
  Landmark,
  MapPin,
  MessagesSquare,
  Play,
  Siren,
  Sparkles,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { useSettings } from "@/features/settings/store";
import { useCreateRun } from "@/shared/api/backend";
import { useFormat, useTx } from "@/shared/domain/format";
import { methodColor } from "@/shared/domain/methods";
import { cn } from "@/shared/lib/cn";
import { DEMANDS, ScenarioRequest, type Meta } from "@/shared/schemas";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { SelectField } from "@/shared/ui/field";

import {
  creationOptions,
  defaultRequest,
  fitRequest,
  presets,
  type Network,
  type ScenarioEvent,
} from "./options";

const NETWORK_ICONS: Record<Network, LucideIcon> = {
  grid4x4: Grid2x2,
  grid8x8: Grid3x3,
  real_district: MapPin,
  real_district_ped: Footprints,
  paris: Landmark,
  barcelona: Building2,
};
const EVENT_ICONS: Record<ScenarioEvent, LucideIcon> = {
  emergency: Siren,
  pedestrians: Footprints,
  incident: TriangleAlert,
  buses: Bus,
};

/**
 * Builds a scenario and asks the backend to play it under two controllers, then record a
 * replay. The networks, events and controllers come from the exported catalog: a network
 * offers only the events its SUMO files can generate and the controllers whose model is
 * trained. Launching is a state change: it is confirmed first, and needs the backend.
 */
export function NewScenario({ meta }: { meta: Meta }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const live = useSettings((s) => s.dataSource) === "live";
  const create = useCreateRun();
  const [pending, setPending] = useState<ScenarioRequest | null>(null);
  const options = useMemo(() => creationOptions(meta), [meta]);

  const form = useForm<ScenarioRequest>({
    resolver: zodResolver(ScenarioRequest),
    defaultValues: defaultRequest(options),
  });
  const { register, handleSubmit, formState, setValue, getValues, control, reset } = form;
  const errors = formState.errors;
  const values = useWatch({ control });
  const option = options.networks.find((n) => n.network === values.network) ?? options.networks[0];
  const methods = option?.methods ?? [];
  const usesLlm = values.left === options.llm || values.right === options.llm;
  const usesCandidate = values.left === options.candidate || values.right === options.candidate;

  const pickNetwork = (network: Network) => {
    const next = options.networks.find((n) => n.network === network);
    if (next) reset(fitRequest({ ...getValues(), network }, next, options));
  };
  const toggleEvent = (e: ScenarioEvent) => {
    const events = getValues("events");
    setValue("events", events.includes(e) ? events.filter((x) => x !== e) : [...events, e], {
      shouldDirty: true,
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("scenarioPage.new")}</CardTitle>
        <CardDescription>{t("scenarioPage.newText")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={(e) => void handleSubmit((v) => setPending(v))(e)}
          noValidate
          className="flex flex-col gap-5"
        >
          <fieldset
            disabled={!live || create.isPending}
            className="flex flex-col gap-5 disabled:opacity-70"
          >
            <fieldset>
              <legend className="mb-2 text-sm font-semibold text-text">
                {t("scenarioPage.stepCity")}
              </legend>
              <div role="radiogroup" className="grid gap-2 sm:grid-cols-2 2xl:grid-cols-3">
                {options.networks.map((n) => {
                  const Icon = NETWORK_ICONS[n.network];
                  const checked = n.network === values.network;
                  return (
                    <button
                      key={n.network}
                      type="button"
                      role="radio"
                      aria-checked={checked}
                      onClick={() => pickNetwork(n.network)}
                      className={cn(
                        "flex items-start gap-3 rounded-lg border px-3 py-2.5 text-start transition-colors",
                        checked
                          ? "border-text bg-surface-2 ring-1 ring-text"
                          : "border-border hover:border-border-strong hover:bg-surface-2",
                      )}
                    >
                      <Icon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-text-2" />
                      <span className="flex min-w-0 flex-col gap-0.5">
                        <span className="text-sm font-medium text-text">
                          {f.networkName(n.network)}
                        </span>
                        <span className="text-xs leading-snug text-muted">
                          {t(`scenarioPage.netInfo.${n.network}`)}
                        </span>
                        <span className="flex flex-wrap gap-1 pt-1">
                          {n.events.includes("pedestrians") ? (
                            <Tag>{t("scenarioPage.tagPedestrians")}</Tag>
                          ) : null}
                          {n.bigCity ? (
                            <Tag tone="warn">
                              {t("scenarioPage.tagScale", { scale: f.number(n.scale) })}
                            </Tag>
                          ) : null}
                        </span>
                      </span>
                    </button>
                  );
                })}
              </div>
              {option?.bigCity ? (
                <p className="mt-2 rounded-md border border-border bg-surface-2 px-3 py-2 text-xs leading-relaxed text-text-2">
                  {t("scenarioPage.bigCityNote", { scale: f.number(option.scale) })}
                </p>
              ) : null}
            </fieldset>

            <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_12rem]">
              <fieldset>
                <legend className="mb-2 text-sm font-semibold text-text">
                  {t("scenarioPage.stepEvents")}
                </legend>
                <div className="flex flex-wrap gap-2">
                  {(["emergency", "pedestrians", "incident", "buses"] as const).map((e) => {
                    const Icon = EVENT_ICONS[e];
                    const allowed = option?.events.includes(e) ?? false;
                    const on = allowed && (values.events ?? []).includes(e);
                    return (
                      <button
                        key={e}
                        type="button"
                        aria-pressed={on}
                        disabled={!allowed}
                        title={
                          allowed
                            ? undefined
                            : t(
                                `scenarioPage.eventOff.${e === "pedestrians" ? "pedestrians" : "other"}`,
                              )
                        }
                        onClick={() => toggleEvent(e)}
                        className={cn(
                          "flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-sm transition-colors",
                          on
                            ? "border-text bg-text text-bg"
                            : "border-border-strong text-text-2 hover:bg-surface-2",
                          !allowed && "cursor-not-allowed border-dashed opacity-50",
                        )}
                      >
                        <Icon aria-hidden="true" className="size-3.5" />
                        {f.scenarioName(e)}
                      </button>
                    );
                  })}
                </div>
                {option && !option.events.includes("pedestrians") ? (
                  <p className="mt-2 text-xs text-muted">
                    {t("scenarioPage.eventOff.pedestrians")}
                  </p>
                ) : null}
              </fieldset>
              <SelectField id="sc-demand" label={t("filters.demand")} {...register("demand")}>
                {DEMANDS.map((d) => (
                  <option key={d} value={d}>
                    {f.demandName(d)}
                  </option>
                ))}
              </SelectField>
            </div>

            <fieldset className="flex flex-col gap-3">
              <legend className="mb-2 text-sm font-semibold text-text">
                {t("scenarioPage.stepControllers")}
              </legend>
              {option ? (
                <div className="flex flex-wrap gap-2">
                  {presets(option, options).map((p) => {
                    const on = values.left === p.left && values.right === p.right;
                    return (
                      <Button
                        key={p.key}
                        type="button"
                        size="sm"
                        variant={on ? "primary" : "outline"}
                        aria-pressed={on}
                        onClick={() => {
                          setValue("left", p.left, { shouldDirty: true });
                          setValue("right", p.right, { shouldDirty: true, shouldValidate: true });
                        }}
                      >
                        {p.key === "vsLlm" ? (
                          <MessagesSquare aria-hidden="true" />
                        ) : (
                          <Sparkles aria-hidden="true" />
                        )}
                        {t(`scenarioPage.presets.${p.key}`)}
                      </Button>
                    );
                  })}
                </div>
              ) : null}
              <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_8rem]">
                <SelectField id="sc-left" label={t("scenarioPage.left")} {...register("left")}>
                  {methods.map((m) => (
                    <option key={m} value={m}>
                      {f.methodName(m)}
                    </option>
                  ))}
                </SelectField>
                <div className="flex flex-col gap-1.5">
                  <SelectField
                    id="sc-right"
                    label={t("scenarioPage.right")}
                    aria-invalid={Boolean(errors.right)}
                    {...register("right")}
                  >
                    {methods.map((m) => (
                      <option key={m} value={m}>
                        {f.methodName(m)}
                      </option>
                    ))}
                  </SelectField>
                  {errors.right ? (
                    <p role="alert" className="text-xs text-jam">
                      {t("scenarioPage.different")}
                    </p>
                  ) : null}
                </div>
                <div className="flex flex-col gap-1.5">
                  <label htmlFor="sc-seed" className="text-sm font-medium text-text">
                    {t("scenarioPage.seed")}
                  </label>
                  <input
                    id="sc-seed"
                    type="number"
                    min={0}
                    max={999}
                    aria-invalid={Boolean(errors.seed)}
                    aria-describedby={errors.seed ? "sc-seed-error" : undefined}
                    className="h-9 rounded-md border border-border-strong bg-surface-2 px-3 text-sm text-text"
                    {...register("seed", { valueAsNumber: true })}
                  />
                  {errors.seed ? (
                    <p id="sc-seed-error" role="alert" className="text-xs text-jam">
                      {t("scenarioPage.seedRange")}
                    </p>
                  ) : null}
                </div>
              </div>
              {usesCandidate || usesLlm ? (
                <ul className="flex flex-col gap-1.5 text-xs leading-relaxed text-text-2">
                  {usesCandidate ? (
                    <Note color={methodColor(options.candidate)}>
                      {t("scenarioPage.candidateNote")}
                    </Note>
                  ) : null}
                  {usesLlm ? (
                    <Note color={methodColor(options.llm)}>{t("scenarioPage.llmNote")}</Note>
                  ) : null}
                </ul>
              ) : null}
            </fieldset>
          </fieldset>
          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" variant="primary" disabled={!live || create.isPending}>
              <Play aria-hidden="true" className="rtl:-scale-x-100" />
              {t("scenarioPage.submit")}
            </Button>
            {!live ? <p className="text-xs text-muted">{t("scenarioPage.liveOnly")}</p> : null}
            {create.isError ? (
              <p role="alert" className="text-xs text-jam">
                {create.error.message}
              </p>
            ) : null}
            {create.isSuccess ? (
              <p role="status" className="text-xs text-flow">
                {t("assistantChat.launched")}
              </p>
            ) : null}
          </div>
        </form>
        <ConfirmDialog
          open={pending !== null}
          onOpenChange={(open) => !open && setPending(null)}
          title={t("scenarioPage.confirmTitle")}
          description={t(
            option?.bigCity ? "scenarioPage.confirmTextBig" : "scenarioPage.confirmText",
          )}
          confirmLabel={t("scenarioPage.confirm")}
          cancelLabel={t("scenarioPage.cancel")}
          onConfirm={() => {
            if (pending) create.mutate(pending);
            setPending(null);
          }}
        >
          {pending ? (
            <p className="rounded-md bg-surface-2 p-2 text-xs text-text-2">
              {f.networkName(pending.network)} · {f.demandName(pending.demand)} ·{" "}
              {pending.events.map((e) => tx(`scenarios.${e}`)).join(", ") ||
                f.scenarioName("normal")}{" "}
              · s{pending.seed}
              <br />
              {f.methodName(pending.left)} / {f.methodName(pending.right)}
            </p>
          ) : null}
        </ConfirmDialog>
      </CardContent>
    </Card>
  );
}

function Tag({ children, tone }: { children: string; tone?: "warn" }) {
  return (
    <span
      className={cn(
        "rounded-full border px-1.5 py-px text-[10.5px] font-medium",
        tone === "warn" ? "border-border-strong text-text-2" : "border-border text-muted",
      )}
    >
      {children}
    </span>
  );
}

function Note({ color, children }: { color: string; children: string }) {
  return (
    <li className="flex items-start gap-2">
      <span
        aria-hidden="true"
        className="mt-1.5 size-2 shrink-0 rounded-full"
        style={{ background: color }}
      />
      <span>{children}</span>
    </li>
  );
}
