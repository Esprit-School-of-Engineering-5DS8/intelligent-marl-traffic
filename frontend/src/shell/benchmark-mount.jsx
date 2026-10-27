/**
 * Benchmark view entry.
 *
 * Renders one React page at a time into `#benchmarkView`. Navigation lives in the
 * dashboard sidebar (`[data-benchmark-tab]`), so this file has no tab bar of its own —
 * it replaces the old `benchmark-rami.jsx` shell that duplicated it.
 *
 * The KEMETRA visual system comes from the shared tokens, in the same order as
 * `src/main.tsx`: Astryx base CSS, then its KEMETRA overrides, then the Tailwind theme.
 */
import React, { useEffect } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import '@astryxdesign/core/astryx.css';
import '@/shared/theme/astryx-tokens.css';
import '@/shared/theme/index.css';
import { Providers } from '@/app/providers';
import '@/shared/i18n';
import { useSettings } from '@/features/settings/store';
import OverviewPage from '@/features/overview/OverviewPage';
import AgentsPage from '@/features/agents/AgentsPage';
import LiveMapPage from '@/features/live-map/LiveMapPage';
import AnalyticsPage from '@/features/analytics/AnalyticsPage';
import LlmMonitorPage from '@/features/analytics/LlmMonitorPage';

const PAGES = {
  overview: OverviewPage,
  agents: AgentsPage,
  live: LiveMapPage,
  compare: AnalyticsPage,
  llm: LlmMonitorPage,
};

/** The benchmark pages read the backend, not the bundled export. */
function LiveDataMode() {
  const update = useSettings((s) => s.update);
  useEffect(() => update({ dataSource: 'live' }), [update]);
  return null;
}

function View({ tab }) {
  const Page = PAGES[tab] || OverviewPage;
  return (
    <>
      <LiveDataMode />
      <Providers>
        <Page />
      </Providers>
    </>
  );
}

let root = null;

export function mountBenchmarkView(container, tab = 'overview') {
  // The benchmark always renders on the KEMETRA light system, even when the rest of the
  // dashboard is set to the dark control-room theme: the tokens are re-declared for this
  // subtree, so no page here inherits the dark palette.
  container.dataset.theme = 'light';
  container.dataset.astryxTheme = 'kemetra';
  container.classList.add('kemetra-light');
  root = createRoot(container);
  root.render(<View tab={tab} />);
  return () => {
    root?.unmount();
    root = null;
  };
}

/** Switch the rendered page; called by the sidebar's benchmark sub-items. */
export function setBenchmarkTab(tab) {
  root?.render(<View tab={tab || 'overview'} />);
}
