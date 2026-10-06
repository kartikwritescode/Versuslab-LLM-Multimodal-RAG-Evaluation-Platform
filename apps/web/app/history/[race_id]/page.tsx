"use client";

import React, { useEffect, useState, use } from "react";
import Link from "next/link";
import { RaceDetailResponse, ModelRunDetail } from "../../../lib/types";
import { fetchRaceDetail, evaluateRace } from "../../../lib/race-client";

interface PageProps {
  params: Promise<{ race_id: string }>;
}

const HEDGE_WORDS = new Set([
  "maybe", "might", "possibly", "perhaps", "probably", "likely",
  "could", "may", "seems", "appears", "suggests", "potentially",
  "arguably", "presumably", "supposedly", "allegedly", "reportedly",
  "apparently", "seemingly", "essentially", "basically", "generally",
  "typically", "usually", "often", "sometimes", "occasionally"
]);

const MODEL_MAX_CONTEXT: Record<string, number> = {
  "openai:gpt-4o-mini": 128000,
  "openai:gpt-4o": 128000,
  "openai:gpt-4-turbo": 128000,
  "anthropic:claude-3-5-haiku-20241022": 200000,
  "anthropic:claude-3-5-sonnet-20241022": 200000,
  "anthropic:claude-3-opus-20240229": 200000,
  "gemini:gemini-2.5-flash": 1048576,
  "gemini:gemini-3.5-flash": 1048576,
  "gemini:gemini-3-flash-preview": 1048576,
  "grok:grok-2-1212": 131072,
  "xai:grok-2-1212": 131072,
  "deepseek:deepseek-chat": 64000,
  "deepseek:deepseek-reasoner": 64000,
};

interface EffectiveMetrics {
  tps: number | null;
  tpot: number | null;
  cost1k: number | null;
  costSec: number | null;
  words: number | null;
  chars: number | null;
  sentences: number | null;
  aggScore: number | null;
  confScore: number | null;
  qualifiers: number;
  inputTps: number | null;
  ctxUtil: number | null;
  maxCtx: number | null;
  chunks: number | null;
  avgChunk: number | null;
  cqRatio: number | null;
}

function getEffectiveMetrics(run: ModelRunDetail): EffectiveMetrics {
  // 1. Tokens Per Second (Throughput)
  let tps = run.tokens_per_second;
  if ((tps === null || tps === undefined) && run.output_tokens && run.latency_ms && run.latency_ms > 0) {
    tps = Math.round((run.output_tokens / (run.latency_ms / 1000)) * 10) / 10;
  }

  // 2. TPOT (Time Per Output Token)
  let tpot = run.time_per_output_token;
  if ((tpot === null || tpot === undefined) && run.output_tokens && run.latency_ms && run.ttft_ms) {
    const gen = run.latency_ms - run.ttft_ms;
    if (gen > 0 && run.output_tokens > 0) {
      tpot = Math.round((gen / run.output_tokens) * 10) / 10;
    }
  }

  // 3. Cost Efficiency
  let cost1k = run.cost_per_1k_tokens;
  let costSec = run.cost_per_second;
  if ((cost1k === null || cost1k === undefined) && run.total_cost && run.output_tokens && run.output_tokens > 0) {
    cost1k = (run.total_cost / run.output_tokens) * 1000;
  }
  if ((costSec === null || costSec === undefined) && run.total_cost && run.latency_ms && run.latency_ms > 0) {
    costSec = run.total_cost / (run.latency_ms / 1000);
  }

  // 4. Response Length Statistics
  let words = run.response_word_count;
  let chars = run.response_char_count;
  let sentences = run.response_sentence_count;
  if (words === null || words === undefined || chars === null || chars === undefined || sentences === null || sentences === undefined) {
    const text = run.response_text || "";
    chars = text.trim().length;
    const splitWords = text.trim().split(/\s+/).filter(Boolean);
    words = splitWords.length;
    const endings = text.match(/[.!?]+/g);
    sentences = endings ? endings.length : (chars > 0 ? 1 : 0);
  }

  // 5. Aggregate Quality Score
  let aggScore = run.aggregate_quality_score;
  if ((aggScore === null || aggScore === undefined) && run.evaluations && run.evaluations.length > 0) {
    const avg = run.evaluations.reduce((sum, e) => sum + e.score, 0) / run.evaluations.length;
    aggScore = Math.round(avg * 100) / 10;
  }

  // 8. Confidence & Qualifiers
  let confScore = run.confidence_score;
  let qualifiers = run.qualifier_count;
  if (confScore === null || confScore === undefined || qualifiers === null || qualifiers === undefined) {
    const text = (run.response_text || "").toLowerCase();
    const splitWords = text.split(/\s+/).filter(Boolean);
    let count = 0;
    for (const w of splitWords) {
      const clean = w.replace(/[.,!?;:]/g, "");
      if (HEDGE_WORDS.has(clean)) count++;
    }
    qualifiers = count;
    if (splitWords.length === 0) {
      confScore = null;
    } else {
      const ratio = count / splitWords.length;
      confScore = ratio >= 0.1 ? 0 : Math.max(0, Math.min(1, 1 - ratio * 10));
    }
  }

  // 9. Input Tokens Per Second (Prompt Processing Speed)
  let inputTps = run.input_tokens_per_second;
  if ((inputTps === null || inputTps === undefined) && run.input_tokens && run.ttft_ms && run.ttft_ms > 0) {
    inputTps = Math.round((run.input_tokens / (run.ttft_ms / 1000)));
  }

  // 10. Memory / Context Utilization
  let ctxUtil = run.context_utilization_percent;
  const maxCtx = run.model_max_context || MODEL_MAX_CONTEXT[run.model_id] || (run.model_id.startsWith("ollama:") ? 8192 : null);
  if ((ctxUtil === null || ctxUtil === undefined) && run.input_tokens && maxCtx) {
    ctxUtil = Math.round((run.input_tokens / maxCtx) * 10000) / 100;
  }

  // 11. Streaming Stability
  const chunks = run.streaming_chunk_count ?? null;
  const avgChunk = run.avg_chunk_size ?? (chunks && chars ? Math.round((chars / chunks) * 10) / 10 : null);

  // 15. Cost vs Quality Tradeoff
  let cqRatio = run.cost_quality_ratio;
  if ((cqRatio === null || cqRatio === undefined) && aggScore !== null && aggScore !== undefined) {
    const cost = run.total_cost ?? 0;
    if (cost > 0) {
      cqRatio = Math.round((aggScore / cost) * 10) / 10;
    }
  }

  return {
    tps: tps ?? null,
    tpot: tpot ?? null,
    cost1k: cost1k ?? null,
    costSec: costSec ?? null,
    words: words ?? null,
    chars: chars ?? null,
    sentences: sentences ?? null,
    aggScore: aggScore ?? null,
    confScore: confScore ?? null,
    qualifiers: qualifiers ?? 0,
    inputTps: inputTps ?? null,
    ctxUtil: ctxUtil ?? null,
    maxCtx: maxCtx ?? null,
    chunks: chunks ?? null,
    avgChunk: avgChunk ?? null,
    cqRatio: cqRatio ?? null,
  };
}

