"use client";

import type { LineupEntry } from "../types";

interface Props {
  lineups: LineupEntry[];
}

const POSITIONS = ["PG", "SG", "SF", "PF", "C"] as const;

export default function LineupCards({ lineups }: Props) {
  if (lineups.length === 0) return null;

  return (
    <section className="mb-6">
      <h2 className="text-lg font-bold text-[var(--text-primary)] mb-3">
        Starting Lineups
      </h2>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {lineups.map((lineup) => (
          <GameLineupCard key={lineup.team} lineup={lineup} />
        ))}
      </div>
    </section>
  );
}

function GameLineupCard({ lineup }: { lineup: LineupEntry }) {
  return (
    <div
      className={`rounded-lg border p-3 ${
        lineup.confirmed
          ? "border-[var(--accent-green)]/30 bg-[var(--bg-card)]"
          : "border-[var(--border)] bg-[var(--bg-card)] opacity-75"
      }`}
    >
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="font-bold text-sm text-[var(--text-primary)]">
            {lineup.team}
          </span>
          <span className="text-xs text-[var(--text-muted)]">
            vs {lineup.opponent}
          </span>
        </div>
        {lineup.confirmed ? (
          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[var(--accent-green)]/20 text-[var(--accent-green)]">
            CONFIRMED
          </span>
        ) : (
          <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[var(--accent-yellow)]/20 text-[var(--accent-yellow)]">
            EXPECTED
          </span>
        )}
      </div>
      <div className="space-y-1">
        {POSITIONS.map((pos) => {
          const player = lineup[pos];
          return (
            <div
              key={pos}
              className="flex items-center gap-2 text-xs"
            >
              <span className="w-6 text-[var(--text-muted)] font-mono">
                {pos}
              </span>
              <span className="text-[var(--text-primary)]">
                {player || "TBD"}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
