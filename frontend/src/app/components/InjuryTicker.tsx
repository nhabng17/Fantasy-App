"use client";

import type { InjuryEntry } from "../types";

interface Props {
  injuries: InjuryEntry[];
}

const STATUS_COLORS: Record<string, string> = {
  Out: "text-[var(--accent-red)]",
  Doubtful: "text-[var(--accent-red)]/80",
  GTD: "text-[var(--accent-yellow)]",
  Questionable: "text-[var(--accent-yellow)]",
  Probable: "text-[var(--accent-green)]",
};

export default function InjuryTicker({ injuries }: Props) {
  const significant = injuries.filter((i) =>
    ["Out", "Doubtful", "GTD", "Questionable"].includes(i.status)
  );

  if (significant.length === 0) return null;

  return (
    <div className="bg-[var(--bg-secondary)] border-b border-[var(--border)] px-4 py-2 overflow-hidden">
      <div className="flex items-center gap-4 animate-scroll">
        <span className="text-xs font-bold text-[var(--accent-red)] whitespace-nowrap shrink-0">
          INJURY REPORT
        </span>
        <div className="flex gap-6 overflow-x-auto scrollbar-none">
          {significant.map((inj, i) => (
            <span
              key={`${inj.player_name}-${i}`}
              className="text-xs whitespace-nowrap shrink-0"
            >
              <span className="text-[var(--text-primary)] font-medium">
                {inj.player_name}
              </span>
              <span className="text-[var(--text-muted)]">
                {" "}
                ({inj.team} &middot; {inj.position})
              </span>
              <span className={`font-bold ml-1 ${STATUS_COLORS[inj.status] || ""}`}>
                {inj.status}
              </span>
              {inj.details && (
                <span className="text-[var(--text-muted)] ml-1">
                  - {inj.details}
                </span>
              )}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
