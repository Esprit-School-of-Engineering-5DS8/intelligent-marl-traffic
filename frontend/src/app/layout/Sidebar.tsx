import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useTranslation } from "react-i18next";
import { NavLink } from "react-router";

import { NAV } from "@/app/nav";
import { useUi } from "@/app/ui-store";
import { cn } from "@/shared/lib/cn";

export function Sidebar() {
  const { t } = useTranslation();
  const collapsed = useUi((s) => s.sidebarCollapsed);
  const toggle = useUi((s) => s.toggleSidebar);

  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col border-e border-border bg-surface transition-[width]",
        collapsed ? "w-16" : "w-60",
      )}
    >
      <div className="flex h-14 items-center gap-2 border-b border-border px-4">
        <img src="/favicon.svg" alt="" className="size-7 shrink-0" />
        {collapsed ? null : (
          <div className="flex min-w-0 flex-col leading-tight">
            <span className="text-sm font-semibold text-text">{t("app.name")}</span>
            <span className="truncate text-xs text-muted">{t("app.tagline")}</span>
          </div>
        )}
      </div>

      <nav aria-label={t("nav.label")} className="flex-1 overflow-y-auto px-2 py-3">
        {NAV.map((group) => (
          <div key={group.key} className="mb-4">
            {collapsed ? (
              <hr className="mx-2 mb-2 border-border" />
            ) : (
              <h2 className="px-3 pb-1 text-[11px] font-medium tracking-wide text-muted uppercase">
                {t(`nav.groups.${group.key}`)}
              </h2>
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
                        "flex h-9 items-center gap-3 rounded-md px-3 text-sm transition-colors",
                        isActive
                          ? "bg-accent-soft font-medium text-accent"
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
