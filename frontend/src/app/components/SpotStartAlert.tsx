"use client";

import type { SpotStartAlert as SpotStartType } from "../types";

interface Props {
  spotStarts: SpotStartType[];
  newAlert: SpotStartType | null;
}

export default function SpotStartAlerts({ spotStarts, newAlert }: Props) {
  if (spotStarts.length === 0) return null;

  return (
    <section className="mb-6">
      <div className="flex items-center gap-2 mb-3">
        <div className="w-2 h-2 rounded-full bg-[var(--accent-green)] animate-pulse" />
        <h2 className="text-lg font-bold text-[var(--text-primary)]">
          Spot Start Alerts
        </h2>
        <span className="text-sm text-[var(--text-muted)]">
          ({spotStarts.length} detected)
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {spotStarts.map((spot) => (
          <SpotStartCard
            key={`${spot.player_name}-${spot.team}`}
            spot={spot}
            isNew={newAlert?.player_name === spot.player_name}
          />
        ))}
      </div>
    </section>
  );
}

function SpotStartCard({
  spot,
  isNew,
}: {
  spot: SpotStartType;
  isNew: boolean;
}) {
  const isValuePlay = spot.salary <= 4500 && spot.historical_spot_avg_fp >= 20;

  return (
    <div
      className={`
        rounded-lg border p-4 transition-all
        ${isNew ? "spot-start-pulse border-[var(--accent-green)]" : "border-[var(--border)]"}
        ${isValuePlay ? "bg-gradient-to-br from-[var(--bg-card)] to-[#1a1f10]" : "bg-[var(--bg-card)]"}
        hover:border-[var(--accent-green)]/50
      `}
    >
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-bold text-[var(--text-primary)]">
              {spot.player_name}
            </span>
            <ConfidenceBadge confidence={spot.confidence} />
          </div>
          <div className="text-sm text-[var(--text-secondary)]">
            {spot.team} &middot; {spot.position}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          {isValuePlay && (
            <span className="text-xs font-bold px-2 py-0.5 rounded-full bg-[var(--accent-gold)]/20 text-[var(--accent-gold)] border border-[var(--accent-gold)]/30">
              VALUE PLAY
            </span>
          )}
          <span className="text-xs px-2 py-0.5 rounded bg-[var(--accent-green)]/20 text-[var(--accent-green)] font-semibold">
            SPOT START
          </span>
        </div>
      </div>

      {spot.replacing_player && (
        <div className="text-xs text-[var(--text-muted)] mb-3">
          Starting for{" "}
          <span className="text-[var(--accent-red)]">
            {spot.replacing_player}
          </span>{" "}
          (OUT)
        </div>
      )}

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
        <Stat label="Salary" value={`$${spot.salary.toLocaleString()}`} highlight={spot.salary <= 4500} />
        <Stat label="Proj Min" value={spot.projected_minutes.toFixed(1)} />
        <Stat label="Spot Avg FP" value={spot.historical_spot_avg_fp.toFixed(1)} highlight={spot.historical_spot_avg_fp >= 25} />
        <Stat label="Prior Spots" value={String(spot.spot_start_count)} />
        <Stat label="Value" value={spot.value_score.toFixed(1) + "x"} highlight={spot.value_score >= 5} />
      </div>
    </div>
  );
}

function Stat({
  label,
  value,
  highlight = false,
}: {
  label: string;
  value: string;
  highlight?: boolean;
}) {
  return (
    <div className="flex justify-between">
      <span className="text-[var(--text-muted)]">{label}</span>
      <span
        className={
          highlight
            ? "font-semibold text-[var(--accent-green)]"
            : "text-[var(--text-primary)]"
        }
      >
        {value}
      </span>
    </div>
  );
}

function ConfidenceBadge({
  confidence,
}: {
  confidence: "Confirmed" | "Expected" | "Probable";
}) {
  const colors = {
    Confirmed: "bg-[var(--accent-green)]/20 text-[var(--accent-green)] border-[var(--accent-green)]/30",
    Expected: "bg-[var(--accent-yellow)]/20 text-[var(--accent-yellow)] border-[var(--accent-yellow)]/30",
    Probable: "bg-[var(--accent-blue)]/20 text-[var(--accent-blue)] border-[var(--accent-blue)]/30",
  };

  return (
    <span
      className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${colors[confidence]}`}
    >
      {confidence.toUpperCase()}
    </span>
  );
}
