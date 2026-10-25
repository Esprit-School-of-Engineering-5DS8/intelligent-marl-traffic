import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

export function EmptyState({
  icon: Icon,
  title,
  children,
  action,
}: {
  icon: LucideIcon;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-none border border-dashed border-border-strong bg-surface/85 backdrop-blur-md px-6 py-14 text-center">
      <Icon aria-hidden="true" className="size-8 text-muted" />
      <h2 className="text-base font-semibold text-text">{title}</h2>
      {children ? <p className="max-w-md text-sm text-text-2">{children}</p> : null}
      {action}
    </div>
  );
}
