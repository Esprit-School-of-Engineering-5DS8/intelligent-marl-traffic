import { useTranslation } from "react-i18next";

/** True when the interface reads right to left (Arabic): charts mirror their x axis. */
export function useRtl(): boolean {
  const { i18n } = useTranslation();
  return i18n.dir(i18n.language) === "rtl";
}
