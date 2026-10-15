import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";

import { useDocumentSettings } from "./theme";

function DocumentSettings() {
  useDocumentSettings();
  return null;
}

export function Providers({ children }: { children: ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          // results are files that change between experiment runs, not between clicks
          queries: { staleTime: 5 * 60_000, retry: 1, refetchOnWindowFocus: false },
        },
      }),
  );
  return (
    <QueryClientProvider client={queryClient}>
      <DocumentSettings />
      {children}
    </QueryClientProvider>
  );
}
