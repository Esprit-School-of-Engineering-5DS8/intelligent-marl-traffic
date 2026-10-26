import { zodResolver } from "@hookform/resolvers/zod";
import { Check, RotateCcw } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { useShallow } from "zustand/react/shallow";

import { usePolicy, useUpdatePolicy } from "@/shared/api/policy";
import { LANGUAGES } from "@/shared/i18n";
import { usePageTitle } from "@/shared/lib/use-page-title";
import { Button } from "@/shared/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/shared/ui/card";
import { SelectField } from "@/shared/ui/field";
import { PageHeader } from "@/shared/ui/page-header";

import { SettingsSchema } from "./schema";
import {
  BASELINE_METHODS,
  DEFAULT_SETTINGS,
  LEARNED_METHODS,
  controlMethod,
  useSettings,
  type Settings,
} from "./store";

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4 sm:grid-cols-2">{children}</CardContent>
    </Card>
  );
}

export default function SettingsPage() {
  const { t } = useTranslation();
  usePageTitle(t("pages.settings.title"));

  const current = useSettings(
    useShallow((s): Settings => ({
      theme: s.theme,
      language: s.language,
      timeUnit: s.timeUnit,
      speedUnit: s.speedUnit,
      dataSource: s.dataSource,
      llmProvider: s.llmProvider,
      controlMode: s.controlMode,
      baselineMethod: s.baselineMethod,
      learnedMethod: s.learnedMethod,
    })),
  );
  const update = useSettings((s) => s.update);
  const [saved, setSaved] = useState(false);
  const policy = usePolicy();
  const updatePolicy = useUpdatePolicy();
  const [policyNote, setPolicyNote] = useState<{ ok: boolean; text: string } | null>(null);

  const form = useForm<Settings>({
    resolver: zodResolver(SettingsSchema),
    // follows changes made elsewhere (top bar) without discarding edits in progress
    values: current,
    resetOptions: { keepDirtyValues: true },
  });
  const { register, handleSubmit, formState } = form;

  const onSubmit = handleSubmit((values) => {
    update(values);
    setSaved(true);
    // The live simulation runs the policy the backend holds; mock data needs no backend.
    if (values.dataSource === "live") {
      updatePolicy.mutate(
        { method: controlMethod(values) },
        {
          onSuccess: (data) =>
            setPolicyNote({
              ok: data.available && !data.degraded,
              text: data.reason ?? `${data.label} · ${data.network}`,
            }),
          onError: (error) =>
            setPolicyNote({
              ok: false,
              text: error instanceof Error ? error.message : String(error),
            }),
        },
      );
    }
  });

  const onReset = () => {
    update(DEFAULT_SETTINGS);
    form.reset(DEFAULT_SETTINGS);
    setSaved(true);
  };

  return (
    <div className="flex max-w-4xl flex-col gap-6">
      <PageHeader title={t("pages.settings.title")} description={t("pages.settings.description")} />

      <form
        onSubmit={(e) => void onSubmit(e)}
        onChange={() => setSaved(false)}
        className="flex flex-col gap-4"
        noValidate
      >
        <Section title={t("settings.appearance")}>
          <SelectField id="theme" label={t("settings.theme")} {...register("theme")}>
            <option value="dark">{t("settings.themeDark")}</option>
            <option value="light">{t("settings.themeLight")}</option>
            <option value="system">{t("settings.themeSystem")}</option>
          </SelectField>
          <SelectField id="language" label={t("settings.language")} {...register("language")}>
            {Object.entries(LANGUAGES).map(([code, { label }]) => (
              <option key={code} value={code} lang={code}>
                {label}
              </option>
            ))}
          </SelectField>
        </Section>

        <Section title={t("settings.units")}>
          <SelectField id="timeUnit" label={t("settings.timeUnit")} {...register("timeUnit")}>
            <option value="s">{t("settings.timeSeconds")}</option>
            <option value="min">{t("settings.timeMinutes")}</option>
          </SelectField>
          <SelectField id="speedUnit" label={t("settings.speedUnit")} {...register("speedUnit")}>
            <option value="kmh">{t("settings.speedKmh")}</option>
            <option value="ms">{t("settings.speedMs")}</option>
          </SelectField>
        </Section>

        <Section title={t("settings.data")}>
          <SelectField
            id="dataSource"
            label={t("settings.dataSource")}
            help={t("settings.dataSourceHelp")}
            {...register("dataSource")}
          >
            <option value="mock">{t("settings.dataSourceMock")}</option>
            <option value="live">{t("settings.dataSourceLive")}</option>
          </SelectField>
        </Section>

        <Section title={t("settings.control")}>
          <SelectField
            id="controlMode"
            label={t("settings.controlMode")}
            help={t("settings.controlHelp")}
            {...register("controlMode")}
          >
            <option value="baseline">{t("settings.controlBaseline")}</option>
            <option value="learned">{t("settings.controlLearned")}</option>
            <option value="llm">{t("settings.controlLlm")}</option>
          </SelectField>
          <SelectField
            id="baselineMethod"
            label={t("settings.baselineMethod")}
            {...register("baselineMethod")}
          >
            {BASELINE_METHODS.map((method) => (
              <option key={method} value={method}>
                {method}
              </option>
            ))}
          </SelectField>
          <SelectField
            id="learnedMethod"
            label={t("settings.learnedMethod")}
            help={t("settings.learnedHelp")}
            {...register("learnedMethod")}
          >
            {LEARNED_METHODS.map((method) => (
              <option key={method} value={method}>
                {method}
              </option>
            ))}
          </SelectField>
          <p className="text-sm text-text-2 sm:col-span-2" role="status" aria-live="polite">
            {policyNote ? (
              <span className={policyNote.ok ? "text-flow" : "text-jam"}>{policyNote.text}</span>
            ) : policy.data ? (
              t("settings.policyActive", { method: policy.data.label })
            ) : (
              t("settings.policyOffline")
            )}
          </p>
        </Section>

        <Section title={t("settings.llm")}>
          <SelectField
            id="llmProvider"
            label={t("settings.llmProvider")}
            help={t("settings.llmHelp")}
            {...register("llmProvider")}
          >
            <option value="ollama">{t("settings.llmOllama")}</option>
            <option value="claude">{t("settings.llmClaude")}</option>
            <option value="openai">{t("settings.llmOpenai")}</option>
          </SelectField>
        </Section>

        <div className="flex flex-wrap items-center gap-3">
          <Button type="submit" variant="primary">
            {t("settings.save")}
          </Button>
          <Button type="button" variant="ghost" onClick={onReset}>
            <RotateCcw aria-hidden="true" />
            {t("settings.reset")}
          </Button>
          <p role="status" aria-live="polite" className="text-sm text-text-2">
            {saved ? (
              <span className="inline-flex items-center gap-1.5 text-flow">
                <Check aria-hidden="true" className="size-4" />
                {t("settings.saved")}
              </span>
            ) : formState.isDirty ? (
              t("settings.unsaved")
            ) : null}
          </p>
        </div>
      </form>
    </div>
  );
}
