export interface PlayerProjection {
  player_id: number;
  player_name: string;
  team: string;
  position: string;
  opponent: string;
  salary: number;
  projected_fp: number;
  dvp_score: number;
  dvp_grade: string;
  depth_score: number;
  injury_boost: number;
  spot_start_boost: number;
  ownership_pct: number;
  value_score: number;
  fp_per_dollar: number;
  is_spot_starter: boolean;
  is_confirmed_starter: boolean;
  minutes_projection: number;
  injury_status: string;
  last_updated: string | null;
}

export interface SpotStartAlert {
  player_name: string;
  team: string;
  position: string;
  replacing_player: string;
  salary: number;
  projected_minutes: number;
  historical_spot_avg_fp: number;
  spot_start_count: number;
  value_score: number;
  confidence: "Confirmed" | "Expected" | "Probable";
  is_value_play?: boolean;
}

export interface InjuryEntry {
  player_name: string;
  team: string;
  position: string;
  status: string;
  details: string;
  last_updated: string | null;
}

export interface LineupEntry {
  team: string;
  opponent: string;
  PG: string;
  SG: string;
  SF: string;
  PF: string;
  C: string;
  confirmed: boolean;
  last_updated: string | null;
}

export interface DvPEntry {
  team: string;
  position: string;
  avg_fp_allowed: number;
  rank: number;
  games_sampled: number;
}

export interface GameLogEntry {
  date: string;
  opponent: string;
  minutes: number;
  pts: number;
  reb: number;
  ast: number;
  stl: number;
  blk: number;
  tov: number;
  three_pm: number;
  dk_fp: number;
  started: boolean;
}

export type Position = "PG" | "SG" | "SF" | "PF" | "C";
export type SortField = "projected_fp" | "value_score" | "fp_per_dollar" | "salary" | "ownership_pct";
export type DvPGrade = "A" | "B" | "C" | "D" | "F";

export interface WSMessage {
  type: "projections_update" | "spot_start_alert" | "lineup_update" | "injury_update";
  data: Record<string, unknown>;
}
