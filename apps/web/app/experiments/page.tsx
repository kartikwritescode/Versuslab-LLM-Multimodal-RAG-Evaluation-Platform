"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { BenchmarkDataset, ExperimentSummary } from "../../lib/types";
import {
  createExperiment,
  fetchDatasets,
  fetchExperiments,
  runExperiment,
} from "../../lib/race-client";

const AVAILABLE_MODELS = [
  { id: "mock:mock-1", label: "Mock Fast (0s, $0)", provider: "mock" },
  { id: "mock:mock-slow-1", label: "Mock Slow (1s, $0)", provider: "mock" },
  { id: "ollama:qwen3:8b", label: "Ollama Qwen 3 8B (Local, $0)", provider: "ollama" },
  { id: "openai:gpt-4o-mini", label: "OpenAI GPT-4o Mini", provider: "openai" },
  { id: "anthropic:claude-3-5-haiku-20241022", label: "Anthropic Claude 3.5 Haiku", provider: "anthropic" },
  { id: "gemini:gemini-3.5-flash", label: "Google Gemini 3.5 Flash", provider: "gemini" },
  { id: "grok:grok-2-1212", label: "xAI Grok 2", provider: "grok" },
  { id: "deepseek:deepseek-chat", label: "DeepSeek V3 (deepseek-chat)", provider: "deepseek" },
];

