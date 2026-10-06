"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { RaceListItem } from "../../lib/types";
import { fetchRaces } from "../../lib/race-client";

export default function HistoryPage() {
  const [races, setRaces] = useState<RaceListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchRaces(50, 0);
      setRaces(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    async function init() {
      try {
        const data = await fetchRaces(50, 0);
        if (!cancelled) {
          setRaces(data.items);
          setTotal(data.total);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void init();
    return () => {
      cancelled = true;
    };
  }, []);

  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case "completed":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-950/70 text-emerald-300 border border-emerald-800/80">
            ✓ Completed
          </span>
        );
      case "cancelled":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-zinc-800 text-zinc-400 border border-zinc-700">
            ⊘ Cancelled
          </span>
        );
      case "running":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-cyan-950/70 text-cyan-300 border border-cyan-800/80">
            <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-ping mr-1.5" />
            Running
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-zinc-800 text-zinc-400 border border-zinc-700">
            {status}
          </span>
        );
    }
  };

  const formatDate = (isoString: string | null) => {
    if (!isoString) return "—";
    try {
      const d = new Date(isoString);
      return d.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return isoString;
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-screen bg-zinc-950 text-zinc-100">
      {/* Header Bar */}
      <header className="border-b border-zinc-800/80 bg-zinc-900/60 backdrop-blur-md sticky top-0 z-20 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="h-8 w-8 rounded-lg bg-gradient-to-tr from-violet-600 to-cyan-500 flex items-center justify-center font-bold text-white shadow-md shadow-violet-500/20 hover:opacity-90 transition-opacity"
            >
              V
            </Link>
            <div>
              <h1 className="text-lg font-semibold text-zinc-50 leading-none">
                VersusLab
              </h1>
              <p className="text-xs text-zinc-400 mt-0.5">
                Experiment & Evaluation History
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href="/experiments"
              className="px-3.5 py-2 rounded-lg text-sm font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition-colors flex items-center gap-1.5"
            >
              <span className="text-violet-400">⚡</span>
              Experiments
            </Link>
            <Link
              href="/"
              className="px-4 py-2 rounded-lg text-sm font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition-colors flex items-center gap-2"
            >
              ← Back to Arena
            </Link>
            <button
              onClick={loadHistory}
              disabled={loading}
              className="px-4 py-2 rounded-lg text-sm font-medium bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white transition-colors cursor-pointer"
            >
              {loading ? "Refreshing..." : "Refresh"}
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-8 flex flex-col gap-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-zinc-100">Past Races</h2>
            <p className="text-xs text-zinc-400 mt-1">
              Historical races persisted in PostgreSQL with metrics and full model responses.
            </p>
          </div>
          <span className="text-xs font-mono px-3 py-1 rounded bg-zinc-900 border border-zinc-800 text-zinc-400">
            Total: {total}
          </span>
        </div>

        {error && (
          <div className="p-4 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-200 text-sm">
            <p className="font-semibold">Failed to load race history</p>
            <p className="mt-0.5">{error}</p>
          </div>
        )}

        {loading && races.length === 0 ? (
          <div className="border border-dashed border-zinc-800 rounded-xl p-12 text-center text-zinc-500 text-sm">
            Loading past races from database...
          </div>
        ) : races.length === 0 ? (
          <div className="border border-dashed border-zinc-800 rounded-xl p-12 text-center text-zinc-500 text-sm flex flex-col items-center gap-3">
            <div className="h-10 w-10 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center text-lg">
              📜
            </div>
            <div>
              <p className="font-medium text-zinc-300">No race history found</p>
              <p className="text-xs text-zinc-500 mt-0.5">
                Run your first streaming race in the Arena to record results!
              </p>
            </div>
            <Link
              href="/"
              className="mt-2 px-4 py-2 rounded-lg text-xs font-medium bg-violet-600 hover:bg-violet-500 text-white"
            >
              Go to Arena
            </Link>
          </div>
        ) : (
          <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-xl overflow-hidden shadow-sm">
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-zinc-900/90 text-zinc-400 uppercase tracking-wider font-semibold border-b border-zinc-800 text-[11px]">
                  <tr>
                    <th className="px-5 py-3.5">Race ID</th>
                    <th className="px-5 py-3.5">Prompt</th>
                    <th className="px-5 py-3.5">Contenders</th>
                    <th className="px-5 py-3.5">Status</th>
                    <th className="px-5 py-3.5">Created At</th>
                    <th className="px-5 py-3.5 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60 font-sans text-zinc-300">
                  {races.map((race) => (
                    <tr
                      key={race.id}
                      className="hover:bg-zinc-800/30 transition-colors"
                    >
                      <td className="px-5 py-4 font-mono text-zinc-400">
                        <Link
                          href={`/history/${race.id}`}
                          className="hover:text-violet-400 transition-colors underline decoration-zinc-700 underline-offset-2"
                        >
                          {race.id.slice(0, 10)}…
                        </Link>
                      </td>
                      <td className="px-5 py-4 max-w-md">
                        <p className="truncate text-zinc-200" title={race.prompt}>
                          {race.prompt}
                        </p>
                      </td>
                      <td className="px-5 py-4">
                        <span className="px-2 py-0.5 rounded bg-zinc-800 border border-zinc-700 font-mono text-[11px] text-zinc-300">
                          {race.model_count} models
                        </span>
                      </td>
                      <td className="px-5 py-4">{getStatusBadge(race.status)}</td>
                      <td className="px-5 py-4 text-zinc-400 font-mono text-[11px]">
                        {formatDate(race.created_at)}
                      </td>
                      <td className="px-5 py-4 text-right">
                        <Link
                          href={`/history/${race.id}`}
                          className="px-3 py-1.5 rounded bg-zinc-800 hover:bg-violet-600 hover:text-white border border-zinc-700 hover:border-violet-500 text-zinc-200 transition-all text-xs inline-flex items-center gap-1"
                        >
                          View Detail →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>

      <footer className="border-t border-zinc-800/60 py-3 px-6 text-center text-xs text-zinc-600">
        VersusLab Phase 5 • PostgreSQL Persistence & History
      </footer>
    </div>
  );
}
