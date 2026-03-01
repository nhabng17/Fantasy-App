"use client";

import { useState, useEffect } from "react";
import type { DvPEntry } from "../types";

const POSITIONS = ["PG", "SG", "SF", "PF", "C"] as const;

export default function DvPChart() {
  const [dvpData, setDvpData] = useState<DvPEntry[]>([]);
  const [selectedPos, setSelectedPos] = useState<string>("PG");

  useEffect(() => {
    fetch("/api/dvp")
      .then((r) => r.json())
      .then(setDvpData)
      .catch(() => {});
  }, []);

  const filtered = dvpData
    .filter((d) => d.position === selectedPos)
    .sort((a, b) => b.avg_fp_allowed - a.avg_fp_allowed);

  if (dvpData.length === 0) return null;

  return (
    <section className="mb-6">
      <div className="flex items-center gap-3 mb-3">
        <h2 className="text-lg font-bold text-[var(--text-primary)]">
          Defense vs Position
        </h2>
        <div className="flex rounded-lg bg-[var(--bg-secondary)] p-0.5 gap-0.5">
          {POSITIONS.map((pos) => (
            <button
              key={pos}
              onClick={() => setSelectedPos(pos)}
              className={`px-2.5 py-1 rounded-md text-xs font-medium transition-colors ${
                selectedPos === pos
                  ? "bg-[var(--accent-purple)] text-white"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              {pos}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-2">
        {filtered.slice(0, 10).map((d, i) => {
          const isSmash = i < 5;
          return (
            <div
              key={d.team}
              className={`rounded-lg p-3 text-center border ${
                isSmash
                  ? "border-[var(--accent-green)]/20 bg-[var(--accent-green)]/5"
                  : "border-[var(--border)] bg-[var(--bg-card)]"
              }`}
            >
              <div className="font-bold text-sm text-[var(--text-primary)]">
                {d.team}
              </div>
              <div
                className={`text-lg font-bold font-mono ${
                  isSmash
                    ? "text-[var(--accent-green)]"
                    : "text-[var(--text-secondary)]"
                }`}
              >
                {d.avg_fp_allowed.toFixed(1)}
              </div>
              <div className="text-[10px] text-[var(--text-muted)]">
                FP allowed
              </div>
              {isSmash && (
                <div className="text-[10px] font-bold text-[var(--accent-green)] mt-1">
                  SMASH SPOT
                </div>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
