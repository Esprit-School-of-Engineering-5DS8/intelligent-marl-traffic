import { useEffect } from "react";
import { useTranslation } from "react-i18next";

/** Names the browser tab after the page, so history and screen readers say where we are. */
export function usePageTitle(title: string): void {
  const { t } = useTranslation();
  const app = t("app.name");
  useEffect(() => {
    document.title = `${title} - ${app}`;
  }, [title, app]);
}
