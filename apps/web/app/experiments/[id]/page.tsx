"use client";

import React, { useEffect, useState, use } from "react";
import Link from "next/link";
import {
  ExperimentResultsResponse,
  ModelComparisonStats,
  ParetoPoint,
} from "../../../lib/types";
import {
  fetchExperimentResults,
  fetchExperimentStatus,
} from "../../../lib/race-client";

interface PageProps {
  params: Promise<{ id: string }>;
}

export default function ExperimentDetailPage({ params }: PageProps) {
  const resolvedParams = use(params);
  const experimentId = resolvedParams.id;

  const [results, setResults] = useState<ExperimentResultsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Status and Progress Polling
  const [pollProgress, setPollProgress] = useState<{
    status: string;
    completed: number;
    total: number;
  }>({ status: "pending", completed: 0, total: 0 });

  useEffect(() => {
    let timer: NodeJS.Timeout | null = null;

    async function checkStatusAndResults() {
      try {
        const stat = await fetchExperimentStatus(experimentId);
        setPollProgress({
          status: stat.status,
          completed: stat.completed_cases,
          total: stat.total_cases,
        });

        if (stat.status === "completed" || stat.status === "failed") {
          const res = await fetchExperimentResults(experimentId);
          setResults(res);
          setLoading(false);
          return;
        }

        // Keep polling while running
        timer = setTimeout(checkStatusAndResults, 2000);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
        setLoading(false);
      }
    }

    checkStatusAndResults();

    return () => {
      if (timer) clearTimeout(timer);
    };
  }, [experimentId]);

  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case "completed":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-950/70 text-emerald-300 border border-emerald-800/80">
            ✓ Completed
          </span>
        );
      case "running":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-cyan-950/70 text-cyan-300 border border-cyan-800/80 animate-pulse">
            ⚡ Running
          </span>
        );
      case "failed":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-rose-950/70 text-rose-300 border border-rose-800/80">
            ✕ Failed
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

  const formatDate = (isoString: string | null | undefined) => {
    if (!isoString) return "—";
    try {
      const d = new Date(isoString);
      return d.toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return isoString;
    }
  };

  // Helper for rendering the Pareto Scatter Chart
  const renderParetoChart = (points: ParetoPoint[]) => {
    if (!points || points.length === 0) return null;

    const width = 680;
    const height = 300;
    const padding = 55;

    // X: Total Cost (dollars)
    const maxCost = Math.max(...points.map((p) => p.total_cost), 0.0001);
    // Y: Quality Score (0 to 1)
    const maxQuality = 1.0;

    const getX = (cost: number) =>
      padding + (cost / maxCost) * (width - 2 * padding);
    const getY = (quality: number) =>
      height - padding - (quality / maxQuality) * (height - 2 * padding);

    const colors = [
      "#8b5cf6", // violet
      "#06b6d4", // cyan
      "#10b981", // emerald
      "#f59e0b", // amber
      "#ec4899", // pink
      "#3b82f6", // blue
    ];

    return (
      <div className="w-full overflow-x-auto bg-zinc-950/60 p-4 rounded-xl border border-zinc-800/70 flex flex-col items-center">
        <svg
          viewBox={`0 0 ${width} ${height}`}
          className="w-full max-w-2xl h-auto font-mono text-[11px]"
        >
          {/* Grid lines */}
          <line
            x1={padding}
            y1={padding}
            x2={padding}
            y2={height - padding}
            stroke="#27272a"
            strokeWidth="1.5"
          />
          <line
            x1={padding}
            y1={height - padding}
            x2={width - padding}
            y2={height - padding}
            stroke="#27272a"
            strokeWidth="1.5"
          />

          {/* Intermediate horizontal grid lines (0.25, 0.5, 0.75, 1.0) */}
          {[0.25, 0.5, 0.75, 1.0].map((q) => {
            const y = getY(q);
            return (
              <g key={q}>
                <line
                  x1={padding}
                  y1={y}
                  x2={width - padding}
                  y2={y}
                  stroke="#18181b"
                  strokeDasharray="4 4"
                />
                <text
                  x={padding - 10}
                  y={y + 3}
                  textAnchor="end"
                  fill="#71717a"
                  fontSize="10"
                >
                  {(q * 100).toFixed(0)}%
                </text>
              </g>
            );
          })}

          {/* X Axis Labels */}
          <text
            x={padding}
            y={height - padding + 18}
            textAnchor="middle"
            fill="#71717a"
            fontSize="10"
          >
            $0.00
          </text>
          <text
            x={width - padding}
            y={height - padding + 18}
            textAnchor="middle"
            fill="#71717a"
            fontSize="10"
          >
            ${maxCost.toFixed(5)}
          </text>

          {/* Axis Titles */}
          <text
            x={width / 2}
            y={height - 10}
            textAnchor="middle"
            fill="#a1a1aa"
            fontSize="11"
            fontFamily="sans-serif"
          >
            Total Financial Cost (USD) →
          </text>
          <text
            x={-height / 2}
            y={15}
            transform="rotate(-90)"
            textAnchor="middle"
            fill="#a1a1aa"
            fontSize="11"
            fontFamily="sans-serif"
          >
            Quality Score (Exact Match / Faithfulness) →
          </text>

          {/* Pareto Points */}
          {points.map((pt, idx) => {
            const cx = getX(pt.total_cost);
            const cy = getY(pt.quality_score);
            const color = colors[idx % colors.length];

            return (
              <g key={pt.model_id} className="group cursor-pointer">
                <circle
                  cx={cx}
                  cy={cy}
                  r={6}
                  fill={color}
                  stroke="#ffffff"
                  strokeWidth="1.5"
                  className="transition-all hover:scale-125"
                />
                <text
                  x={cx + 9}
                  y={cy + 3}
                  fill="#e4e4e7"
                  fontSize="10"
                  fontWeight="600"
                >
                  {pt.model_id.split(":")[1] || pt.model_id}
                </text>
                <title>{`${pt.model_id}: ${(pt.quality_score * 100).toFixed(1)}% quality, $${pt.total_cost.toFixed(6)} cost, ${(pt.mean_latency_ms / 1000).toFixed(2)}s latency`}</title>
              </g>
            );
          })}
        </svg>
        <p className="text-[11px] text-zinc-500 mt-2">
          Hover over points to inspect tradeoffs. High-quality, low-cost models sit towards the top-left Pareto frontier.
        </p>
      </div>
    );
  };

  return (
    <div className="flex-1 flex flex-col min-h-screen bg-zinc-950 text-zinc-100 font-sans">
      {/* Header Bar */}
      <header className="border-b border-zinc-800/80 bg-zinc-900/60 backdrop-blur-md sticky top-0 z-20 px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Link
              href="/"
              className="h-8 w-8 rounded-lg bg-gradient-to-tr from-violet-600 to-cyan-500 flex items-center justify-center font-bold text-white shadow-md shadow-violet-500/20"
            >
              V
            </Link>
            <div>
              <h1 className="text-lg font-semibold text-zinc-50 leading-none">
                VersusLab
              </h1>
              <p className="text-xs text-zinc-400 mt-0.5">
                Experiment Comparison Dashboard
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Link
              href="/experiments"
              className="px-4 py-2 rounded-lg text-sm font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition-colors flex items-center gap-2"
            >
              ← All Experiments
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-8 flex flex-col gap-6">
        {error && (
          <div className="p-4 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-200 text-sm">
            <p className="font-semibold">Error loading experiment</p>
            <p className="mt-0.5">{error}</p>
          </div>
        )}

        {/* Progress Card while Running */}
        {pollProgress.status === "running" && (
          <section className="bg-cyan-950/30 border border-cyan-800/60 rounded-xl p-6 shadow-sm space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="animate-spin inline-block w-4 h-4 border-2 border-cyan-400 border-t-transparent rounded-full" />
                <h2 className="text-sm font-semibold text-cyan-200">
                  Experiment Running Across Benchmark Cases...
                </h2>
              </div>
              <span className="text-xs font-mono text-cyan-400">
                {pollProgress.completed} / {pollProgress.total} completed
              </span>
            </div>

            <div className="w-full bg-zinc-900 rounded-full h-2.5 overflow-hidden border border-zinc-800">
              <div
                className="bg-gradient-to-r from-cyan-500 to-violet-500 h-2.5 rounded-full transition-all duration-500"
                style={{
                  width: `${
                    pollProgress.total > 0
                      ? (pollProgress.completed / pollProgress.total) * 100
                      : 10
                  }%`,
                }}
              />
            </div>
            <p className="text-xs text-zinc-400">
              Races are executed sequentially across cases with concurrency enforcement. This page will automatically update once all runs complete.
            </p>
          </section>
        )}

        {loading && pollProgress.status !== "running" ? (
          <div className="border border-dashed border-zinc-800 rounded-xl p-12 text-center text-zinc-500 text-sm">
            Loading experiment results...
          </div>
        ) : results ? (
          <>
            {/* Overview Card */}
            <section className="bg-zinc-900/40 border border-zinc-800/80 rounded-xl p-6 shadow-sm space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800/70 pb-4">
                <div>
                  <span className="text-xs font-mono text-zinc-500">EXPERIMENT ID</span>
                  <h2 className="text-base font-bold text-zinc-100 mt-0.5">
                    {results.name}
                  </h2>
                </div>
                <div className="flex items-center gap-3">
                  {getStatusBadge(results.status)}
                  <span className="text-xs font-mono px-2.5 py-1 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                    {results.models_stats.length} contenders
                  </span>
                </div>
              </div>

              {/* Metadata Grid */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-xs font-mono text-zinc-400 pt-1">
                <div className="bg-zinc-950/50 p-3 rounded-lg border border-zinc-800/50">
                  <span className="text-zinc-500 block text-[11px]">Dataset</span>
                  <span className="text-zinc-200 font-semibold truncate block">
                    {results.dataset_name} v{results.dataset_version}
                  </span>
                </div>
                <div className="bg-zinc-950/50 p-3 rounded-lg border border-zinc-800/50">
                  <span className="text-zinc-500 block text-[11px]">Cases Evaluated</span>
                  <span className="text-zinc-200 font-semibold">
                    {results.total_cases}
                  </span>
                </div>
                <div className="bg-zinc-950/50 p-3 rounded-lg border border-zinc-800/50">
                  <span className="text-zinc-500 block text-[11px]">Git Commit</span>
                  <span className="text-cyan-400 font-semibold">
                    {results.git_commit ? results.git_commit.slice(0, 7) : "—"}
                  </span>
                </div>
                <div className="bg-zinc-950/50 p-3 rounded-lg border border-zinc-800/50">
                  <span className="text-zinc-500 block text-[11px]">Created At</span>
                  <span className="text-zinc-300 font-semibold">
                    {formatDate(results.created_at)}
                  </span>
                </div>
                <div className="bg-zinc-950/50 p-3 rounded-lg border border-zinc-800/50">
                  <span className="text-zinc-500 block text-[11px]">LLM Judge</span>
                  <span className="text-zinc-300 font-semibold">
                    {results.include_llm_judge ? "Enabled" : "Disabled (Deterministic)"}
                  </span>
                </div>
              </div>
            </section>

            {/* Pareto Tradeoff Chart */}
            <section className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300">
                    Tradeoff Frontier: Quality vs. Financial Cost
                  </h3>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    Evaluates multi-dimensional performance without collapsing models into an artificial single score
                  </p>
                </div>
              </div>
              {renderParetoChart(results.pareto_points)}
            </section>

            {/* Multi-Model Comparison Table */}
            <section className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300">
                  Performance & Quality Summary Table
                </h3>
              </div>

              <div className="overflow-x-auto rounded-xl border border-zinc-800/80 bg-zinc-900/40 shadow-sm">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-zinc-800/80 bg-zinc-900/80 text-zinc-400 font-medium">
                      <th className="py-3 px-4">Model ID</th>
                      <th className="py-3 px-4 text-right">Runs</th>
                      <th className="py-3 px-4 text-right">Error %</th>
                      <th className="py-3 px-4 text-right">Mean TTFT</th>
                      <th className="py-3 px-4 text-right">Mean Latency</th>
                      <th className="py-3 px-4 text-right">Throughput</th>
                      <th className="py-3 px-4 text-right">Total Cost</th>
                      <th className="py-3 px-4 text-right">Exact Match</th>
                      <th className="py-3 px-4 text-right">Schema / Eval</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60 font-mono">
                    {results.models_stats.map((m: ModelComparisonStats) => {
                      const exactMatchScore = m.mean_metrics["exact_match"];
                      const schemaScore =
                        m.mean_metrics["json_schema_validity"] ??
                        m.mean_metrics["correctness"];

                      return (
                        <tr
                          key={m.model_id}
                          className="hover:bg-zinc-800/30 transition-colors"
                        >
                          <td className="py-3 px-4 font-sans font-semibold text-zinc-100">
                            {m.model_id}
                          </td>
                          <td className="py-3 px-4 text-right text-zinc-300">
                            {m.successful_runs}/{m.runs_count}
                          </td>
                          <td
                            className={`py-3 px-4 text-right font-semibold ${
                              m.error_rate > 0 ? "text-rose-400" : "text-emerald-400"
                            }`}
                          >
                            {(m.error_rate * 100).toFixed(1)}%
                          </td>
                          <td className="py-3 px-4 text-right text-cyan-400 font-semibold">
                            {m.mean_ttft_ms != null ? `${m.mean_ttft_ms}ms` : "—"}
                          </td>
                          <td className="py-3 px-4 text-right text-zinc-300">
                            {m.mean_latency_ms != null
                              ? `${(m.mean_latency_ms / 1000).toFixed(2)}s`
                              : "—"}
                          </td>
                          <td className="py-3 px-4 text-right text-violet-400">
                            {m.mean_tokens_per_sec != null
                              ? `${m.mean_tokens_per_sec.toFixed(1)} tok/s`
                              : "—"}
                          </td>
                          <td className="py-3 px-4 text-right text-emerald-400 font-semibold">
                            ${m.total_cost.toFixed(6)}
                          </td>
                          <td className="py-3 px-4 text-right">
                            {exactMatchScore !== undefined ? (
                              <span
                                className={`px-2 py-0.5 rounded font-bold ${
                                  exactMatchScore >= 0.8
                                    ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                                    : exactMatchScore >= 0.5
                                    ? "bg-amber-950 text-amber-300 border border-amber-800"
                                    : "bg-rose-950 text-rose-300 border border-rose-800"
                                }`}
                              >
                                {(exactMatchScore * 100).toFixed(1)}%
                              </span>
                            ) : (
                              <span className="text-zinc-600">—</span>
                            )}
                          </td>
                          <td className="py-3 px-4 text-right">
                            {schemaScore !== undefined ? (
                              <span
                                className={`px-2 py-0.5 rounded font-bold ${
                                  schemaScore >= 0.8
                                    ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                                    : "bg-amber-950 text-amber-300 border border-amber-800"
                                }`}
                              >
                                {(schemaScore * 100).toFixed(1)}%
                              </span>
                            ) : (
                              <span className="text-zinc-600">—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            {/* Benchmark Cases Detail Table */}
            <section className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300">
                  Individual Case Results ({results.cases.length})
                </h3>
              </div>

              <div className="space-y-3">
                {results.cases.map((c, idx) => (
                  <div
                    key={c.case_id || idx}
                    className="p-4 rounded-xl bg-zinc-900/50 border border-zinc-800/80 text-xs space-y-3"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800/60 pb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-zinc-500">#{idx + 1}</span>
                        <span className="px-2 py-0.5 rounded bg-zinc-800 text-violet-300 border border-zinc-700 font-mono text-[10px] uppercase">
                          {c.category}
                        </span>
                      </div>
                      {c.race_id && (
                        <Link
                          href={`/history/${c.race_id}`}
                          className="text-violet-400 hover:text-violet-300 font-mono text-[11px] underline"
                        >
                          Race {c.race_id.slice(0, 8)}… →
                        </Link>
                      )}
                    </div>

                    <div>
                      <span className="text-zinc-500 font-semibold block text-[10px] uppercase">
                        Question
                      </span>
                      <p className="text-zinc-200 text-sm font-sans mt-0.5">
                        {c.question}
                      </p>
                    </div>

                    {c.expected_answer && (
                      <div className="p-2 rounded bg-zinc-950/70 border border-zinc-800/60 font-mono text-[11px] text-zinc-300">
                        <span className="text-zinc-500 block text-[10px]">
                          Expected Answer:
                        </span>
                        {c.expected_answer}
                      </div>
                    )}

                    {/* Contender Answers Grid */}
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2.5 pt-1">
                      {Object.entries(c.models).map(([modelId, mData]) => {
                        const m = mData as {
                          status: string;
                          response_text?: string;
                          evaluations?: Record<string, number>;
                        };
                        const exactMatch = m.evaluations?.exact_match;

                        return (
                          <div
                            key={modelId}
                            className="p-2.5 rounded-lg bg-zinc-950/60 border border-zinc-800/60 flex flex-col justify-between"
                          >
                            <div>
                              <div className="flex items-center justify-between font-mono text-[11px] mb-1">
                                <span className="font-semibold text-zinc-300 truncate">
                                  {modelId}
                                </span>
                                {exactMatch !== undefined && (
                                  <span
                                    className={`px-1.5 py-0.5 rounded text-[10px] font-bold ${
                                      exactMatch === 1
                                        ? "bg-emerald-950 text-emerald-300"
                                        : "bg-rose-950 text-rose-300"
                                    }`}
                                  >
                                    {exactMatch === 1 ? "✓ Match" : "✕ Mismatch"}
                                  </span>
                                )}
                              </div>
                              <p className="text-zinc-400 text-xs font-sans line-clamp-3 leading-relaxed">
                                {m.response_text || (
                                  <span className="text-zinc-600 italic">
                                    No text / {m.status}
                                  </span>
                                )}
                              </p>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          </>
        ) : null}
      </main>

      <footer className="border-t border-zinc-800/60 py-3 px-6 text-center text-xs text-zinc-600">
        VersusLab Phase 9 • Experiment Engine & Benchmarking Platform
      </footer>
    </div>
  );
}
