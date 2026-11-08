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
import UnifiedModelsRunsPage from '@/features/models/UnifiedModelsRunsPage';
import FreshCompare from '@/features/analytics/FreshCompare';
import TrainingPage from '@/features/training/TrainingPage';

/* One page per sidebar sub-item — the sidebar is the only tab control. */
const PAGES = {
  models: UnifiedModelsRunsPage,
  training: TrainingPage,
  compare: FreshCompare,
};

/** The benchmark pages read the backend, not the bundled export. */
function LiveDataMode() {
  const update = useSettings((s) => s.update);
  useEffect(() => update({ dataSource: 'live' }), [update]);
  return null;
}

function View({ tab }) {
  const Page = PAGES[tab] || UnifiedModelsRunsPage;
  return (
    <>
      <LiveDataMode />
      <Providers>
        <Page key={tab} />
      </Providers>
    </>
  );
}

let root = null;

export function mountBenchmarkView(container, tab = 'models') {
  container.dataset.theme = 'light';
  container.dataset.astryxTheme = 'kemetra';
  container.classList.add('kemetra-light');
  root = createRoot(container);
  root.render(<View tab={tab} />);
}

/** Switch the rendered page; called by the sidebar's benchmark sub-items. */
export function setBenchmarkTab(tab) {
  root?.render(<View tab={tab || 'models'} />);
}
