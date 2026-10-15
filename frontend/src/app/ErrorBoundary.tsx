import { TriangleAlert } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/shared/ui/button";

export function ErrorPanel({ onRetry }: { onRetry: () => void }) {
  const { t } = useTranslation();
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-3 rounded-lg border border-jam/40 bg-jam-soft p-6"
    >
      <div className="flex items-center gap-2 text-jam">
        <TriangleAlert aria-hidden="true" className="size-5" />
        <h2 className="text-base font-semibold">{t("common.errorTitle")}</h2>
      </div>
      <p className="max-w-xl text-sm text-text-2">{t("common.errorText")}</p>
      <Button variant="outline" onClick={onRetry}>
        {t("common.retry")}
      </Button>
    </div>
  );
}

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Contains a crash to the page (or widget) it wraps; the shell and the other pages keep
 * working. Give it a `key` that changes with the route so navigating away resets it.
 */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Page crashed", error, info.componentStack);
  }

  override render(): ReactNode {
    if (this.state.error) return <ErrorPanel onRetry={() => this.setState({ error: null })} />;
    return this.props.children;
  }
}
