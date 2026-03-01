"use client";

import { useState, useEffect, useCallback, useRef } from "react";
import type {
  PlayerProjection,
  SpotStartAlert,
  InjuryEntry,
  LineupEntry,
  WSMessage,
} from "../types";

const API_BASE = "/api";

function getWsUrl(): string {
  if (typeof window !== "undefined") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/api/ws/projections`;
  }
  return "ws://localhost:8000/api/ws/projections";
}

export function useProjections() {
  const [projections, setProjections] = useState<PlayerProjection[]>([]);
  const [spotStarts, setSpotStarts] = useState<SpotStartAlert[]>([]);
  const [injuries, setInjuries] = useState<InjuryEntry[]>([]);
  const [lineups, setLineups] = useState<LineupEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null);
  const [newAlert, setNewAlert] = useState<SpotStartAlert | null>(null);
  const [syncing, setSyncing] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [projRes, spotRes, injRes, lineupRes] = await Promise.all([
        fetch(`${API_BASE}/projections?limit=100`),
        fetch(`${API_BASE}/spot-starts`),
        fetch(`${API_BASE}/injuries`),
        fetch(`${API_BASE}/lineups`),
      ]);

      if (projRes.ok) setProjections(await projRes.json());
      if (spotRes.ok) setSpotStarts(await spotRes.json());
      if (injRes.ok) setInjuries(await injRes.json());
      if (lineupRes.ok) setLineups(await lineupRes.json());

      setLastUpdate(new Date());
      setError(null);
    } catch (err) {
      setError("Failed to fetch data. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }, []);

  const connectWebSocket = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    const ws = new WebSocket(getWsUrl());
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const message: WSMessage = JSON.parse(event.data);

        switch (message.type) {
          case "projections_update":
            setProjections(
              (message.data as { projections: PlayerProjection[] }).projections
            );
            setLastUpdate(new Date());
            break;

          case "spot_start_alert": {
            const spot = message.data as unknown as SpotStartAlert;
            setSpotStarts((prev) => {
              const exists = prev.some(
                (s) => s.player_name === spot.player_name
              );
              return exists
                ? prev.map((s) =>
                    s.player_name === spot.player_name ? spot : s
                  )
                : [spot, ...prev];
            });
            setNewAlert(spot);
            setTimeout(() => setNewAlert(null), 10000);
            break;
          }

          case "lineup_update": {
            const lineup = message.data as unknown as LineupEntry;
            setLineups((prev) => {
              const exists = prev.some((l) => l.team === lineup.team);
              return exists
                ? prev.map((l) => (l.team === lineup.team ? lineup : l))
                : [...prev, lineup];
            });
            break;
          }

          case "injury_update": {
            const injury = message.data as unknown as InjuryEntry;
            setInjuries((prev) => {
              const exists = prev.some(
                (i) => i.player_name === injury.player_name
              );
              return exists
                ? prev.map((i) =>
                    i.player_name === injury.player_name ? injury : i
                  )
                : [injury, ...prev];
            });
            break;
          }
        }
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      setTimeout(connectWebSocket, 5000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }, []);

  useEffect(() => {
    fetchData();
    connectWebSocket();

    return () => {
      wsRef.current?.close();
    };
  }, [fetchData, connectWebSocket]);

  const syncData = useCallback(async () => {
    try {
      setSyncing(true);
      setError(null);
      const res = await fetch(`${API_BASE}/refresh`, { method: "POST" });
      if (!res.ok) throw new Error("Sync failed");

      const pollUntilDone = async () => {
        let prevCount = 0;
        let stableChecks = 0;
        for (let i = 0; i < 40; i++) {
          await new Promise((r) => setTimeout(r, 5000));
          const healthRes = await fetch(`${API_BASE}/health`);
          if (!healthRes.ok) continue;
          const health = await healthRes.json();
          const total = Object.values(health.db_counts as Record<string, number>).reduce((a, b) => a + b, 0);
          if (total > 0 && total === prevCount) {
            stableChecks++;
            if (stableChecks >= 2) break;
          } else {
            stableChecks = 0;
          }
          prevCount = total;
        }
      };

      await pollUntilDone();
      await fetchData();
    } catch {
      setError("Data sync failed. Check backend logs.");
    } finally {
      setSyncing(false);
    }
  }, [fetchData]);

  return {
    projections,
    spotStarts,
    injuries,
    lineups,
    loading,
    error,
    lastUpdate,
    newAlert,
    syncing,
    refresh: fetchData,
    syncData,
  };
}