export default function ExperimentsPage() {
  const router = useRouter();
  const [experiments, setExperiments] = useState<ExperimentSummary[]>([]);
  const [datasets, setDatasets] = useState<BenchmarkDataset[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // New Experiment Form State
  const [showModal, setShowModal] = useState(false);
  const [name, setName] = useState("VersusLab Multi-Model Benchmark");
  const [selectedDatasetId, setSelectedDatasetId] = useState("");
  const [selectedModels, setSelectedModels] = useState<string[]>([
    "mock:mock-1",
    "mock:mock-slow-1",
  ]);
  const [includeJudge, setIncludeJudge] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    async function loadData() {
      setLoading(true);
      setError(null);
      try {
        const [expList, dsList] = await Promise.all([
          fetchExperiments(),
          fetchDatasets(),
        ]);
        setExperiments(expList);
        setDatasets(dsList);
        if (dsList.length > 0 && !selectedDatasetId) {
          setSelectedDatasetId(dsList[0].id);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  const handleToggleModel = (modelId: string) => {
    if (selectedModels.includes(modelId)) {
      if (selectedModels.length > 1) {
        setSelectedModels(selectedModels.filter((m) => m !== modelId));
      }
    } else {
      setSelectedModels([...selectedModels, modelId]);
    }
  };

  const handleCreateAndRun = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedDatasetId || selectedModels.length === 0) return;

    setSubmitting(true);
    setError(null);
    try {
      const exp = await createExperiment({
        name,
        dataset_id: selectedDatasetId,
        models: selectedModels,
        include_llm_judge: includeJudge,
      });

      await runExperiment(exp.id);
      router.push(`/experiments/${exp.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      setSubmitting(false);
    }
  };

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
      return d.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return isoString;
    }
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
                Experiment Engine & Benchmark Runner
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowModal(true)}
              className="px-4 py-2 rounded-lg text-sm font-semibold bg-gradient-to-r from-violet-600 to-indigo-600 hover:from-violet-500 hover:to-indigo-500 text-white transition-all shadow-md shadow-violet-600/20 border border-violet-500/40 cursor-pointer flex items-center gap-2"
            >
              + New Experiment
            </button>
            <Link
              href="/"
              className="px-3.5 py-2 rounded-lg text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition-colors"
            >
              Race
            </Link>
            <Link
              href="/history"
              className="px-3.5 py-2 rounded-lg text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition-colors"
            >
              History
            </Link>
          </div>
        </div>
      </header>

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-8 flex flex-col gap-6">
        {error && (
          <div className="p-4 rounded-lg bg-rose-950/60 border border-rose-800 text-rose-200 text-sm">
            <p className="font-semibold">Error</p>
            <p className="mt-0.5">{error}</p>
          </div>
        )}

        {/* Datasets Summary Card */}
        <section className="bg-zinc-900/40 border border-zinc-800/80 rounded-xl p-5 shadow-sm">
          <div className="flex items-center justify-between border-b border-zinc-800/70 pb-3 mb-4">
            <div>
              <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wider">
                Available Benchmark Datasets
              </h2>
              <p className="text-xs text-zinc-400 mt-0.5">
                Immutable test suites used for reproducible evaluation experiments
              </p>
            </div>
            <span className="text-xs font-mono px-2 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
              {datasets.length} versioned datasets
            </span>
          </div>

          {datasets.length === 0 ? (
            <div className="text-center py-6 text-xs text-zinc-500">
              No datasets loaded yet. Run <code className="text-violet-400">python scripts/load_benchmark_dataset.py</code> to load the seed benchmark.
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {datasets.map((ds) => (
                <div
                  key={ds.id}
                  className="p-4 rounded-lg bg-zinc-950/60 border border-zinc-800/60 text-xs flex flex-col justify-between"
                >
                  <div>
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold text-zinc-100">{ds.name}</h3>
                      <span className="px-2 py-0.5 rounded bg-violet-950/70 text-violet-300 border border-violet-800/60 font-mono text-[10px]">
                        v{ds.version}
                      </span>
                    </div>
                    {ds.description && (
                      <p className="text-zinc-400 mt-1 line-clamp-2 leading-relaxed">
                        {ds.description}
                      </p>
                    )}
                  </div>
                  <div className="mt-3 pt-2 border-t border-zinc-900 flex items-center justify-between text-zinc-500 font-mono text-[11px]">
                    <span>{ds.case_count ?? 0} benchmark cases</span>
                    <span>{formatDate(ds.created_at)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Experiments List */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold text-zinc-200 uppercase tracking-wider">
                Experiment History ({experiments.length})
              </h2>
              <p className="text-xs text-zinc-400 mt-0.5">
                Multi-model evaluations with deterministic scores and Pareto tradeoffs
              </p>
            </div>
          </div>

          {loading ? (
            <div className="border border-dashed border-zinc-800 rounded-xl p-12 text-center text-zinc-500 text-sm">
              Loading experiments...
            </div>
          ) : experiments.length === 0 ? (
            <div className="border border-dashed border-zinc-800 rounded-xl p-12 text-center text-zinc-500 text-sm">
              No experiments recorded yet. Click <strong className="text-violet-400">+ New Experiment</strong> above to launch your first run.
            </div>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-zinc-800/80 bg-zinc-900/40 shadow-sm">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-zinc-800/80 bg-zinc-900/80 text-zinc-400 font-medium">
                    <th className="py-3 px-4">Experiment Name</th>
                    <th className="py-3 px-4">Dataset</th>
                    <th className="py-3 px-4">Models</th>
                    <th className="py-3 px-4">Git Commit</th>
                    <th className="py-3 px-4">Status</th>
                    <th className="py-3 px-4">Created</th>
                    <th className="py-3 px-4 text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-800/60 font-mono">
                  {experiments.map((exp) => (
                    <tr
                      key={exp.id}
                      className="hover:bg-zinc-800/30 transition-colors"
                    >
                      <td className="py-3 px-4 font-sans font-medium text-zinc-100">
                        <Link
                          href={`/experiments/${exp.id}`}
                          className="hover:text-violet-400 transition-colors"
                        >
                          {exp.name}
                        </Link>
                      </td>
                      <td className="py-3 px-4 text-zinc-300">
                        {exp.dataset_name}{" "}
                        <span className="text-zinc-500 text-[10px]">
                          v{exp.dataset_version}
                        </span>
                      </td>
                      <td className="py-3 px-4 text-zinc-400">
                        <span className="px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 border border-zinc-700 text-[11px]">
                          {exp.model_count} models
                        </span>
                      </td>
                      <td className="py-3 px-4 text-zinc-500 text-[11px]">
                        {exp.git_commit ? (
                          <span className="font-mono text-cyan-400">
                            {exp.git_commit.slice(0, 7)}
                          </span>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="py-3 px-4">{getStatusBadge(exp.status)}</td>
                      <td className="py-3 px-4 text-zinc-400 font-sans">
                        {formatDate(exp.created_at)}
                      </td>
                      <td className="py-3 px-4 text-right font-sans">
                        <Link
                          href={`/experiments/${exp.id}`}
                          className="px-3 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700 transition-colors text-xs inline-block"
                        >
                          View Results →
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </main>

      {/* New Experiment Modal */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 max-w-lg w-full shadow-2xl space-y-5">
            <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
              <h2 className="text-base font-semibold text-zinc-100">
                Create New Benchmark Experiment
              </h2>
              <button
                onClick={() => setShowModal(false)}
                className="text-zinc-400 hover:text-zinc-200 text-sm cursor-pointer"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateAndRun} className="space-y-4 text-xs">
              <div>
                <label className="block text-zinc-300 font-medium mb-1">
                  Experiment Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                  className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-100 focus:outline-none focus:border-violet-500"
                />
              </div>

              <div>
                <label className="block text-zinc-300 font-medium mb-1">
                  Benchmark Dataset
                </label>
                <select
                  value={selectedDatasetId}
                  onChange={(e) => setSelectedDatasetId(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-zinc-950 border border-zinc-800 text-zinc-100 focus:outline-none focus:border-violet-500"
                >
                  {datasets.map((ds) => (
                    <option key={ds.id} value={ds.id}>
                      {ds.name} (v{ds.version}, {ds.case_count ?? 0} cases)
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-zinc-300 font-medium mb-1">
                  Contender Models ({selectedModels.length} selected)
                </label>
                <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                  {AVAILABLE_MODELS.map((m) => (
                    <label
                      key={m.id}
                      className="flex items-center gap-2 p-2 rounded bg-zinc-950/60 border border-zinc-800/80 cursor-pointer hover:border-zinc-700"
                    >
                      <input
                        type="checkbox"
                        checked={selectedModels.includes(m.id)}
                        onChange={() => handleToggleModel(m.id)}
                        className="rounded border-zinc-700 text-violet-600 focus:ring-0"
                      />
                      <span className="font-mono text-zinc-200">{m.id}</span>
                      <span className="text-[11px] text-zinc-500 ml-auto">
                        {m.label}
                      </span>
                    </label>
                  ))}
                </div>
              </div>

              <div className="pt-2 border-t border-zinc-800">
                <label className="flex items-start gap-2.5 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={includeJudge}
                    onChange={(e) => setIncludeJudge(e.target.checked)}
                    className="mt-0.5 rounded border-zinc-700 text-violet-600 focus:ring-0"
                  />
                  <div>
                    <span className="text-zinc-200 font-medium block">
                      Include Blind LLM-as-a-Judge Evaluation
                    </span>
                    <span className="text-[11px] text-zinc-500 leading-snug block">
                      Invokes configured judge model to score correctness, relevance, completeness, and instruction-following. Disabled by default to prevent unexpected API costs.
                    </span>
                  </div>
                </label>
              </div>

              <div className="flex items-center justify-end gap-3 pt-3 border-t border-zinc-800">
                <button
                  type="button"
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 rounded-lg text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-300 transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting || selectedModels.length === 0}
                  className="px-4 py-2 rounded-lg text-xs font-semibold bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white transition-all cursor-pointer shadow-md shadow-violet-600/20"
                >
                  {submitting ? "Launching..." : "Launch Experiment"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      <footer className="border-t border-zinc-800/60 py-3 px-6 text-center text-xs text-zinc-600">
        VersusLab Phase 9 • Experiment Engine & Benchmarking Platform
      </footer>
    </div>
  );
}
