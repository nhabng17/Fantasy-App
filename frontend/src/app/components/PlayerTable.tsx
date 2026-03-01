"use client";

import { useState } from "react";
import type { PlayerProjection, Position, SortField } from "../types";

interface Props {
  projections: PlayerProjection[];
}

const POSITIONS: (Position | "ALL")[] = ["ALL", "PG", "SG", "SF", "PF", "C"];

const SORT_OPTIONS: { value: SortField; label: string }[] = [
  { value: "projected_fp", label: "Projected FP" },
  { value: "value_score", label: "Value (FP/$1K)" },
  { value: "fp_per_dollar", label: "FP per $" },
  { value: "salary", label: "Salary" },
  { value: "ownership_pct", label: "Ownership %" },
];

export default function PlayerTable({ projections }: Props) {
  const [position, setPosition] = useState<Position | "ALL">("ALL");
  const [sortBy, setSortBy] = useState<SortField>("projected_fp");
  const [spotStartsOnly, setSpotStartsOnly] = useState(false);
  const [minPriceOnly, setMinPriceOnly] = useState(false);

  const filtered = projections
    .filter((p) => position === "ALL" || p.position === position)
    .filter((p) => !spotStartsOnly || p.is_spot_starter)
    .filter((p) => !minPriceOnly || p.salary <= 4500)
    .sort((a, b) => {
      const aVal = a[sortBy];
      const bVal = b[sortBy];
      return sortBy === "salary"
        ? (aVal as number) - (bVal as number)
        : (bVal as number) - (aVal as number);
    });

  return (
    <section>
      {/* Controls */}
      <div className="flex flex-wrap items-center gap-3 mb-4">
        {/* Position Tabs */}
        <div className="flex rounded-lg bg-[var(--bg-secondary)] p-1 gap-0.5">
          {POSITIONS.map((pos) => (
            <button
              key={pos}
              onClick={() => setPosition(pos)}
              className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${
                position === pos
                  ? "bg-[var(--accent-blue)] text-white"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              {pos}
            </button>
          ))}
        </div>

        {/* Sort */}
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as SortField)}
          className="bg-[var(--bg-secondary)] text-[var(--text-primary)] border border-[var(--border)] rounded-lg px-3 py-1.5 text-sm"
        >
          {SORT_OPTIONS.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>

        {/* Toggle Filters */}
        <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)] cursor-pointer">
          <input
            type="checkbox"
            checked={spotStartsOnly}
            onChange={(e) => setSpotStartsOnly(e.target.checked)}
            className="accent-[var(--accent-green)]"
          />
          Spot Starts Only
        </label>

        <label className="flex items-center gap-2 text-sm text-[var(--text-secondary)] cursor-pointer">
          <input
            type="checkbox"
            checked={minPriceOnly}
            onChange={(e) => setMinPriceOnly(e.target.checked)}
            className="accent-[var(--accent-gold)]"
          />
          Min Price Only
        </label>

        <span className="ml-auto text-sm text-[var(--text-muted)]">
          {filtered.length} players
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-[var(--border)]">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[var(--bg-secondary)] text-[var(--text-muted)] text-xs uppercase tracking-wider">
              <th className="text-left px-4 py-3 sticky left-0 bg-[var(--bg-secondary)]">Player</th>
              <th className="text-center px-3 py-3">Pos</th>
              <th className="text-center px-3 py-3">Matchup</th>
              <th className="text-center px-3 py-3">DvP</th>
              <th className="text-right px-3 py-3">Salary</th>
              <th className="text-right px-3 py-3">Proj FP</th>
              <th className="text-right px-3 py-3">FP/$1K</th>
              <th className="text-right px-3 py-3">FP/$</th>
              <th className="text-right px-3 py-3">Own %</th>
              <th className="text-right px-3 py-3">Min</th>
              <th className="text-center px-3 py-3">Status</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((p) => (
              <PlayerRow key={p.player_id} projection={p} />
            ))}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={11} className="text-center py-8 text-[var(--text-muted)]">
                  No players match your filters
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PlayerRow({ projection: p }: { projection: PlayerProjection }) {
  return (
    <tr className="border-t border-[var(--border)] hover:bg-[var(--bg-hover)] transition-colors">
      <td className="px-4 py-3 sticky left-0 bg-[var(--bg-primary)]">
        <div className="flex items-center gap-2">
          <span className="font-medium text-[var(--text-primary)]">
            {p.player_name}
          </span>
          {p.is_spot_starter && (
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[var(--accent-green)]/20 text-[var(--accent-green)]">
              SPOT
            </span>
          )}
          {p.injury_status && (
            <InjuryBadge status={p.injury_status} />
          )}
        </div>
        <div className="text-xs text-[var(--text-muted)]">{p.team}</div>
      </td>
      <td className="text-center px-3 py-3 text-[var(--text-secondary)]">
        {p.position}
      </td>
      <td className="text-center px-3 py-3 text-[var(--text-secondary)]">
        {p.opponent ? `vs ${p.opponent}` : "-"}
      </td>
      <td className="text-center px-3 py-3">
        <DvPBadge grade={p.dvp_grade} />
      </td>
      <td className="text-right px-3 py-3 font-mono text-[var(--text-primary)]">
        {p.salary > 0 ? `$${p.salary.toLocaleString()}` : "-"}
      </td>
      <td className="text-right px-3 py-3 font-mono font-semibold text-[var(--text-primary)]">
        {p.projected_fp.toFixed(1)}
      </td>
      <td className="text-right px-3 py-3 font-mono">
        <span
          className={
            p.value_score >= 5
              ? "text-[var(--accent-green)] font-semibold"
              : "text-[var(--text-secondary)]"
          }
        >
          {p.value_score > 0 ? `${p.value_score.toFixed(1)}x` : "-"}
        </span>
      </td>
      <td className="text-right px-3 py-3 font-mono">
        <span
          className={
            p.fp_per_dollar >= 0.006
              ? "text-[var(--accent-green)] font-semibold"
              : "text-[var(--text-secondary)]"
          }
        >
          {p.fp_per_dollar > 0 ? p.fp_per_dollar.toFixed(4) : "-"}
        </span>
      </td>
      <td className="text-right px-3 py-3 font-mono text-[var(--text-secondary)]">
        {p.ownership_pct > 0 ? `${p.ownership_pct.toFixed(1)}%` : "-"}
      </td>
      <td className="text-right px-3 py-3 font-mono text-[var(--text-secondary)]">
        {p.minutes_projection.toFixed(0)}
      </td>
      <td className="text-center px-3 py-3">
        <StarterBadge
          isConfirmed={p.is_confirmed_starter}
          isSpot={p.is_spot_starter}
        />
      </td>
    </tr>
  );
}

