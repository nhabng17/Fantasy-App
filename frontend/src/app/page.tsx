"use client";

import { useProjections } from "./hooks/useProjections";
import SpotStartAlerts from "./components/SpotStartAlert";
import PlayerTable from "./components/PlayerTable";
import InjuryTicker from "./components/InjuryTicker";
import LineupCards from "./components/LineupCard";
import DvPChart from "./components/DvPChart";

export default function Dashboard() {
  const {
    projections,
    spotStarts,
    injuries,
    lineups,
    loading,
    error,
    lastUpdate,
    newAlert,
    refresh,
  } = useProjections();

  return (
    <div className="min-h-screen flex flex-col">
      {/* Injury Ticker */}
      <InjuryTicker injuries={injuries} />

      {/* Header */}
      <header className="border-b border-[var(--border)] bg-[var(--bg-secondary)]">
        <div className="max-w-7xl mx-auto px-4 py-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-[var(--text-primary)]">
              Fantasy Basketball Predictor
            </h1>
            <p className="text-sm text-[var(--text-muted)]">
              DraftKings Projections &middot; DvP &middot; Spot Starts &middot;
              Real-Time Lineups
            </p>
          </div>
          <div className="flex items-center gap-4">
            {lastUpdate && (
              <span className="text-xs text-[var(--text-muted)]">
                Updated{" "}
                {lastUpdate.toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </span>
            )}
            <button
              onClick={refresh}
              disabled={loading}
              className="px-4 py-2 rounded-lg bg-[var(--accent-blue)] text-white text-sm font-medium hover:bg-[var(--accent-blue)]/80 disabled:opacity-50 transition-colors"
            >
              {loading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 py-6">
        {error && (
          <div className="mb-6 p-4 rounded-lg bg-[var(--accent-red)]/10 border border-[var(--accent-red)]/30 text-[var(--accent-red)] text-sm">
            {error}
          </div>
        )}

        {/* Spot Start Alerts -- most prominent section */}
        <SpotStartAlerts spotStarts={spotStarts} newAlert={newAlert} />

        {/* Starting Lineups */}
        <LineupCards lineups={lineups} />

        {/* DvP Heatmap */}
        <DvPChart />

        {/* Main Projections Table */}
        <div className="mb-4">
          <h2 className="text-lg font-bold text-[var(--text-primary)] mb-3">
            Player Projections
          </h2>
        </div>
        <PlayerTable projections={projections} />
      </main>

      {/* Footer */}
      <footer className="border-t border-[var(--border)] bg-[var(--bg-secondary)] py-4">
        <div className="max-w-7xl mx-auto px-4 text-center text-xs text-[var(--text-muted)]">
          Data refreshes automatically. Lineups update every 5 min. Injuries every 15 min. Stats every 2 hours.
        </div>
      </footer>
    </div>
  );
}
