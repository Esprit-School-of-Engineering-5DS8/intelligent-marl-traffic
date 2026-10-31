import {
  Bot,
  CornerDownLeft,
  Languages,
  Moon,
  PanelLeft,
  Search,
  Sun,
  type LucideIcon,
} from "lucide-react";
import { Dialog } from "radix-ui";
import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";

import { NAV } from "@/app/nav";
import { useResolvedTheme } from "@/app/theme";
import { useUi } from "@/app/ui-store";
import { useSettings, type Language } from "@/features/settings/store";
import { LANGUAGES } from "@/shared/i18n";
import { cn } from "@/shared/lib/cn";
import { Kbd } from "@/shared/ui/kbd";

import { filterCommands } from "./filter";

interface Command {
  id: string;
  group: "pages" | "actions";
  label: string;
  hint?: string;
  icon: LucideIcon;
  keywords?: string;
  run: () => void;
}

function useCommands(close: () => void): Command[] {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const theme = useResolvedTheme();
  const language = useSettings((s) => s.language);
  const update = useSettings((s) => s.update);
  const setAssistantOpen = useUi((s) => s.setAssistantOpen);
  const toggleSidebar = useUi((s) => s.toggleSidebar);
  const collapsed = useUi((s) => s.sidebarCollapsed);

  return useMemo(() => {
    const done = (action: () => void) => () => {
      close();
      action();
    };
    const pages: Command[] = NAV.flatMap((group) =>
      group.items.map(({ key, path, icon }) => ({
        id: `page-${key}`,
        group: "pages" as const,
        label: t(`nav.${key}`),
        hint: t(`nav.groups.${group.key}`),
        icon,
        keywords: path,
        run: done(() => void navigate(path)),
      })),
    );
    const languages: Command[] = (Object.keys(LANGUAGES) as Language[])
      .filter((code) => code !== language)
      .map((code) => ({
        id: `language-${code}`,
        group: "actions" as const,
        label: t("palette.language", { language: LANGUAGES[code].label }),
        icon: Languages,
        keywords: "langue language",
        run: done(() => update({ language: code })),
      }));
    const actions: Command[] = [
      {
        id: "assistant",
        group: "actions",
        label: t("palette.assistant"),
        icon: Bot,
        keywords: "assistant chat question",
        run: done(() => setAssistantOpen(true)),
      },
      {
        id: "theme",
        group: "actions",
        label: theme === "dark" ? t("topbar.toLight") : t("topbar.toDark"),
        icon: theme === "dark" ? Sun : Moon,
        keywords: "theme thème",
        run: done(() => update({ theme: theme === "dark" ? "light" : "dark" })),
      },
      ...languages,
      {
        id: "sidebar",
        group: "actions",
        label: collapsed ? t("nav.expand") : t("nav.collapse"),
        icon: PanelLeft,
        keywords: "menu sidebar",
        run: done(toggleSidebar),
      },
    ];
    return [...pages, ...actions];
  }, [t, navigate, theme, language, update, setAssistantOpen, toggleSidebar, collapsed, close]);
}

/** Ctrl+K: every page and the main actions, searched and run from the keyboard. */
export function CommandPalette() {
  const { t } = useTranslation();
  const open = useUi((s) => s.paletteOpen);
  const setOpen = useUi((s) => s.setPaletteOpen);
  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px]" />
        <Dialog.Content
          aria-describedby={undefined}
          className="fixed start-1/2 top-[12vh] z-50 flex max-h-[70vh] w-[min(640px,calc(100vw-2rem))] -translate-x-1/2 flex-col overflow-hidden rounded-xl border border-border-strong bg-surface shadow-2xl focus:outline-none rtl:translate-x-1/2"
        >
          <Dialog.Title className="sr-only">{t("palette.title")}</Dialog.Title>
          {/* mounted only while open: each opening starts a fresh search */}
          <PaletteBody close={() => setOpen(false)} />
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}

