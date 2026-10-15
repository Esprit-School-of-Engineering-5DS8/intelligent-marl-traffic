import "i18next";

import type fr from "./locales/fr.json";

// translation keys are checked at compile time against the French resource
declare module "i18next" {
  interface CustomTypeOptions {
    defaultNS: "translation";
    resources: { translation: typeof fr };
  }
}
