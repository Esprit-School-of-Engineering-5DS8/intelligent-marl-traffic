import { Bot, Eraser, FileText, Send, Square, User } from "lucide-react";
import { useRef, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import Markdown from "react-markdown";
import { useLocation } from "react-router";

import { useSettings } from "@/features/settings/store";
import { useLlmStatus } from "@/shared/api/backend";
import { useComparisons, useMeta, useSummary } from "@/shared/api/queries";
import { useFormat, useTx } from "@/shared/domain/format";
import { cn } from "@/shared/lib/cn";
import type { ChatEvent } from "@/shared/schemas";
import { useFilters } from "@/shared/state/filters";
import { Badge } from "@/shared/ui/badge";
import { Button } from "@/shared/ui/button";

import { answerLocally } from "./local";
import { newId, useChat, type Message } from "./store";
import { streamChat } from "./stream";
import { ToolCard } from "./ToolCard";

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Questions about the results, answered from the result files (locally or via the backend). */
export function Chat({ compact = false }: { compact?: boolean }) {
  const { t, i18n } = useTranslation();
  const tx = useTx();
  const f = useFormat();
  const { pathname } = useLocation();
  const live = useSettings((s) => s.dataSource) === "live";
  const provider = useSettings((s) => s.llmProvider);
  const llm = useLlmStatus();
  const meta = useMeta();
  const summary = useSummary();
  const comparisons = useComparisons();
  const { messages, add, update, clear } = useChat();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const abort = useRef<AbortController | null>(null);
  const list = useRef<HTMLDivElement>(null);
  const ready = Boolean(meta.data && summary.data && comparisons.data);

  const apply = (id: string, ev: ChatEvent) =>
    update(id, (m): Message => {
      switch (ev.type) {
        case "token":
          return { ...m, text: m.text + ev.text };
        case "tool_call":
          return { ...m, tools: [...m.tools, { id: ev.id, call: ev.call, status: "proposed" }] };
        case "source":
          return m.sources.includes(ev.file) ? m : { ...m, sources: [...m.sources, ev.file] };
        case "done":
          return { ...m, writtenBy: ev.writtenBy, streaming: false };
        case "error":
          return { ...m, error: ev.message, streaming: false };
      }
    });

  const scroll = () =>
    requestAnimationFrame(() => list.current?.scrollTo({ top: list.current.scrollHeight }));

  async function send(question: string) {
    const text = question.trim();
    if (!text || busy || !ready) return;
    setInput("");
    setBusy(true);
    add({ id: newId(), role: "user", text, tools: [], sources: [] });
    const id = newId();
    add({ id, role: "assistant", text: "", tools: [], sources: [], streaming: true });
    scroll();
    const { cell, controllers } = useFilters.getState();
    const context = { page: pathname, cell, controllers };
    const controller = new AbortController();
    abort.current = controller;
    const local = async () => {
      const data = { meta: meta.data!, summary: summary.data!, comparisons: comparisons.data! };
      for (const ev of answerLocally(text, context, data, tx, f, live)) {
        if (controller.signal.aborted) break;
        if (ev.type === "token") {
          // shown word by word, like a streamed answer
          for (const word of ev.text.split(/(?<= )/)) {
            apply(id, { type: "token", text: word });
            await sleep(14);
          }
        } else apply(id, ev);
        scroll();
      }
    };
    try {
      // the backend's assistant writes in French; other languages get the code's answers
      if (live && llm.data?.available && i18n.language === "fr") {
        for await (const ev of streamChat(
          { question: text, context, provider, language: i18n.language },
          controller.signal,
        )) {
          apply(id, ev);
          scroll();
        }
      } else {
        await local();
      }
    } catch (err) {
      if (!controller.signal.aborted) {
        // backend lost mid-answer: answer from the exported results instead
        update(id, (m) => ({ ...m, text: "", tools: [], sources: [] }));
        await local().catch(() => apply(id, { type: "error", message: String(err) }));
      }
    } finally {
      update(id, (m) => ({ ...m, streaming: false }));
      setBusy(false);
      abort.current = null;
      scroll();
    }
  }

  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void send(input);
    }
  };

  const suggestions = [
    t("assistantChat.s1"),
    t("assistantChat.s2"),
    t("assistantChat.s3"),
    t("assistantChat.s4"),
  ];
  const online = live && llm.data?.available && i18n.language === "fr";

  return (
    <div
      className={cn(
        "flex min-h-0 flex-col gap-3",
        compact ? "h-full" : "h-[calc(100dvh-220px)] min-h-[480px]",
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <Badge tone={online ? "flow" : "neutral"}>
          <Bot aria-hidden="true" />
          {online ? `${llm.data?.model ?? provider}` : t("assistantChat.writtenByCode")}
        </Badge>
        {messages.length ? (
          <Button variant="ghost" size="sm" onClick={clear} disabled={busy}>
            <Eraser aria-hidden="true" />
            {t("assistantChat.clear")}
          </Button>
        ) : null}
      </div>
      <p className="text-[11px] text-muted">
        {online ? t("assistantChat.online") : t("assistantChat.offline")}
      </p>

      <div
        ref={list}
        role="log"
        aria-live="polite"
        aria-label={t("assistant.title")}
        className="min-h-0 flex-1 overflow-y-auto pe-1"
      >
        {messages.length === 0 ? (
          <div className="flex flex-col gap-2">
            <p className="text-xs font-medium text-text-2">{t("assistantChat.suggestions")}</p>
            {suggestions.map((s) => (
              <button
                key={s}
                type="button"
                disabled={!ready}
                onClick={() => void send(s)}
                className="rounded-md border border-border bg-surface-2 px-3 py-2 text-start text-sm text-text hover:border-border-strong disabled:opacity-50"
              >
                {s}
              </button>
            ))}
          </div>
        ) : (
          <ul className="flex flex-col gap-4">
            {messages.map((m) => (
              <li key={m.id} className="flex gap-2">
                <span
                  aria-hidden="true"
                  className={cn(
                    "mt-0.5 flex size-6 shrink-0 items-center justify-center rounded-full",
                    m.role === "user" ? "bg-surface-3" : "bg-accent-soft text-accent",
                  )}
                >
                  {m.role === "user" ? <User className="size-3.5" /> : <Bot className="size-3.5" />}
                </span>
                <div className="flex min-w-0 flex-1 flex-col gap-2">
                  <span className="sr-only">
                    {m.role === "user" ? t("assistantChat.you") : t("assistant.title")}
                  </span>
                  {m.role === "user" ? (
                    <p className="text-sm text-text">{m.text}</p>
                  ) : (
                    <div className="prose-sm text-sm leading-relaxed text-text [&_strong]:font-semibold [&_ul]:list-disc [&_ul]:ps-5">
                      {m.text ? (
                        <Markdown>{m.text}</Markdown>
                      ) : m.streaming ? (
                        <span className="animate-pulse text-muted">…</span>
                      ) : null}
                    </div>
                  )}
                  {m.tools.map((tool) => (
                    <ToolCard key={tool.id} messageId={m.id} tool={tool} />
                  ))}
                  {m.error ? (
                    <p role="alert" className="text-xs text-jam">
                      {t("assistantChat.error")} : {m.error}
                    </p>
                  ) : null}
                  {m.role === "assistant" && !m.streaming && (m.sources.length || m.writtenBy) ? (
                    <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-muted">
                      {m.writtenBy ? (
                        <span>
                          {m.writtenBy === "model"
                            ? t("assistantChat.writtenByModel")
                            : t("assistantChat.writtenByCode")}
                        </span>
                      ) : null}
                      {m.sources.map((s) => (
                        <span
                          key={s}
                          className="inline-flex items-center gap-1 rounded-sm bg-surface-2 px-1.5 py-0.5 font-mono"
                        >
                          <FileText aria-hidden="true" className="size-3" />
                          {s}
                        </span>
                      ))}
                    </div>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          void send(input);
        }}
        className="flex items-end gap-2"
      >
        <label htmlFor={compact ? "chat-input-panel" : "chat-input"} className="sr-only">
          {t("assistantChat.input")}
        </label>
        <textarea
          id={compact ? "chat-input-panel" : "chat-input"}
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={onKey}
          placeholder={t("assistantChat.inputPlaceholder")}
          className="min-h-[44px] flex-1 resize-none rounded-md border border-border-strong bg-surface-2 px-3 py-2 text-sm text-text placeholder:text-muted"
        />
        {busy ? (
          <Button
            type="button"
            variant="outline"
            size="icon"
            onClick={() => abort.current?.abort()}
            aria-label={t("assistantChat.stop")}
          >
            <Square aria-hidden="true" />
          </Button>
        ) : (
          <Button
            type="submit"
            variant="primary"
            size="icon"
            disabled={!input.trim() || !ready}
            aria-label={t("assistantChat.send")}
          >
            <Send aria-hidden="true" className="rtl:-scale-x-100" />
          </Button>
        )}
      </form>
    </div>
  );
}
