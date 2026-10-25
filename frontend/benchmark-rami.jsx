import React, { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/ibm-plex-sans/400.css';
import '@fontsource/ibm-plex-sans/500.css';
import '@fontsource/ibm-plex-sans/600.css';
import '@fontsource/ibm-plex-mono/400.css';
import '@fontsource/ibm-plex-mono/500.css';
import './src/shared/theme/index.css';
import { Providers } from './src/app/providers.tsx';
import './src/shared/i18n/index.ts';
import { useSettings } from './src/features/settings/store.ts';
import OverviewPage from './src/features/overview/OverviewPage.tsx';
import AgentsPage from './src/features/agents/AgentsPage.tsx';
import LiveMapPage from './src/features/live-map/LiveMapPage.tsx';
import AnalyticsPage from './src/features/analytics/AnalyticsPage.tsx';

const tabs = [['overview', 'Vue d’ensemble'], ['agents', 'Agents RL'], ['live', 'Carte en direct'], ['compare', 'Analyse comparative']];
function LiveDataMode() { const update = useSettings((s) => s.update); useEffect(() => update({ dataSource: 'live' }), [update]); return null; }
function Page({ tab }) { const pages = { overview: OverviewPage, agents: AgentsPage, live: LiveMapPage, compare: AnalyticsPage }; const PageComponent = pages[tab] || OverviewPage; return <><LiveDataMode /><PageComponent /></>; }
function App() {
  const [tab, setTab] = useState('overview');
  return (
    <div className="benchmark-react-shell rami-migrated-shell bg-bg text-text min-h-full">
      <nav className="benchmark-tabs" aria-label="Benchmark sections">
        {tabs.map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`benchmark-tab ${tab === id ? 'is-active' : ''}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </nav>
      <Providers>
        <Page tab={tab} />
      </Providers>
    </div>
  );
}
export function mountRamiBenchmark(container) {
  const root = createRoot(container);
  root.render(<App />);
  return () => root.unmount();
}
