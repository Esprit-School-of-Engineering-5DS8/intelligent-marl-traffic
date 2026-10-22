import { X } from "lucide-react";
import { Dialog } from "radix-ui";
import type { ReactNode } from "react";

/** Side panel (Radix dialog: focus trapped, Escape closes, labelled for screen readers). */
export function Sheet({
  open,
  onOpenChange,
  title,
  description,
  closeLabel,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  description?: string;
  closeLabel: string;
  children: ReactNode;
}) {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-40 bg-black/40" />
        <Dialog.Content className="fixed inset-y-0 end-0 z-50 flex w-full max-w-md flex-col border-s border-border bg-surface shadow-xl focus:outline-none">
          <header className="flex items-start justify-between gap-4 border-b border-border p-4">
            <div className="flex flex-col gap-1">
              <Dialog.Title className="text-base font-semibold text-text">{title}</Dialog.Title>
              {description ? (
                <Dialog.Description className="text-sm text-text-2">
                  {description}
                </Dialog.Description>
              ) : null}
            </div>
            <Dialog.Close
              aria-label={closeLabel}
              className="rounded-md p-1 text-muted hover:bg-surface-2 hover:text-text"
            >
              <X aria-hidden="true" className="size-4" />
            </Dialog.Close>
          </header>
          <div className="min-h-0 flex-1 overflow-y-auto p-4">{children}</div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