function PaletteBody({ close }: { close: () => void }) {
  const { t } = useTranslation();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const listId = useId();
  const listRef = useRef<HTMLUListElement>(null);
  const commands = useCommands(close);
  const shown = filterCommands(commands, query);
  const current = Math.min(active, Math.max(0, shown.length - 1));

  useEffect(() => {
    listRef.current
      ?.querySelector(`[data-index="${current}"]`)
      // not in every environment (jsdom)
      ?.scrollIntoView?.({ block: "nearest" });
  }, [current]);

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((current + 1) % Math.max(1, shown.length));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((current - 1 + shown.length) % Math.max(1, shown.length));
    } else if (e.key === "Home") {
      e.preventDefault();
      setActive(0);
    } else if (e.key === "End") {
      e.preventDefault();
      setActive(shown.length - 1);
    } else if (e.key === "Enter") {
      e.preventDefault();
      shown[current]?.run();
    }
  };

  const groups = (["pages", "actions"] as const)
    .map((g) => ({ key: g, items: shown.filter((c) => c.group === g) }))
    .filter((g) => g.items.length);

  return (
    <>
      <div className="flex items-center gap-3 border-b border-border px-4">
        <Search aria-hidden="true" className="size-4 shrink-0 text-muted" />
        <input
          role="combobox"
          aria-expanded="true"
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={shown.length ? `${listId}-${current}` : undefined}
          aria-label={t("palette.title")}
          placeholder={t("palette.placeholder")}
          value={query}
          onChange={(e) => {
            setQuery(e.target.value);
            setActive(0);
          }}
          onKeyDown={onKeyDown}
          className="h-14 min-w-0 flex-1 bg-transparent text-base text-text outline-none placeholder:text-muted"
        />
        <Kbd aria-hidden="true">Esc</Kbd>
      </div>
      <ul
        ref={listRef}
        id={listId}
        role="listbox"
        aria-label={t("palette.results")}
        className="min-h-0 flex-1 overflow-y-auto p-2"
      >
        {groups.map((group) => (
          <li key={group.key} role="presentation">
            <p id={`${listId}-${group.key}`} className="eyebrow px-3 pt-2 pb-1" aria-hidden="true">
              {t(`palette.groups.${group.key}`)}
            </p>
            <ul role="group" aria-labelledby={`${listId}-${group.key}`}>
              {group.items.map((c) => {
                const index = shown.indexOf(c);
                const selected = index === current;
                const Icon = c.icon;
                return (
                  // keyboard handled by the input (combobox pattern); the mouse picks too
                  // eslint-disable-next-line jsx-a11y/click-events-have-key-events
                  <li
                    key={c.id}
                    id={`${listId}-${index}`}
                    data-index={index}
                    role="option"
                    aria-selected={selected}
                    onMouseMove={() => setActive(index)}
                    onClick={c.run}
                    className={cn(
                      "flex h-10 cursor-pointer items-center gap-3 rounded-md px-3 text-sm",
                      selected ? "bg-accent-soft text-text" : "text-text-2",
                    )}
                  >
                    <Icon aria-hidden="true" className="size-4 shrink-0" />
                    <span className="min-w-0 flex-1 truncate">{c.label}</span>
                    {c.hint ? <span className="text-xs text-muted">{c.hint}</span> : null}
                    {selected ? (
                      <CornerDownLeft aria-hidden="true" className="size-3.5 text-muted" />
                    ) : null}
                  </li>
                );
              })}
            </ul>
          </li>
        ))}
        {!shown.length ? (
          <li role="presentation" className="px-3 py-8 text-center text-sm text-muted">
            {t("palette.empty")}
          </li>
        ) : null}
      </ul>
      <footer className="flex items-center gap-4 border-t border-border px-4 py-2 text-[11px] text-muted">
        <span className="flex items-center gap-1.5">
          <Kbd>↑</Kbd>
          <Kbd>↓</Kbd> {t("palette.move")}
        </span>
        <span className="flex items-center gap-1.5">
          <Kbd>↵</Kbd> {t("palette.run")}
        </span>
        <span className="flex items-center gap-1.5">
          <Kbd>Esc</Kbd> {t("palette.close")}
        </span>
      </footer>
    </>
  );
}