export default function RaceDetailPage({ params }: PageProps) {
  const resolvedParams = use(params);
  const raceId = resolvedParams.race_id;

  const [race, setRace] = useState<RaceDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [evaluating, setEvaluating] = useState(false);
  const [evalError, setEvalError] = useState<string | null>(null);
  const [comparisonTab, setComparisonTab] = useState<"all" | "speed" | "quality" | "cost" | "content">("all");

  useEffect(() => {
    async function loadDetail() {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchRaceDetail(raceId);
        setRace(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    }
    loadDetail();
  }, [raceId]);

  const handleEvaluate = async () => {
    setEvaluating(true);
    setEvalError(null);
    try {
      await evaluateRace(raceId);
      const updated = await fetchRaceDetail(raceId);
      setRace(updated);
    } catch (err) {
      setEvalError(err instanceof Error ? err.message : String(err));
    } finally {
      setEvaluating(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case "done":
      case "completed":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-emerald-950/70 text-emerald-300 border border-emerald-800/80">
            ✓ {status}
          </span>
        );
      case "error":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-rose-950/70 text-rose-300 border border-rose-800/80">
            ✕ Error
          </span>
        );
      case "timeout":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-amber-950/70 text-amber-300 border border-amber-800/80">
            ⏱ Timeout
          </span>
        );
      case "cancelled":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-zinc-800 text-zinc-400 border border-zinc-700">
            ⊘ Cancelled
          </span>
        );
      case "streaming":
        return (
          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-cyan-950/70 text-cyan-300 border border-cyan-800/80 animate-pulse">
            Streaming
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
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      });
    } catch {
      return isoString;
    }
  };

  const totalRaceCost = race?.model_runs.reduce(
    (acc, r) => acc + (r.total_cost ?? 0),
    0
  ) ?? 0;

  const totalEvaluationsCount = race?.model_runs.reduce(
    (acc, r) => acc + (r.evaluations?.length ?? 0),
    0
  ) ?? 0;

  const hasEvaluations = totalEvaluationsCount > 0;

  // Calculate winner models across comparison categories
  const completedRuns = (race?.model_runs || []).filter(
    (r) => r.status.toLowerCase() === "done" || r.status.toLowerCase() === "completed"
  );

  const metricsMap = new Map<string, EffectiveMetrics>();
  for (const r of race?.model_runs || []) {
    metricsMap.set(r.id, getEffectiveMetrics(r));
  }

  const bestTtftRun = [...completedRuns]
    .filter((r) => r.ttft_ms !== null)
    .sort((a, b) => a.ttft_ms! - b.ttft_ms!)[0];

  const bestTpsRun = [...completedRuns]
    .filter((r) => (metricsMap.get(r.id)?.tps ?? 0) > 0)
    .sort((a, b) => (metricsMap.get(b.id)?.tps ?? 0) - (metricsMap.get(a.id)?.tps ?? 0))[0];

  const bestQualityRun = [...completedRuns]
    .filter((r) => (metricsMap.get(r.id)?.aggScore ?? 0) > 0)
    .sort((a, b) => (metricsMap.get(b.id)?.aggScore ?? 0) - (metricsMap.get(a.id)?.aggScore ?? 0))[0];

  const bestValueRun = [...completedRuns]
    .filter(
      (r) => (metricsMap.get(r.id)?.cqRatio ?? 0) > 0 || (r.total_cost === 0 && (metricsMap.get(r.id)?.aggScore ?? 0) > 0)
    )
    .sort((a, b) => {
      if (a.total_cost === 0 && b.total_cost !== 0) return -1;
      if (b.total_cost === 0 && a.total_cost !== 0) return 1;
      return (metricsMap.get(b.id)?.cqRatio ?? 0) - (metricsMap.get(a.id)?.cqRatio ?? 0);
    })[0];

  const bestTpotRun = [...completedRuns]
    .filter((r) => (metricsMap.get(r.id)?.tpot ?? 0) > 0)
    .sort((a, b) => (metricsMap.get(a.id)?.tpot ?? 0) - (metricsMap.get(b.id)?.tpot ?? 0))[0];

  const bestCostRun = [...completedRuns]
    .filter((r) => r.total_cost !== null && r.total_cost !== undefined)
    .sort((a, b) => (a.total_cost ?? 0) - (b.total_cost ?? 0))[0];

  return (
    <div className="flex-1 flex flex-col min-h-screen bg-zinc-950 text-zinc-100">
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
                Detailed Race Report & Contender Benchmark
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            {race && (race.status === "completed" || race.status === "done") && (
              <button
                onClick={handleEvaluate}
                disabled={evaluating}
                className="px-3.5 py-2 rounded-lg text-xs font-semibold bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 disabled:opacity-50 text-white transition-all flex items-center gap-2 shadow-md shadow-violet-600/20 border border-violet-500/40 cursor-pointer"
              >
                {evaluating ? (
                  <>
                    <span className="animate-spin inline-block w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full" />
                    Judging Race...
                  </>
                ) : hasEvaluations ? (
                  "⚡ Re-evaluate Race"
                ) : (
                  "⚡ Evaluate Race (LLM Judge)"
                )}
              </button>
            )}
            <Link
              href="/history"
              className="px-4 py-2 rounded-lg text-sm font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition-colors flex items-center gap-2"
            >
              ← Back to History
            </Link>
            <Link
              href="/"
              className="px-4 py-2 rounded-lg text-sm font-medium bg-violet-600 hover:bg-violet-500 text-white transition-colors"
            >
              New Race
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-8 flex flex-col gap-6">
        {error && (
          <div className="p-4 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-200 text-sm">
            <p className="font-semibold">Error loading race</p>
            <p className="mt-0.5">{error}</p>
          </div>
        )}

        {evalError && (
          <div className="p-4 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-200 text-sm">
            <p className="font-semibold">Evaluation Error</p>
            <p className="mt-0.5">{evalError}</p>
          </div>
        )}

        {loading ? (
          <div className="border border-dashed border-zinc-800 rounded-xl p-12 text-center text-zinc-500 text-sm">
            Loading race details...
          </div>
        ) : race ? (
          <>
            {/* Race Overview Card */}
            <section className="bg-zinc-900/40 border border-zinc-800/80 rounded-xl p-6 shadow-sm space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800/70 pb-4">
                <div>
                  <span className="text-xs font-mono text-zinc-500">RACE ID</span>
                  <h2 className="text-base font-mono font-bold text-zinc-100 mt-0.5">
                    {race.id}
                  </h2>
                </div>
                <div className="flex items-center gap-3">
                  {getStatusBadge(race.status)}
                  <span className="text-xs font-mono px-2.5 py-1 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                    {race.model_runs.length} contenders
                  </span>
                  {hasEvaluations && (
                    <span className="text-xs font-medium px-2.5 py-1 rounded bg-violet-950/70 text-violet-300 border border-violet-800/80">
                      ★ {totalEvaluationsCount} evaluations
                    </span>
                  )}
                </div>
              </div>

              {race.shared_context_hash && (
                <div className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 rounded-lg bg-zinc-950 border border-cyan-900/40 text-xs font-mono">
                  <div className="flex items-center gap-2">
                    <span className="text-zinc-500">Context hash:</span>
                    <span className="text-cyan-400 font-bold" title={race.shared_context_hash}>
                      {race.shared_context_hash.slice(0, 8)}…{race.shared_context_hash.slice(-6)}
                    </span>
                  </div>
                  <span className="text-emerald-400 font-semibold text-[11px] bg-emerald-950/50 px-2 py-0.5 rounded border border-emerald-800/50">
                    ✓ Identical across {race.model_runs.length}/{race.model_runs.length} models
                  </span>
                </div>
              )}

              {/* Prompt Box */}
              <div>
                <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400 block mb-1.5">
                  Prompt
                </span>
                <div className="bg-zinc-950 border border-zinc-800/90 rounded-lg p-4 text-sm text-zinc-200 whitespace-pre-wrap leading-relaxed font-sans">
                  {race.prompt}
                </div>
              </div>

              {/* Metadata Grid */}
              <div className="grid grid-cols-2 md:grid-cols-5 gap-4 text-xs font-mono text-zinc-400 pt-1">
                <div className="bg-zinc-950/50 p-3 rounded-lg border border-zinc-800/50">
                  <span className="text-zinc-500 block text-[11px]">Created At</span>
                  <span className="text-zinc-300 font-semibold">{formatDate(race.created_at)}</span>
                </div>
                <div className="bg-zinc-950/50 p-3 rounded-lg border border-zinc-800/50">
                  <span className="text-zinc-500 block text-[11px]">Finished At</span>
                  <span className="text-zinc-300 font-semibold">{formatDate(race.finished_at)}</span>
                </div>
                <div className="bg-zinc-950/50 p-3 rounded-lg border border-zinc-800/50">
                  <span className="text-zinc-500 block text-[11px]">Temperature</span>
                  <span className="text-zinc-300 font-semibold">{race.temperature}</span>
                </div>
                <div className="bg-zinc-950/50 p-3 rounded-lg border border-zinc-800/50">
                  <span className="text-zinc-500 block text-[11px]">Max Tokens</span>
                  <span className="text-zinc-300 font-semibold">{race.max_tokens ?? "None"}</span>
                </div>
                <div className="bg-zinc-950/50 p-3 rounded-lg border border-zinc-800/50">
                  <span className="text-zinc-500 block text-[11px]">Total Est. Cost</span>
                  <span className="text-emerald-400 font-semibold">
                    ${totalRaceCost.toFixed(6)}
                  </span>
                </div>
              </div>
            </section>

            {/* SECTION: Best-in-Class Winner Showcase */}
            {completedRuns.length >= 2 && (
              <section className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-300 flex items-center gap-2">
                    <span>🏆</span> Best-in-Class Highlights
                  </h3>
                  <span className="text-xs text-zinc-500">Across {completedRuns.length} contenders</span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
                  {/* Top Quality */}
                  {bestQualityRun && (
                    <div className="bg-gradient-to-br from-violet-950/40 to-zinc-900/80 border border-violet-800/50 rounded-xl p-3 shadow-sm flex flex-col justify-between">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] uppercase font-bold text-violet-400 tracking-wider">Top Quality</span>
                        <span className="text-violet-400 text-xs">★</span>
                      </div>
                      <div className="my-1.5 truncate">
                        <span className="text-sm font-bold text-violet-200 block truncate" title={bestQualityRun.model_id}>
                          {bestQualityRun.model_id.split(":")[1] || bestQualityRun.model_id}
                        </span>
                        <span className="text-xs font-mono font-semibold text-violet-400">
                          {metricsMap.get(bestQualityRun.id)?.aggScore?.toFixed(1)}/10
                        </span>
                      </div>
                      <span className="text-[10px] text-zinc-500">Highest judge score</span>
                    </div>
                  )}

                  {/* Fastest Speed */}
                  {bestTpsRun && (
                    <div className="bg-gradient-to-br from-emerald-950/40 to-zinc-900/80 border border-emerald-800/50 rounded-xl p-3 shadow-sm flex flex-col justify-between">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] uppercase font-bold text-emerald-400 tracking-wider">Top Throughput</span>
                        <span className="text-emerald-400 text-xs">⚡</span>
                      </div>
                      <div className="my-1.5 truncate">
                        <span className="text-sm font-bold text-emerald-200 block truncate" title={bestTpsRun.model_id}>
                          {bestTpsRun.model_id.split(":")[1] || bestTpsRun.model_id}
                        </span>
                        <span className="text-xs font-mono font-semibold text-emerald-400">
                          {metricsMap.get(bestTpsRun.id)?.tps?.toFixed(1)} tok/s
                        </span>
                      </div>
                      <span className="text-[10px] text-zinc-500">Generation throughput</span>
                    </div>
                  )}

                  {/* Lowest TPOT */}
                  {bestTpotRun && (
                    <div className="bg-gradient-to-br from-cyan-950/40 to-zinc-900/80 border border-cyan-800/50 rounded-xl p-3 shadow-sm flex flex-col justify-between">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] uppercase font-bold text-cyan-400 tracking-wider">Lowest TPOT</span>
                        <span className="text-cyan-400 text-xs">⏱️</span>
                      </div>
                      <div className="my-1.5 truncate">
                        <span className="text-sm font-bold text-cyan-200 block truncate" title={bestTpotRun.model_id}>
                          {bestTpotRun.model_id.split(":")[1] || bestTpotRun.model_id}
                        </span>
                        <span className="text-xs font-mono font-semibold text-cyan-400">
                          {metricsMap.get(bestTpotRun.id)?.tpot?.toFixed(1)} ms/tok
                        </span>
                      </div>
                      <span className="text-[10px] text-zinc-500">Time per output token</span>
                    </div>
                  )}

                  {/* Best Value */}
                  {bestValueRun && (
                    <div className="bg-gradient-to-br from-amber-950/40 to-zinc-900/80 border border-amber-800/50 rounded-xl p-3 shadow-sm flex flex-col justify-between">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] uppercase font-bold text-amber-400 tracking-wider">Best Value</span>
                        <span className="text-amber-400 text-xs">💎</span>
                      </div>
                      <div className="my-1.5 truncate">
                        <span className="text-sm font-bold text-amber-200 block truncate" title={bestValueRun.model_id}>
                          {bestValueRun.model_id.split(":")[1] || bestValueRun.model_id}
                        </span>
                        <span className="text-xs font-mono font-semibold text-amber-400">
                          {bestValueRun.total_cost === 0
                            ? "Free (Top Value)"
                            : `${metricsMap.get(bestValueRun.id)?.cqRatio?.toFixed(0)} pts/$`}
                        </span>
                      </div>
                      <span className="text-[10px] text-zinc-500">Quality score per dollar</span>
                    </div>
                  )}

                  {/* Lowest TTFT */}
                  {bestTtftRun && (
                    <div className="bg-gradient-to-br from-sky-950/40 to-zinc-900/80 border border-sky-800/50 rounded-xl p-3 shadow-sm flex flex-col justify-between">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] uppercase font-bold text-sky-400 tracking-wider">Fastest TTFT</span>
                        <span className="text-sky-400 text-xs">🚀</span>
                      </div>
                      <div className="my-1.5 truncate">
                        <span className="text-sm font-bold text-sky-200 block truncate" title={bestTtftRun.model_id}>
                          {bestTtftRun.model_id.split(":")[1] || bestTtftRun.model_id}
                        </span>
                        <span className="text-xs font-mono font-semibold text-sky-400">
                          {bestTtftRun.ttft_ms} ms
                        </span>
                      </div>
                      <span className="text-[10px] text-zinc-500">Time to first token</span>
                    </div>
                  )}

                  {/* Lowest Cost */}
                  {bestCostRun && (
                    <div className="bg-gradient-to-br from-indigo-950/40 to-zinc-900/80 border border-indigo-800/50 rounded-xl p-3 shadow-sm flex flex-col justify-between">
                      <div className="flex items-center justify-between">
                        <span className="text-[10px] uppercase font-bold text-indigo-400 tracking-wider">Most Economic</span>
                        <span className="text-indigo-400 text-xs">💰</span>
                      </div>
                      <div className="my-1.5 truncate">
                        <span className="text-sm font-bold text-indigo-200 block truncate" title={bestCostRun.model_id}>
                          {bestCostRun.model_id.split(":")[1] || bestCostRun.model_id}
                        </span>
                        <span className="text-xs font-mono font-semibold text-indigo-400">
                          ${(bestCostRun.total_cost ?? 0).toFixed(6)}
                        </span>
                      </div>
                      <span className="text-[10px] text-zinc-500">Lowest total financial cost</span>
                    </div>
                  )}
                </div>
              </section>
            )}

            {/* SECTION: Contender Head-to-Head Comparison Matrix */}
            <section className="bg-zinc-900/50 border border-zinc-800/80 rounded-xl overflow-hidden shadow-sm space-y-0">
              <div className="p-4 border-b border-zinc-800/70 flex flex-wrap items-center justify-between gap-3 bg-zinc-900/80">
                <div>
                  <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-200">
                    Contender Comparison Matrix
                  </h3>
                  <p className="text-xs text-zinc-400 mt-0.5">
                    Compare performance, economics, quality, and response metrics across all contenders
                  </p>
                </div>

                {/* Filter Tabs */}
                <div className="flex items-center gap-1 bg-zinc-950 p-1 rounded-lg border border-zinc-800 text-xs font-medium">
                  <button
                    onClick={() => setComparisonTab("all")}
                    className={`px-3 py-1.5 rounded-md transition-all ${
                      comparisonTab === "all"
                        ? "bg-violet-600 text-white shadow-sm"
                        : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
                    }`}
                  >
                    All Metrics
                  </button>
                  <button
                    onClick={() => setComparisonTab("speed")}
                    className={`px-3 py-1.5 rounded-md transition-all ${
                      comparisonTab === "speed"
                        ? "bg-violet-600 text-white shadow-sm"
                        : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
                    }`}
                  >
                    ⚡ Speed
                  </button>
                  <button
                    onClick={() => setComparisonTab("quality")}
                    className={`px-3 py-1.5 rounded-md transition-all ${
                      comparisonTab === "quality"
                        ? "bg-violet-600 text-white shadow-sm"
                        : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
                    }`}
                  >
                    ★ Quality & Value
                  </button>
                  <button
                    onClick={() => setComparisonTab("cost")}
                    className={`px-3 py-1.5 rounded-md transition-all ${
                      comparisonTab === "cost"
                        ? "bg-violet-600 text-white shadow-sm"
                        : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
                    }`}
                  >
                    💰 Cost
                  </button>
                  <button
                    onClick={() => setComparisonTab("content")}
                    className={`px-3 py-1.5 rounded-md transition-all ${
                      comparisonTab === "content"
                        ? "bg-violet-600 text-white shadow-sm"
                        : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-900"
                    }`}
                  >
                    📊 Content
                  </button>
                </div>
              </div>

              {/* Responsive Table */}
              <div className="overflow-x-auto">
                <table className="w-full text-left border-collapse text-xs">
                  <thead>
                    <tr className="border-b border-zinc-800 bg-zinc-950/70 text-zinc-400 font-semibold">
                      <th className="py-3 px-4 min-w-[160px]">Model Contender</th>
                      <th className="py-3 px-3 text-center">Status</th>

                      {/* Speed Metrics Columns */}
                      {(comparisonTab === "all" || comparisonTab === "speed") && (
                        <>
                          <th className="py-3 px-3 text-right">TTFT</th>
                          <th className="py-3 px-3 text-right">Latency</th>
                          <th className="py-3 px-3 text-right">Throughput (Speed)</th>
                          <th className="py-3 px-3 text-right">TPOT</th>
                          {comparisonTab === "speed" && (
                            <th className="py-3 px-3 text-right">Input Tok/s</th>
                          )}
                        </>
                      )}

                      {/* Quality & Value Columns */}
                      {(comparisonTab === "all" || comparisonTab === "quality") && (
                        <>
                          <th className="py-3 px-3 text-right">Quality Score</th>
                          <th className="py-3 px-3 text-right">Quality Pts / $</th>
                          <th className="py-3 px-3 text-center">Confidence</th>
                        </>
                      )}

                      {/* Cost Columns */}
                      {(comparisonTab === "all" || comparisonTab === "cost") && (
                        <>
                          <th className="py-3 px-3 text-right">Total Cost</th>
                          <th className="py-3 px-3 text-right">Cost / 1K Tok</th>
                          {comparisonTab === "cost" && (
                            <th className="py-3 px-3 text-right">Cost / Sec</th>
                          )}
                        </>
                      )}

                      {/* Content & Context Columns */}
                      {(comparisonTab === "all" || comparisonTab === "content") && (
                        <>
                          <th className="py-3 px-3 text-right">Words</th>
                          <th className="py-3 px-3 text-right">Context Used</th>
                          <th className="py-3 px-3 text-center">Streaming</th>
                        </>
                      )}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-800/60 font-mono">
                    {race.model_runs.map((run: ModelRunDetail) => {
                      const m = metricsMap.get(run.id) || getEffectiveMetrics(run);
                      const isTopQuality = bestQualityRun?.id === run.id;
                      const isTopSpeed = bestTpsRun?.id === run.id;
                      const isBestValue = bestValueRun?.id === run.id;

                      return (
                        <tr
                          key={run.id}
                          className="hover:bg-zinc-800/20 transition-colors"
                        >
                          {/* Contender Name */}
                          <td className="py-3 px-4 font-sans">
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-zinc-100">
                                {run.model_id}
                              </span>
                              {isTopQuality && (
                                <span className="text-[10px] font-sans px-1.5 py-0.5 rounded bg-violet-950/80 text-violet-300 border border-violet-800/80">
                                  ★ Quality
                                </span>
                              )}
                              {isTopSpeed && (
                                <span className="text-[10px] font-sans px-1.5 py-0.5 rounded bg-emerald-950/80 text-emerald-300 border border-emerald-800/80">
                                  ⚡ Speed
                                </span>
                              )}
                              {isBestValue && (
                                <span className="text-[10px] font-sans px-1.5 py-0.5 rounded bg-amber-950/80 text-amber-300 border border-amber-800/80">
                                  💎 Value
                                </span>
                              )}
                            </div>
                          </td>

                          {/* Status */}
                          <td className="py-3 px-3 text-center font-sans">
                            {getStatusBadge(run.status)}
                          </td>

                          {/* Speed Columns */}
                          {(comparisonTab === "all" || comparisonTab === "speed") && (
                            <>
                              <td className="py-3 px-3 text-right text-cyan-400">
                                {run.ttft_ms !== null ? `${run.ttft_ms}ms` : "—"}
                              </td>
                              <td className="py-3 px-3 text-right text-zinc-300">
                                {run.latency_ms !== null ? `${(run.latency_ms / 1000).toFixed(2)}s` : "—"}
                              </td>
                              <td className="py-3 px-3 text-right font-bold">
                                {m.tps !== null ? (
                                  <span
                                    className={
                                      m.tps >= 30
                                        ? "text-emerald-400"
                                        : m.tps >= 15
                                        ? "text-amber-400"
                                        : "text-rose-400"
                                    }
                                  >
                                    {m.tps.toFixed(1)} tok/s
                                  </span>
                                ) : "—"}
                              </td>
                              <td className="py-3 px-3 text-right text-zinc-300">
                                {m.tpot !== null ? `${m.tpot.toFixed(1)}ms` : "—"}
                              </td>
                              {comparisonTab === "speed" && (
                                <td className="py-3 px-3 text-right text-zinc-400">
                                  {m.inputTps !== null ? `${m.inputTps} tok/s` : "—"}
                                </td>
                              )}
                            </>
                          )}

                          {/* Quality Columns */}
                          {(comparisonTab === "all" || comparisonTab === "quality") && (
                            <>
                              <td className="py-3 px-3 text-right">
                                {m.aggScore !== null ? (
                                  <span className="font-bold text-violet-300 bg-violet-950/40 px-2 py-0.5 rounded border border-violet-800/40">
                                    {m.aggScore.toFixed(1)} / 10
                                  </span>
                                ) : (
                                  <span className="text-zinc-600">—</span>
                                )}
                              </td>
                              <td className="py-3 px-3 text-right font-semibold">
                                {run.total_cost === 0 && m.aggScore ? (
                                  <span className="text-amber-300">Free (Top Value)</span>
                                ) : m.cqRatio !== null ? (
                                  <span className="text-amber-300">{m.cqRatio.toFixed(0)} pts/$</span>
                                ) : (
                                  <span className="text-zinc-600">—</span>
                                )}
                              </td>
                              <td className="py-3 px-3 text-center">
                                {m.confScore !== null ? (
                                  <span
                                    className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-sans font-medium ${
                                      m.confScore >= 0.7
                                        ? "bg-cyan-950/70 text-cyan-300 border border-cyan-800/80"
                                        : m.confScore >= 0.4
                                        ? "bg-amber-950/70 text-amber-300 border border-amber-800/80"
                                        : "bg-rose-950/70 text-rose-300 border border-rose-800/80"
                                    }`}
                                  >
                                    {(m.confScore * 100).toFixed(0)}% ({m.qualifiers} qual)
                                  </span>
                                ) : (
                                  <span className="text-zinc-600 font-sans">—</span>
                                )}
                              </td>
                            </>
                          )}

                          {/* Cost Columns */}
                          {(comparisonTab === "all" || comparisonTab === "cost") && (
                            <>
                              <td className="py-3 px-3 text-right text-emerald-400 font-semibold">
                                {run.total_cost !== null && run.total_cost !== undefined
                                  ? `$${run.total_cost.toFixed(6)}`
                                  : "—"}
                              </td>
                              <td className="py-3 px-3 text-right text-emerald-300">
                                {m.cost1k !== null ? `$${m.cost1k.toFixed(4)}` : "—"}
                              </td>
                              {comparisonTab === "cost" && (
                                <td className="py-3 px-3 text-right text-emerald-300">
                                  {m.costSec !== null ? `$${m.costSec.toFixed(5)}` : "—"}
                                </td>
                              )}
                            </>
                          )}

                          {/* Content Columns */}
                          {(comparisonTab === "all" || comparisonTab === "content") && (
                            <>
                              <td className="py-3 px-3 text-right text-zinc-300">
                                {m.words !== null ? `${m.words} w` : "—"}
                              </td>
                              <td className="py-3 px-3 text-right">
                                {m.ctxUtil !== null ? (
                                  <span
                                    className={
                                      m.ctxUtil >= 80
                                        ? "text-rose-400 font-bold"
                                        : m.ctxUtil >= 50
                                        ? "text-amber-400 font-bold"
                                        : "text-emerald-400"
                                    }
                                  >
                                    {m.ctxUtil.toFixed(1)}%
                                  </span>
                                ) : (
                                  <span className="text-zinc-600">—</span>
                                )}
                              </td>
                              <td className="py-3 px-3 text-center">
                                {m.chunks !== null ? (
                                  <span className="font-sans text-[11px] px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700">
                                    {m.chunks} chunks • {m.avgChunk ? `${m.avgChunk} c/ch` : "Stable"}
                                  </span>
                                ) : (
                                  <span className="text-zinc-600 font-sans">Streamed</span>
                                )}
                              </td>
                            </>
                          )}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>

            {/* SECTION: Individual Contender Results (Cards Grid) */}
            <section className="space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-sm font-semibold uppercase tracking-wider text-zinc-400">
                  Contender Results ({race.model_runs.length})
                </h3>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
                {race.model_runs.map((run: ModelRunDetail) => {
                  const m = metricsMap.get(run.id) || getEffectiveMetrics(run);

                  return (
                    <div
                      key={run.id}
                      className="flex flex-col bg-zinc-900/60 border border-zinc-800/90 rounded-xl overflow-hidden shadow-sm"
                    >
                      {/* Card Header */}
                      <div className="px-4 py-3 border-b border-zinc-800/80 bg-zinc-900/90 flex items-center justify-between">
                        <div className="min-w-0 pr-2">
                          <h4 className="text-sm font-semibold text-zinc-100 truncate">
                            {run.model_id}
                          </h4>
                          <p className="text-[11px] font-mono text-zinc-500 truncate">
                            run: {run.id.slice(0, 8)}…
                          </p>
                        </div>
                        <div className="shrink-0">{getStatusBadge(run.status)}</div>
                      </div>

                      {/* Primary Metrics Grid (Hero Stats) */}
                      <div className="px-4 py-3 border-b border-zinc-800/50 bg-zinc-950/40">
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
                          {/* TTFT */}
                          <div className="bg-zinc-900/60 rounded-lg p-2.5 border border-zinc-800/60">
                            <span className="text-zinc-500 block text-[10px] font-semibold mb-1">TTFT</span>
                            <span className={run.ttft_ms !== null ? "text-cyan-400 font-bold text-sm" : "text-zinc-600"}>
                              {run.ttft_ms !== null ? `${run.ttft_ms}ms` : "—"}
                            </span>
                          </div>

                          {/* Latency */}
                          <div className="bg-zinc-900/60 rounded-lg p-2.5 border border-zinc-800/60">
                            <span className="text-zinc-500 block text-[10px] font-semibold mb-1">LATENCY</span>
                            <span className={run.latency_ms !== null ? "text-zinc-200 font-bold text-sm" : "text-zinc-600"}>
                              {run.latency_ms !== null ? `${(run.latency_ms / 1000).toFixed(2)}s` : "—"}
                            </span>
                          </div>

                          {/* Throughput (Metric 1) */}
                          <div className="bg-zinc-900/60 rounded-lg p-2.5 border border-zinc-800/60">
                            <span className="text-zinc-500 block text-[10px] font-semibold mb-1">SPEED</span>
                            <span className={
                              m.tps !== null
                                ? m.tps >= 30
                                  ? "text-emerald-400 font-bold text-sm"
                                  : m.tps >= 15
                                  ? "text-amber-400 font-bold text-sm"
                                  : "text-rose-400 font-bold text-sm"
                                : "text-zinc-600"
                            }>
                              {m.tps !== null ? `${m.tps.toFixed(1)} tok/s` : "—"}
                            </span>
                          </div>

                          {/* Total Cost */}
                          <div className="bg-zinc-900/60 rounded-lg p-2.5 border border-zinc-800/60">
                            <span className="text-zinc-500 block text-[10px] font-semibold mb-1">COST</span>
                            <span className={run.total_cost !== null && run.total_cost !== undefined ? "text-emerald-400 font-bold text-sm" : "text-zinc-600"}>
                              {run.total_cost !== null && run.total_cost !== undefined ? `$${run.total_cost.toFixed(6)}` : "—"}
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Quality, Value & Confidence Banner (Metrics 5, 15, 8) */}
                      {(m.aggScore !== null || m.confScore !== null) && (
                        <div className="px-4 py-3 border-b border-zinc-800/50 bg-gradient-to-br from-violet-950/20 via-zinc-950/40 to-indigo-950/20 space-y-2">
                          <div className="flex items-center justify-between gap-3">
                            {/* Metric 5: Aggregate Quality Score */}
                            {m.aggScore !== null && (
                              <div>
                                <span className="text-[10px] font-semibold text-violet-400 uppercase tracking-wider block mb-0.5">
                                  Quality Score
                                </span>
                                <div className="flex items-center gap-1.5">
                                  <span className="text-2xl font-bold text-violet-300">
                                    {m.aggScore.toFixed(1)}
                                  </span>
                                  <span className="text-xs text-zinc-500">/10</span>
                                  <div className="flex gap-0.5 ml-1">
                                    {Array.from({ length: 5 }).map((_, i) => {
                                      const threshold = (i + 1) * 2;
                                      const filled = (m.aggScore ?? 0) >= threshold;
                                      return (
                                        <span key={i} className={filled ? "text-violet-400 text-xs" : "text-zinc-700 text-xs"}>
                                          ★
                                        </span>
                                      );
                                    })}
                                  </div>
                                </div>
                              </div>
                            )}

                            {/* Metric 15: Quality Points Per Dollar & Metric 8: Confidence */}
                            <div className="text-right flex flex-col items-end gap-1">
                              {run.total_cost === 0 && m.aggScore ? (
                                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-300 bg-amber-950/60 px-2 py-0.5 rounded border border-amber-800/60">
                                  💎 Free (Top Value)
                                </span>
                              ) : m.cqRatio !== null ? (
                                <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-amber-300 bg-amber-950/60 px-2 py-0.5 rounded border border-amber-800/60" title="Quality points per dollar">
                                  💎 {m.cqRatio.toFixed(0)} pts/$
                                </span>
                              ) : null}

                              {/* Metric 8: Confidence & Qualifier Count */}
                              {m.confScore !== null && (
                                <span
                                  className={`inline-flex items-center gap-1 text-[10px] font-medium px-2 py-0.5 rounded border ${
                                    m.confScore >= 0.7
                                      ? "bg-cyan-950/60 text-cyan-300 border-cyan-800/60"
                                      : m.confScore >= 0.4
                                      ? "bg-amber-950/60 text-amber-300 border-amber-800/60"
                                      : "bg-rose-950/60 text-rose-300 border-rose-800/60"
                                  }`}
                                  title={`${m.qualifiers} hedge/qualifier words detected in response`}
                                >
                                  🎯 {(m.confScore * 100).toFixed(0)}% conf ({m.qualifiers} qual)
                                </span>
                              )}
                            </div>
                          </div>
                        </div>
                      )}

                      {/* Advanced Metrics - Collapsible Section */}
                      <details open className="group border-b border-zinc-800/50 bg-zinc-950/20">
                        <summary className="px-4 py-2.5 cursor-pointer hover:bg-zinc-900/40 transition-colors flex items-center justify-between">
                          <span className="text-[10px] font-semibold text-zinc-400 uppercase tracking-wider">
                            Detailed Metrics & Benchmarks
                          </span>
                          <span className="text-zinc-500 text-xs group-open:rotate-180 transition-transform">▼</span>
                        </summary>
                        <div className="px-4 py-3 space-y-3">
                          {/* Performance Details: TPOT (2), Input Speed (9), Tokens */}
                          <div>
                            <h5 className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-2">
                              Performance & Generation
                            </h5>
                            <div className="grid grid-cols-2 gap-2 text-xs">
                              {/* Metric 2: TPOT */}
                              <div className="flex justify-between items-center bg-zinc-900/40 rounded px-2.5 py-1.5">
                                <span className="text-zinc-400">TPOT</span>
                                <span className="text-zinc-200 font-mono font-semibold">
                                  {m.tpot !== null ? `${m.tpot.toFixed(1)}ms` : "—"}
                                </span>
                              </div>
                              {/* Metric 9: Input Speed */}
                              <div className="flex justify-between items-center bg-zinc-900/40 rounded px-2.5 py-1.5">
                                <span className="text-zinc-400">Input Speed</span>
                                <span className="text-zinc-200 font-mono font-semibold">
                                  {m.inputTps !== null ? `${m.inputTps} tok/s` : "—"}
                                </span>
                              </div>
                              <div className="flex justify-between items-center bg-zinc-900/40 rounded px-2.5 py-1.5">
                                <span className="text-zinc-400">Tokens (I/O)</span>
                                <span className="text-violet-300 font-mono font-semibold">
                                  {run.input_tokens ?? "—"} / {run.output_tokens ?? "—"}
                                </span>
                              </div>
                              {/* Metric 10: Context Utilization with limits */}
                              <div className="flex flex-col justify-center bg-zinc-900/40 rounded px-2.5 py-1.5">
                                <div className="flex justify-between items-center">
                                  <span className="text-zinc-400">Context Used</span>
                                  <span className={`font-mono font-semibold ${
                                    m.ctxUtil !== null
                                      ? m.ctxUtil >= 80 ? "text-rose-300" :
                                        m.ctxUtil >= 50 ? "text-amber-300" :
                                        "text-emerald-300"
                                      : "text-zinc-600"
                                  }`}>
                                    {m.ctxUtil !== null ? `${m.ctxUtil.toFixed(1)}%` : "—"}
                                  </span>
                                </div>
                                {m.ctxUtil !== null && (
                                  <div className="w-full bg-zinc-800 rounded-full h-1 mt-1 overflow-hidden">
                                    <div
                                      className={`h-1 rounded-full ${
                                        m.ctxUtil >= 80 ? "bg-rose-400" :
                                        m.ctxUtil >= 50 ? "bg-amber-400" :
                                        "bg-emerald-400"
                                      }`}
                                      style={{ width: `${Math.min(100, Math.max(2, m.ctxUtil))}%` }}
                                    />
                                  </div>
                                )}
                              </div>
                            </div>
                          </div>

                          {/* Metric 3: Cost Efficiency */}
                          <div>
                            <h5 className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-2">
                              Cost Efficiency
                            </h5>
                            <div className="grid grid-cols-2 gap-2 text-xs">
                              <div className="flex justify-between items-center bg-zinc-900/40 rounded px-2.5 py-1.5">
                                <span className="text-zinc-400">Per 1K Tokens</span>
                                <span className="text-emerald-300 font-mono font-semibold">
                                  {m.cost1k !== null ? `$${m.cost1k.toFixed(4)}` : "—"}
                                </span>
                              </div>
                              <div className="flex justify-between items-center bg-zinc-900/40 rounded px-2.5 py-1.5">
                                <span className="text-zinc-400">Per Second</span>
                                <span className="text-emerald-300 font-mono font-semibold">
                                  {m.costSec !== null ? `$${m.costSec.toFixed(5)}` : "—"}
                                </span>
                              </div>
                            </div>
                          </div>

                          {/* Metric 4: Response Statistics */}
                          <div>
                            <h5 className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-2">
                              Response Length & Structure
                            </h5>
                            <div className="grid grid-cols-3 gap-2 text-xs">
                              <div className="flex justify-between items-center bg-zinc-900/40 rounded px-2.5 py-1.5">
                                <span className="text-zinc-400">Words</span>
                                <span className="text-zinc-200 font-mono font-semibold">
                                  {m.words ?? "—"}
                                </span>
                              </div>
                              <div className="flex justify-between items-center bg-zinc-900/40 rounded px-2.5 py-1.5">
                                <span className="text-zinc-400">Chars</span>
                                <span className="text-zinc-200 font-mono font-semibold">
                                  {m.chars ?? "—"}
                                </span>
                              </div>
                              <div className="flex justify-between items-center bg-zinc-900/40 rounded px-2.5 py-1.5">
                                <span className="text-zinc-400">Sentences</span>
                                <span className="text-zinc-200 font-mono font-semibold">
                                  {m.sentences ?? "—"}
                                </span>
                              </div>
                            </div>
                          </div>

                          {/* Metric 11: Streaming Stability */}
                          <div>
                            <h5 className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider mb-2">
                              Streaming Dynamics
                            </h5>
                            <div className="grid grid-cols-2 gap-2 text-xs">
                              <div className="flex justify-between items-center bg-zinc-900/40 rounded px-2.5 py-1.5">
                                <span className="text-zinc-400">Stream Chunks</span>
                                <span className="text-zinc-200 font-mono font-semibold">
                                  {m.chunks !== null ? `${m.chunks} deltas` : "Live Stream"}
                                </span>
                              </div>
                              <div className="flex justify-between items-center bg-zinc-900/40 rounded px-2.5 py-1.5">
                                <span className="text-zinc-400">Avg Chunk Size</span>
                                <span className="text-zinc-200 font-mono font-semibold">
                                  {m.avgChunk !== null ? `${m.avgChunk} chars` : "Steady"}
                                </span>
                              </div>
                            </div>
                          </div>
                        </div>
                      </details>

                      {/* Context Hash & Citation Verification Bar */}
                      {(run.context_hash || (run.citations_valid !== undefined && run.citations_valid !== null)) && (
                        <div className="px-4 py-1.5 border-b border-zinc-800/40 bg-zinc-950/20 flex flex-wrap items-center justify-between gap-1 text-[11px] font-mono">
                          {run.context_hash ? (
                            <span className="text-zinc-500 truncate" title={`Context hash: ${run.context_hash}`}>
                              hash: <span className="text-cyan-400 font-semibold">{run.context_hash.slice(0, 8)}…</span>
                            </span>
                          ) : <span />}

                          {run.citations_valid !== null && run.citations_valid !== undefined && (
                            run.citations_valid ? (
                              <span className="inline-flex items-center gap-1 text-emerald-400 text-[10px] bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/60 font-sans font-medium">
                                ✓ Citations valid
                              </span>
                            ) : (
                              <span
                                className="inline-flex items-center gap-1 text-rose-400 text-[10px] bg-rose-950/60 px-2 py-0.5 rounded border border-rose-800/60 font-sans font-medium"
                                title={`Invalid citations cited: ${run.invalid_citations?.join(", ") ?? "None"}`}
                              >
                                ✕ Invalid: {run.invalid_citations?.join(", ") ?? "None"}
                              </span>
                            )
                          )}
                        </div>
                      )}

                      {/* Response Text / Error details */}
                      <div className="flex-1 p-4 flex flex-col justify-between overflow-y-auto max-h-[300px]">
                        <div>
                          {run.error_message && (
                            <div className="mb-3 p-3 rounded bg-rose-950/50 border border-rose-800/80 text-rose-300 text-xs leading-relaxed">
                              <span className="font-semibold uppercase tracking-wide text-[10px] block mb-0.5">
                                Error Detail
                              </span>
                              {run.error_message}
                            </div>
                          )}

                          {run.response_text ? (
                            <div className="text-sm text-zinc-200 whitespace-pre-wrap leading-relaxed font-sans">
                              {run.response_text}
                            </div>
                          ) : (
                            <div className="text-xs text-zinc-600 italic">
                              No response text recorded.
                            </div>
                          )}
                        </div>

                        {run.finish_reason && (
                          <div className="mt-4 pt-2 border-t border-zinc-800/40 text-[11px] text-zinc-500 font-mono">
                            finish_reason: <span className="text-zinc-400">{run.finish_reason}</span>
                          </div>
                        )}
                      </div>

                      {/* Evaluation Scores Table */}
                      {run.evaluations && run.evaluations.length > 0 && (
                        <div className="p-3.5 border-t border-zinc-800/80 bg-zinc-950/40">
                          <div className="flex items-center justify-between mb-2">
                            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-400">
                              Evaluations ({run.evaluations.length})
                            </span>
                          </div>
                          <div className="space-y-2 max-h-[220px] overflow-y-auto pr-1">
                            {run.evaluations.map((ev) => (
                              <div
                                key={ev.id}
                                className="p-2 rounded bg-zinc-900/80 border border-zinc-800/70 text-xs flex flex-col gap-1"
                              >
                                <div className="flex items-center justify-between">
                                  <span className="font-mono font-medium text-violet-300">
                                    {ev.metric}
                                  </span>
                                  <span
                                    className={`font-mono font-bold px-1.5 py-0.5 rounded text-[10px] ${
                                      ev.score >= 0.8
                                        ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/80"
                                        : ev.score >= 0.5
                                        ? "bg-amber-950/80 text-amber-300 border border-amber-800/80"
                                        : "bg-rose-950/80 text-rose-300 border border-rose-800/80"
                                    }`}
                                  >
                                    {ev.score.toFixed(2)}
                                  </span>
                                </div>
                                {ev.judge_model && (
                                  <div className="text-[10px] text-zinc-500 font-mono">
                                    judge: {ev.judge_model}
                                  </div>
                                )}
                                {ev.reason && (
                                  <p className="text-[11px] text-zinc-300 leading-relaxed font-sans">
                                    {ev.reason}
                                  </p>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </section>
          </>
        ) : null}
      </main>

      <footer className="border-t border-zinc-800/60 py-3 px-6 text-center text-xs text-zinc-600">
        VersusLab Phase 12 • LLM Evaluation, Economics & Benchmarking Platform
      </footer>
    </div>
  );
}
