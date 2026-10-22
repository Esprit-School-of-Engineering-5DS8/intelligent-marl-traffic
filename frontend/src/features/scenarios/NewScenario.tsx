import { zodResolver } from "@hookform/resolvers/zod";
import { Play } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";

import { useSettings } from "@/features/settings/store";
import { useCreateRun } from "@/shared/api/backend";
import { useFormat, useTx } from "@/shared/domain/format";
import { sortMethods } from "@/shared/domain/methods";
import { DEMANDS, EVENTS, NETWORKS, ScenarioRequest, type Meta } from "@/shared/schemas";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/shared/ui/card";
import { ConfirmDialog } from "@/shared/ui/confirm-dialog";
import { SelectField } from "@/shared/ui/field";

/**
 * Asks the backend to run the same episode under two controllers and record a replay.
 * Launching is a state change: it is confirmed first, and only possible with the backend.
 */
export function NewScenario({ meta }: { meta: Meta }) {
  const { t } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const live = useSettings((s) => s.dataSource) === "live";
  const create = useCreateRun();
  const [pending, setPending] = useState<ScenarioRequest | null>(null);
  const methods = sortMethods(meta.methods.filter((m) => !m.includes("_ev")));

  const form = useForm<ScenarioRequest>({
    resolver: zodResolver(ScenarioRequest),
    defaultValues: {
      network: "grid4x4",
      demand: "peak",
      events: ["emergency"],
      seed: 3,
      left: "ft",
      right: "coop_full",
    },
  });
  const { register, handleSubmit, formState } = form;
  const errors = formState.errors;

  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("scenarioPage.new")}</CardTitle>
        <CardDescription>{t("scenarioPage.newText")}</CardDescription>
      </CardHeader>
      <CardContent>
        <form
          onSubmit={(e) => void handleSubmit((values) => setPending(values))(e)}
          noValidate
          className="flex flex-col gap-4"
        >
          <fieldset
            disabled={!live || create.isPending}
            className="grid gap-3 disabled:opacity-60 sm:grid-cols-2"
          >
            <SelectField id="sc-network" label={t("filters.network")} {...register("network")}>
              {NETWORKS.map((n) => (
                <option key={n} value={n}>
                  {f.networkName(n)}
                </option>
              ))}
            </SelectField>
            <SelectField id="sc-demand" label={t("filters.demand")} {...register("demand")}>
              {DEMANDS.map((d) => (
                <option key={d} value={d}>
                  {f.demandName(d)}
                </option>
              ))}
            </SelectField>
            <fieldset className="sm:col-span-2">
              <legend className="mb-1.5 text-sm font-medium text-text">
                {t("scenarioPage.events")}
              </legend>
              <div className="flex flex-wrap gap-3">
                {EVENTS.map((e) => (
                  <label key={e} className="flex items-center gap-2 text-sm text-text-2">
                    <input
                      type="checkbox"
                      value={e}
                      {...register("events")}
                      className="size-4 accent-[var(--accent)]"
                    />
                    {f.scenarioName(e)}
                  </label>
                ))}
              </div>
            </fieldset>
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
          description={t("scenarioPage.confirmText")}
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