function DvPBadge({ grade }: { grade: string }) {
  const colorMap: Record<string, string> = {
    A: "text-[var(--grade-a)] bg-[var(--grade-a)]/15",
    B: "text-[var(--grade-b)] bg-[var(--grade-b)]/15",
    C: "text-[var(--grade-c)] bg-[var(--grade-c)]/15",
    D: "text-[var(--grade-d)] bg-[var(--grade-d)]/15",
    F: "text-[var(--grade-f)] bg-[var(--grade-f)]/15",
  };

  return (
    <span
      className={`inline-block w-7 text-center text-xs font-bold rounded py-0.5 ${colorMap[grade] || ""}`}
    >
      {grade}
    </span>
  );
}

function InjuryBadge({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    GTD: "bg-yellow-500/20 text-yellow-400 border-yellow-500/30",
    Probable: "bg-green-500/20 text-green-400 border-green-500/30",
  };
  const classes = colorMap[status] || "bg-red-500/20 text-red-400 border-red-500/30";
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border ${classes}`}>
      {status.toUpperCase()}
    </span>
  );
}

function StarterBadge({
  isConfirmed,
  isSpot,
}: {
  isConfirmed: boolean;
  isSpot: boolean;
}) {
  if (isSpot) {
    return (
      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[var(--accent-green)]/20 text-[var(--accent-green)] border border-[var(--accent-green)]/30">
        SPOT
      </span>
    );
  }
  if (isConfirmed) {
    return (
      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-[var(--accent-blue)]/20 text-[var(--accent-blue)]">
        START
      </span>
    );
  }
  return (
    <span className="text-[10px] px-1.5 py-0.5 rounded text-[var(--text-muted)]">
      -
    </span>
  );
}
