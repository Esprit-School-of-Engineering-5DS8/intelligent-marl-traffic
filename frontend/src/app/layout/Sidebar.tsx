import { PanelLeftClose, PanelLeftOpen, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router";

import { NAV } from "@/app/nav";
import { useUi } from "@/app/ui-store";
import { cn } from "@/shared/lib/cn";
import { Kbd } from "@/shared/ui/kbd";

export function Sidebar() {
  const { t } = useTranslation();
  const collapsed = useUi((s) => s.sidebarCollapsed);
  const toggle = useUi((s) => s.toggleSidebar);
  const openPalette = useUi((s) => s.setPaletteOpen);

  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col border-e border-border bg-surface transition-[width]",
        collapsed ? "w-16" : "w-64",
      )}
    >
      <div className="flex h-16 items-center gap-3 border-b border-border px-4">
        <img src="/favicon.svg" alt="" className="size-8 shrink-0" />
        {collapsed ? null : (
          <div className="flex min-w-0 flex-col leading-tight">
            <span className="text-[15px] font-semibold tracking-tight text-text">
              {t("app.name")}
            </span>
            <span className="truncate text-xs text-muted">{t("app.tagline")}</span>
          </div>
        )}
      </div>

      <div className="px-3 pt-3">
        <button
          type="button"
          onClick={() => openPalette(true)}
          aria-keyshortcuts="Control+K"
          title={collapsed ? t("palette.open") : undefined}
          className={cn(
            "flex h-9 w-full items-center gap-2 rounded-md border border-border bg-surface-2 px-3 text-sm text-muted hover:border-border-strong hover:text-text",
            collapsed && "justify-center px-0",
          )}
        >
          <Search aria-hidden="true" className="size-4 shrink-0" />
          <span className={cn("flex-1 text-start", collapsed && "sr-only")}>
            {t("palette.open")}
          </span>
          {collapsed ? null : <Kbd aria-hidden="true">Ctrl K</Kbd>}
        </button>
      </div>

      <nav aria-label={t("nav.label")} className="flex-1 overflow-y-auto px-3 py-3">
        {NAV.map((group) => (
          <div key={group.key} className="mb-5">
            {collapsed ? (
              <hr className="mx-2 mb-2 border-border" />
            ) : (
              <h2 className="eyebrow px-3 pb-1.5">{t(`nav.groups.${group.key}`)}</h2>
            )}
            <ul className="flex flex-col gap-0.5">
              {group.items.map(({ key, path, icon: Icon }) => (
                <li key={key}>
                  <NavLink
                    to={path}
                    end={path === "/"}
                    title={collapsed ? t(`nav.${key}`) : undefined}
                    className={({ isActive }) =>
                      cn(
                        "relative flex h-9 items-center gap-3 rounded-md px-3 text-sm transition-colors",
                        isActive
                          ? "bg-accent-soft font-medium text-text before:absolute before:inset-y-2 before:start-0 before:w-0.5 before:rounded-full before:bg-accent"
                          : "text-text-2 hover:bg-surface-2 hover:text-text",
                        collapsed && "justify-center px-0",
                      )
                    }
                  >
                    <Icon aria-hidden="true" className="size-4 shrink-0" />
                    <span className={cn(collapsed && "sr-only")}>{t(`nav.${key}`)}</span>
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>

      <div className="border-t border-border p-2">
        <button
          type="button"
          onClick={toggle}
          aria-expanded={!collapsed}
          className={cn(
            "flex h-9 w-full items-center gap-3 rounded-md px-3 text-sm text-text-2 hover:bg-surface-2 hover:text-text",
            collapsed && "justify-center px-0",
          )}
        >
          {collapsed ? (
            <PanelLeftOpen aria-hidden="true" className="size-4 rtl:-scale-x-100" />
          ) : (
            <PanelLeftClose aria-hidden="true" className="size-4 rtl:-scale-x-100" />
          )}
          <span className={cn(collapsed && "sr-only")}>
            {collapsed ? t("nav.expand") : t("nav.collapse")}
          </span>
        </button>
      </div>
    </aside>
  );
}
