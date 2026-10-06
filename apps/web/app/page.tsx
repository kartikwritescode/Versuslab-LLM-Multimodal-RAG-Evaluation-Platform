"use client";

import React, { useState, useRef, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  ContenderState,
  DocumentItem,
  ModelStatus,
  RaceEvent,
} from "../lib/types";
import {
  cancelRace,
  fetchDocuments,
  startRaceStream,
} from "../lib/race-client";
import DocumentManager from "./components/DocumentManager";

interface ModelOption {
  id: string;
  name: string;
  category: "Mock" | "Local" | "Cloud";
  provider: string;
  icon: string;
  description: string;
}

const AVAILABLE_MODELS: ModelOption[] = [
  {
    id: "mock:mock-1",
    name: "Mock (Fast)",
    category: "Mock",
    provider: "mock",
    icon: "⚡",
    description: "Instant start, 20 tokens/sec",
  },
  {
    id: "mock-slow:mock-slow-1",
    name: "Mock (Slow)",
    category: "Mock",
    provider: "mock",
    icon: "⏱",
    description: "1.0s TTFT, 4 tokens/sec",
  },
  {
    id: "mock-broken:mock-broken-1",
    name: "Mock (Broken)",
    category: "Mock",
    provider: "mock",
    icon: "💥",
    description: "Throws error after 3 tokens",
  },
  {
    id: "mock-stuck:mock-stuck-1",
    name: "Mock (Stuck)",
    category: "Mock",
    provider: "mock",
    icon: "⏸",
    description: "Simulates hung model with 999s delay",
  },
  {
    id: "ollama:qwen3:8b",
    name: "Ollama (qwen3:8b)",
    category: "Local",
    provider: "ollama",
    icon: "🦙",
    description: "Local Ollama engine (Qwen 3 8B, $0/token)",
  },
  {
    id: "openai:gpt-4o-mini",
    name: "OpenAI (gpt-4o-mini)",
    category: "Cloud",
    provider: "openai",
    icon: "🟢",
    description: "Fast general-purpose chat",
  },
  {
    id: "anthropic:claude-3-5-haiku-20241022",
    name: "Claude (3.5 Haiku)",
    category: "Cloud",
    provider: "anthropic",
    icon: "🟠",
    description: "High speed, low latency reasoning",
  },
  {
    id: "gemini:gemini-3.5-flash",
    name: "Gemini (3.5 Flash)",
    category: "Cloud",
    provider: "gemini",
    icon: "✨",
    description: "Google Gemini 3.5 Flash multimodal low latency chat",
  },
  {
    id: "grok:grok-2-1212",
    name: "Grok (grok-2-1212)",
    category: "Cloud",
    provider: "grok",
    icon: "⚫",
    description: "xAI chat model",
  },
  {
    id: "deepseek:deepseek-chat",
    name: "DeepSeek (deepseek-chat)",
    category: "Cloud",
    provider: "deepseek",
    icon: "🐋",
    description: "DeepSeek-V3 fast reasoning chat",
  },
];

const PRESET_PROMPTS = [
  {
    title: "⚡ Sync vs Async",
    prompt: "Explain the difference between synchronous and asynchronous programming in 3 concise bullet points.",
  },
  {
    title: "🧠 Hybrid RAG Search",
    prompt: "How does Hybrid Retrieval (combining Dense Vector embeddings with BM25 keyword matching) improve RAG answer faithfulness?",
  },
  {
    title: "🚀 Python Retry Pattern",
    prompt: "Write a production-grade async retry function in Python with exponential backoff, jitter, and cancellation handling.",
  },
  {
    title: "📄 Document Summary",
    prompt: "Based on the attached document, summarize the key components and requirements in 4 numbered takeaways with [S1], [S2] citations.",
  },
];

const DEFAULT_PROMPT = PRESET_PROMPTS[0].prompt;

function getNow(): number {
  return typeof performance !== "undefined" ? performance.now() : Date.now();
}

export default function RacePage() {
  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [selectedModels, setSelectedModels] = useState<string[]>([
    "mock:mock-1",
    "ollama:qwen3:8b",
  ]);
  const [temperature, setTemperature] = useState(0.7);
  const [maxTokens, setMaxTokens] = useState<number | undefined>(undefined);

  const [isRunning, setIsRunning] = useState(false);
  const [activeRaceId, setActiveRaceId] = useState<string | null>(null);
  const [globalError, setGlobalError] = useState<string | null>(null);
  const [contenders, setContenders] = useState<Record<string, ContenderState>>({});

  // RAG Document Attachment state
  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);

  // Load available documents on mount
  useEffect(() => {
    async function loadDocs() {
      try {
        const docs = await fetchDocuments();
        setDocuments(docs);
      } catch (err) {
        console.error("Failed to load documents:", err);
      }
    }
    loadDocs();
  }, []);

  const handleDocumentUploaded = (doc: DocumentItem) => {
    setDocuments((prev) => {
      const exists = prev.some((d) => d.id === doc.id);
      return exists ? prev : [doc, ...prev];
    });
  };

  // Refs for tracking execution state across callbacks
  const abortControllerRef = useRef<AbortController | null>(null);
  const activeRaceIdRef = useRef<string | null>(null);
  const raceStartTimeRef = useRef<number | null>(null);
  const pendingDeltasRef = useRef<Record<string, string>>({});
  const rafHandleRef = useRef<number | null>(null);
  const contendersRef = useRef<Record<string, ContenderState>>({});

  // Keep contendersRef in sync with state for access in event callbacks
  useEffect(() => {
    contendersRef.current = contenders;
  }, [contenders]);

  // Flush RAF delta buffer
  const flushBatch = useCallback(() => {
    const deltas = pendingDeltasRef.current;
    pendingDeltasRef.current = {};
    rafHandleRef.current = null;

    const modelIds = Object.keys(deltas);
    if (modelIds.length === 0) return;

    setContenders((prev) => {
      let changed = false;
      const updated = { ...prev };

      for (const modelId of modelIds) {
        const chunk = deltas[modelId];
        if (chunk && updated[modelId]) {
          changed = true;
          updated[modelId] = {
            ...updated[modelId],
            text: updated[modelId].text + chunk,
          };
        }
      }

      return changed ? updated : prev;
    });
  }, []);

  const scheduleFlush = useCallback(() => {
    if (rafHandleRef.current === null) {
      rafHandleRef.current = requestAnimationFrame(flushBatch);
    }
  }, [flushBatch]);

  // Live timer tick for active models
  useEffect(() => {
    if (!isRunning) return;

    const interval = setInterval(() => {
      const now = getNow();
      setContenders((prev) => {
        let changed = false;
        const updated = { ...prev };

        for (const [id, c] of Object.entries(updated)) {
          if (c.status === "queued" || c.status === "streaming") {
            const start = c.startTime ?? raceStartTimeRef.current ?? now;
            const elapsed = Math.max(0, Math.round(now - start));
            if (elapsed !== c.elapsedMs) {
              changed = true;
              updated[id] = { ...c, elapsedMs: elapsed };
            }
          }
        }

        return changed ? updated : prev;
      });
    }, 50);

    return () => clearInterval(interval);
  }, [isRunning]);

  // Clean up on unmount
  useEffect(() => {
    return () => {
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
      if (rafHandleRef.current !== null) {
        cancelAnimationFrame(rafHandleRef.current);
      }
    };
  }, []);

  const toggleModel = (id: string) => {
    if (isRunning) return;
    setSelectedModels((prev) =>
      prev.includes(id) ? prev.filter((m) => m !== id) : [...prev, id]
    );
  };

  const handleStop = useCallback(async () => {
    if (!isRunning) return;

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }

    const raceId = activeRaceIdRef.current;
    if (raceId) {
      await cancelRace(raceId);
    }

    flushBatch();

    const now = getNow();
    setContenders((prev) => {
      const updated = { ...prev };
      for (const [id, c] of Object.entries(updated)) {
        if (c.status === "queued" || c.status === "streaming") {
          const start = c.startTime ?? raceStartTimeRef.current ?? now;
          updated[id] = {
            ...c,
            status: "cancelled",
            endTime: now,
            elapsedMs: Math.round(now - start),
            error: "Cancelled by user",
          };
        }
      }
      return updated;
    });

    setIsRunning(false);
  }, [flushBatch, isRunning]);

  const handleIncomingEvent = useCallback((event: RaceEvent) => {
    const now = getNow();

    switch (event.type) {
      case "race.started": {
        setActiveRaceId(event.race_id);
        activeRaceIdRef.current = event.race_id;
        break;
      }

      case "model.started": {
        if (!event.model_id) break;
        const mid = event.model_id;
        setContenders((prev) => {
          const current = prev[mid];
          if (!current) return prev;
          return {
            ...prev,
            [mid]: {
              ...current,
              status: "streaming",
              startTime: now,
            },
          };
        });
        break;
      }

      case "model.delta": {
        if (!event.model_id) break;
        const mid = event.model_id;

        if (event.text) {
          const current = contendersRef.current[mid];
          if (current && current.firstTokenTime === null) {
            const start = current.startTime ?? raceStartTimeRef.current ?? now;
            const ttft = Math.round(now - start);
            setContenders((prev) => {
              const c = prev[mid];
              if (!c || c.firstTokenTime !== null) return prev;
              return {
                ...prev,
                [mid]: {
                  ...c,
                  firstTokenTime: now,
                  ttftMs: ttft,
                },
              };
            });
          }

          pendingDeltasRef.current[mid] =
            (pendingDeltasRef.current[mid] || "") + event.text;
          scheduleFlush();
        }
        break;
      }

      case "model.completed": {
        if (!event.model_id) break;
        const mid = event.model_id;
        flushBatch();

        setContenders((prev) => {
          const current = prev[mid];
          if (!current) return prev;
          const start = current.startTime ?? raceStartTimeRef.current ?? now;
          return {
            ...prev,
            [mid]: {
              ...current,
              status: "done",
              endTime: now,
              elapsedMs: Math.round(now - start),
              finishReason: event.finish_reason ?? null,
              usage: event.usage ?? null,
            },
          };
        });
        break;
      }

      case "model.error": {
        if (!event.model_id) break;
        const mid = event.model_id;
        flushBatch();

        setContenders((prev) => {
          const current = prev[mid];
          if (!current) return prev;
          const start = current.startTime ?? raceStartTimeRef.current ?? now;
          return {
            ...prev,
            [mid]: {
              ...current,
              status: "error",
              endTime: now,
              elapsedMs: Math.round(now - start),
              error: event.error || "Model error encountered",
            },
          };
        });
        break;
      }

      case "model.timeout": {
        if (!event.model_id) break;
        const mid = event.model_id;
        flushBatch();

        setContenders((prev) => {
          const current = prev[mid];
          if (!current) return prev;
          const start = current.startTime ?? raceStartTimeRef.current ?? now;
          return {
            ...prev,
            [mid]: {
              ...current,
              status: "timeout",
              endTime: now,
              elapsedMs: Math.round(now - start),
              error: event.error || "Request timed out",
            },
          };
        });
        break;
      }

      case "model.cancelled": {
        if (!event.model_id) break;
        const mid = event.model_id;
        flushBatch();

        setContenders((prev) => {
          const current = prev[mid];
          if (!current) return prev;
          const start = current.startTime ?? raceStartTimeRef.current ?? now;
          return {
            ...prev,
            [mid]: {
              ...current,
              status: "cancelled",
              endTime: now,
              elapsedMs: Math.round(now - start),
              error: event.error || "Execution cancelled",
            },
          };
        });
        break;
      }

      case "race.completed":
      case "race.cancelled": {
        flushBatch();
        setIsRunning(false);
        break;
      }
    }
  }, [flushBatch, scheduleFlush]);

  const handleRunRace = useCallback(async () => {
    if (isRunning) return;
    if (selectedModels.length === 0) {
      setGlobalError("Please select at least one model to race.");
      return;
    }
    if (!prompt.trim()) {
      setGlobalError("Prompt cannot be empty.");
      return;
    }

    setGlobalError(null);
    setIsRunning(true);
    setActiveRaceId(null);
    activeRaceIdRef.current = null;

    const startInstant = getNow();
    raceStartTimeRef.current = startInstant;

    const initialContenders: Record<string, ContenderState> = {};
    for (const modelId of selectedModels) {
      initialContenders[modelId] = {
        modelId,
        status: "queued",
        text: "",
        ttftMs: null,
        elapsedMs: 0,
        startTime: null,
        firstTokenTime: null,
        endTime: null,
        finishReason: null,
        usage: null,
        error: null,
      };
    }
    setContenders(initialContenders);
    pendingDeltasRef.current = {};

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    try {
      await startRaceStream(
        {
          prompt: prompt.trim(),
          models: selectedModels,
          temperature,
          max_tokens: maxTokens,
          document_id: selectedDocumentId,
        },
        (event: RaceEvent) => {
          handleIncomingEvent(event);
        },
        abortController.signal
      );
    } catch (err: unknown) {
      if (!abortController.signal.aborted) {
        const msg = err instanceof Error ? err.message : String(err);
        setGlobalError(`Race failed: ${msg}`);
      }
    } finally {
      flushBatch();
      setIsRunning(false);
    }
  }, [
    flushBatch,
    handleIncomingEvent,
    isRunning,
    maxTokens,
    prompt,
    selectedDocumentId,
    selectedModels,
    temperature,
  ]);

  const getStatusBadge = (status: ModelStatus) => {
    switch (status) {
      case "queued":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-zinc-800/80 text-zinc-400 border border-zinc-700/60 shadow-sm">
            <span className="h-1.5 w-1.5 rounded-full bg-zinc-400 animate-pulse" />
            Queued
          </span>
        );
      case "streaming":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-950/80 text-emerald-300 border border-emerald-700/80 shadow-sm shadow-emerald-950/40">
            <span className="h-2 w-2 rounded-full bg-emerald-400 animate-ping" />
            Streaming
          </span>
        );
      case "done":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-cyan-950/70 text-cyan-300 border border-cyan-700/60 shadow-sm">
            ✓ Finished
          </span>
        );
      case "error":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-950/80 text-rose-300 border border-rose-800/80 shadow-sm">
            ✕ Error
          </span>
        );
      case "timeout":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-950/80 text-amber-300 border border-amber-800/80 shadow-sm">
            ⏱ Timeout
          </span>
        );
      case "cancelled":
        return (
          <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-zinc-800 text-zinc-400 border border-zinc-700 shadow-sm">
            ⊘ Cancelled
          </span>
        );
    }
  };

  const contenderKeys = Object.keys(contenders);

  // Identify the fastest TTFT winner among completed models
  const fastestTTFT = contenderKeys.reduce<number | null>((min, key) => {
    const c = contenders[key];
    if (c && c.status === "done" && c.ttftMs !== null) {
      if (min === null || c.ttftMs < min) return c.ttftMs;
    }
    return min;
  }, null);

  const getGridColsClass = (count: number) => {
    if (count <= 1) return "grid-cols-1";
    if (count === 2) return "grid-cols-1 md:grid-cols-2";
    if (count === 3) return "grid-cols-1 md:grid-cols-2 lg:grid-cols-3";
    return "grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4";
  };

  return (
    <div className="flex-1 flex flex-col min-h-screen bg-zinc-950 text-zinc-100 bg-ambient-radial">
      {/* Modern Sticky Header */}
      <header className="border-b border-zinc-800/80 bg-zinc-950/75 backdrop-blur-xl sticky top-0 z-40 px-6 py-3.5 transition-all">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          {/* Logo & Platform Info */}
          <div className="flex items-center gap-3.5">
            <div className="h-9 w-9 rounded-xl bg-gradient-to-tr from-violet-600 via-indigo-600 to-cyan-400 flex items-center justify-center font-bold text-white shadow-lg shadow-violet-600/30 text-base">
              ⚡
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-bold tracking-tight text-white leading-none">
                  VersusLab
                </h1>
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-violet-950 text-violet-300 border border-violet-700/60 uppercase tracking-wider">
                  Arena
                </span>
              </div>
              <p className="text-[11px] text-zinc-400 mt-1 flex items-center gap-2">
                <span>Multiplexed Live LLM Streaming & Evaluation</span>
                <span className="h-1 w-1 rounded-full bg-zinc-600" />
                <span className="text-emerald-400 flex items-center gap-1 font-mono text-[10px]">
                  <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  FastAPI Engine Online
                </span>
              </p>
            </div>
          </div>

          {/* Navigation & Controls */}
          <div className="flex items-center gap-3">
            <nav className="flex items-center gap-1.5 bg-zinc-900/60 p-1 rounded-xl border border-zinc-800/80">
              <Link
                href="/"
                className="px-3 py-1.5 rounded-lg text-xs font-medium bg-zinc-800 text-white shadow-sm transition-all flex items-center gap-1.5"
              >
                <span>🏁</span>
                <span>Race</span>
              </Link>
              <Link
                href="/experiments"
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-zinc-400 hover:text-white hover:bg-zinc-800/60 transition-all flex items-center gap-1.5"
              >
                <span>⚡</span>
                <span>Benchmarks</span>
              </Link>
              <Link
                href="/history"
                className="px-3 py-1.5 rounded-lg text-xs font-medium text-zinc-400 hover:text-white hover:bg-zinc-800/60 transition-all flex items-center gap-1.5"
              >
                <span>📜</span>
                <span>History</span>
              </Link>
            </nav>

            {/* Run Race Action */}
            {isRunning ? (
              <button
                type="button"
                onClick={handleStop}
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-900/40 transition-all flex items-center gap-2 cursor-pointer animate-pulse"
              >
                <span className="h-2 w-2 rounded-sm bg-white" />
                <span>Stop Race</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={handleRunRace}
                disabled={selectedModels.length === 0 || !prompt.trim()}
                className="px-5 py-2 rounded-xl text-xs font-semibold bg-gradient-to-r from-violet-600 via-indigo-600 to-cyan-500 hover:from-violet-500 hover:via-indigo-500 hover:to-cyan-400 disabled:opacity-50 disabled:cursor-not-allowed text-white shadow-lg shadow-violet-600/30 hover:shadow-violet-600/50 hover:scale-[1.02] active:scale-[0.98] transition-all flex items-center gap-2 cursor-pointer"
              >
                <svg className="w-3.5 h-3.5 fill-current" viewBox="0 0 24 24">
                  <path d="M8 5v14l11-7z" />
                </svg>
                <span>Run Race</span>
                <span className="hidden sm:inline-block px-1.5 py-0.2 rounded bg-white/20 text-[10px] font-mono">
                  Ctrl+↵
                </span>
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Main Workspace */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-6 py-6 flex flex-col gap-6">
        {/* Global Error Banner */}
        {globalError && (
          <div className="p-4 rounded-xl bg-rose-950/70 border border-rose-800 text-rose-200 text-xs flex items-start justify-between shadow-xl shadow-rose-950/20 animate-in fade-in">
            <div className="flex items-start gap-2.5">
              <span className="text-base">⚠️</span>
              <div>
                <p className="font-semibold text-rose-100">Race Failure</p>
                <p className="mt-0.5 text-rose-300 leading-relaxed">{globalError}</p>
              </div>
            </div>
            <button
              onClick={() => setGlobalError(null)}
              className="text-rose-400 hover:text-white text-sm ml-4 cursor-pointer"
            >
              ✕
            </button>
          </div>
        )}

        {/* Configuration Cockpit */}
        <section className="glass-panel rounded-2xl p-5 shadow-2xl space-y-5">
          {/* Prompt Section */}
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <label
                htmlFor="prompt-input"
                className="text-xs font-semibold uppercase tracking-wider text-zinc-300 flex items-center gap-2"
              >
                <span>💬</span>
                <span>Experiment Prompt</span>
              </label>
              <span className="text-[11px] text-zinc-500 font-mono">
                Fairness Rule: Broadcasted identically to all contender models
              </span>
            </div>

            <textarea
              id="prompt-input"
              rows={3}
              value={prompt}
              disabled={isRunning}
              onChange={(e) => setPrompt(e.target.value)}
              onKeyDown={(e) => {
                if ((e.ctrlKey || e.metaKey) && e.key === "Enter" && !isRunning) {
                  e.preventDefault();
                  handleRunRace();
                }
              }}
              placeholder="Enter your prompt here, or select a preset below..."
              className="w-full bg-zinc-950/80 border border-zinc-800/90 rounded-xl p-3.5 text-sm text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-violet-500 focus:ring-2 focus:ring-violet-500/20 transition-all disabled:opacity-60 resize-y font-sans shadow-inner"
            />

            {/* Quick Preset Prompt Chips */}
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <span className="text-[11px] text-zinc-500 uppercase tracking-wider font-semibold">
                Presets:
              </span>
              {PRESET_PROMPTS.map((preset, idx) => (
                <button
                  key={idx}
                  type="button"
                  disabled={isRunning}
                  onClick={() => setPrompt(preset.prompt)}
                  className="px-2.5 py-1 rounded-lg bg-zinc-900/90 hover:bg-zinc-800 text-zinc-400 hover:text-zinc-200 border border-zinc-800 hover:border-zinc-700 text-xs transition-colors cursor-pointer disabled:opacity-50"
                >
                  {preset.title}
                </button>
              ))}
            </div>
          </div>

          {/* Enhanced Document Attachment (RAG Context) */}
          <div className="pt-4 border-t border-zinc-800/70">
            <DocumentManager
              documents={documents}
              selectedDocumentId={selectedDocumentId}
              onSelectDocument={setSelectedDocumentId}
              onDocumentUploaded={handleDocumentUploaded}
              disabled={isRunning}
            />
          </div>

          {/* Model Contender Selector & Parameters */}
          <div className="pt-4 border-t border-zinc-800/70 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-zinc-300 flex items-center gap-1.5">
                  <span>🏁</span>
                  <span>Select Contenders ({selectedModels.length} selected, max 8)</span>
                </span>
              </div>

              <div className="flex items-center gap-4 text-xs">
                <div className="flex items-center gap-2 bg-zinc-950/60 px-3 py-1.5 rounded-lg border border-zinc-800/80">
                  <label htmlFor="temp-input" className="text-zinc-400 font-medium">
                    Temp:
                  </label>
                  <input
                    id="temp-input"
                    type="number"
                    step="0.1"
                    min="0"
                    max="2"
                    value={temperature}
                    disabled={isRunning}
                    onChange={(e) => setTemperature(parseFloat(e.target.value) || 0.7)}
                    className="w-14 bg-zinc-900 border border-zinc-700/60 rounded px-1.5 py-0.5 text-xs text-zinc-100 text-center focus:outline-none focus:border-violet-500"
                  />
                </div>

                <div className="flex items-center gap-2 bg-zinc-950/60 px-3 py-1.5 rounded-lg border border-zinc-800/80">
                  <label htmlFor="max-tokens-input" className="text-zinc-400 font-medium">
                    Max tokens:
                  </label>
                  <input
                    id="max-tokens-input"
                    type="number"
                    placeholder="None"
                    value={maxTokens ?? ""}
                    disabled={isRunning}
                    onChange={(e) => {
                      const v = parseInt(e.target.value, 10);
                      setMaxTokens(isNaN(v) ? undefined : v);
                    }}
                    className="w-16 bg-zinc-900 border border-zinc-700/60 rounded px-1.5 py-0.5 text-xs text-zinc-100 text-center focus:outline-none focus:border-violet-500"
                  />
                </div>
              </div>
            </div>

            {/* Model Multi-Select Chips with Category Badges */}
            <div className="flex flex-wrap gap-2.5">
              {AVAILABLE_MODELS.map((model) => {
                const isSelected = selectedModels.includes(model.id);
                return (
                  <button
                    key={model.id}
                    type="button"
                    disabled={isRunning}
                    onClick={() => toggleModel(model.id)}
                    title={model.description}
                    className={`px-3 py-2 rounded-xl text-xs font-medium border transition-all cursor-pointer flex items-center gap-2.5 ${
                      isSelected
                        ? "bg-violet-950/70 border-violet-500 text-white shadow-md shadow-violet-950/50 scale-[1.02]"
                        : "bg-zinc-950/60 border-zinc-800/80 text-zinc-400 hover:border-zinc-700 hover:text-zinc-200 hover:bg-zinc-900/60"
                    } ${isRunning ? "opacity-60 cursor-not-allowed" : ""}`}
                  >
                    <span className="text-sm shrink-0">{model.icon}</span>
                    <span className="font-semibold">{model.name}</span>
                    <span
                      className={`text-[9px] px-1.5 py-0.5 rounded font-mono uppercase tracking-wider ${
                        model.category === "Mock"
                          ? "bg-zinc-800 text-zinc-400"
                          : model.category === "Local"
                          ? "bg-emerald-950/90 text-emerald-300 border border-emerald-800/80"
                          : "bg-cyan-950/90 text-cyan-300 border border-cyan-800/80"
                      }`}
                    >
                      {model.category}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </section>

        {/* Live Race Contender Columns */}
        {contenderKeys.length === 0 ? (
          <div className="flex-1 border-2 border-dashed border-zinc-800/80 rounded-2xl p-12 flex flex-col items-center justify-center text-center glass-panel">
            <div className="h-14 w-14 rounded-2xl bg-zinc-900 border border-zinc-800 flex items-center justify-center text-2xl mb-3 shadow-inner">
              ⚡
            </div>
            <h3 className="text-sm font-semibold text-zinc-200">
              Arena Ready
            </h3>
            <p className="text-xs text-zinc-500 mt-1.5 max-w-md leading-relaxed">
              Select your models and optional knowledge document above, then click <strong className="text-violet-400">Run Race</strong> to stream responses concurrently over one multiplexed SSE connection.
            </p>
          </div>
        ) : (
          <section className="flex-1 flex flex-col space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
                  Live Contenders ({contenderKeys.length})
                </span>
                {activeRaceId && (
                  <span className="text-[10px] text-zinc-500 font-mono">
                    ID: {activeRaceId.slice(0, 8)}...
                  </span>
                )}
              </div>
              <span className="text-xs text-zinc-400 font-mono flex items-center gap-1.5">
                {isRunning ? (
                  <>
                    <span className="h-2 w-2 rounded-full bg-emerald-400 animate-ping" />
                    <span className="text-emerald-400 font-medium">Racing Models...</span>
                  </>
                ) : (
                  <span className="text-zinc-500">Race Concluded</span>
                )}
              </span>
            </div>

            <div className={`grid ${getGridColsClass(contenderKeys.length)} gap-4 flex-1 items-stretch`}>
              {contenderKeys.map((modelId) => {
                const c = contenders[modelId];
                const option = AVAILABLE_MODELS.find((m) => m.id === modelId);
                const displayName = option ? option.name : modelId;
                const isFastest = fastestTTFT !== null && c.status === "done" && c.ttftMs === fastestTTFT;

                // Calculate throughput (tokens / second)
                const elapsedSeconds = c.elapsedMs / 1000;
                const tokPerSec =
                  c.usage && elapsedSeconds > 0
                    ? (c.usage.output_tokens / elapsedSeconds).toFixed(1)
                    : null;

                return (
                  <div
                    key={modelId}
                    className={`flex flex-col rounded-2xl overflow-hidden glass-panel shadow-lg transition-all ${
                      isFastest ? "ring-2 ring-violet-500/80 shadow-violet-950/30" : "hover:border-zinc-700/80"
                    }`}
                  >
                    {/* Contender Card Header */}
                    <div className="px-4 py-3 border-b border-zinc-800/80 bg-zinc-950/70 flex items-center justify-between">
                      <div className="min-w-0 pr-2">
                        <div className="flex items-center gap-2">
                          <span className="text-sm shrink-0">{option?.icon || "🤖"}</span>
                          <h3 className="text-sm font-bold text-zinc-100 truncate" title={modelId}>
                            {displayName}
                          </h3>
                          {isFastest && (
                            <span className="px-1.5 py-0.2 rounded bg-amber-950 text-amber-300 font-mono text-[9px] border border-amber-800 shrink-0 font-bold animate-pulse">
                              ⚡ FASTEST TTFT
                            </span>
                          )}
                        </div>
                        <p className="text-[10px] font-mono text-zinc-500 truncate mt-0.5">
                          {modelId}
                        </p>
                      </div>
                      <div className="shrink-0">{getStatusBadge(c.status)}</div>
                    </div>

                    {/* Metrics Ribbon */}
                    <div className="px-4 py-2 border-b border-zinc-800/50 bg-zinc-950/40 flex items-center justify-between text-xs font-mono">
                      <div>
                        <span className="text-zinc-500 text-[10px]">TTFT: </span>
                        <span className={c.ttftMs !== null ? "text-cyan-400 font-semibold" : "text-zinc-600"}>
                          {c.ttftMs !== null ? `${c.ttftMs}ms` : "—"}
                        </span>
                      </div>

                      <div>
                        <span className="text-zinc-500 text-[10px]">Total: </span>
                        <span className="text-zinc-300 font-medium">
                          {(c.elapsedMs / 1000).toFixed(2)}s
                        </span>
                      </div>

                      {tokPerSec && (
                        <div>
                          <span className="text-zinc-500 text-[10px]">Speed: </span>
                          <span className="text-emerald-400 font-medium">
                            {tokPerSec} t/s
                          </span>
                        </div>
                      )}

                      {c.usage && (
                        <div>
                          <span className="text-zinc-500 text-[10px]">Tokens: </span>
                          <span className="text-violet-400">
                            {c.usage.output_tokens}
                          </span>
                        </div>
                      )}
                    </div>

                    {/* Answer text / Streaming view */}
                    <div className="flex-1 p-4 flex flex-col justify-between overflow-y-auto max-h-[500px] min-h-[220px]">
                      <div>
                        {c.error && (
                          <div className="mb-3 p-3 rounded-xl bg-rose-950/60 border border-rose-800/80 text-rose-300 text-xs leading-relaxed shadow-sm">
                            <span className="font-semibold uppercase tracking-wider text-[10px] block mb-1 text-rose-200">
                              {c.status}
                            </span>
                            {c.error}
                          </div>
                        )}

                        {c.text ? (
                          <div className="text-sm text-zinc-200 whitespace-pre-wrap leading-relaxed font-sans select-text">
                            {c.text}
                            {c.status === "streaming" && (
                              <span className="cursor-blink" />
                            )}
                          </div>
                        ) : (
                          c.status === "streaming" && (
                            <div className="flex items-center gap-2 text-xs text-zinc-500 italic py-2">
                              <span className="h-2 w-2 rounded-full bg-emerald-400 animate-ping" />
                              <span>Generating first token...</span>
                            </div>
                          )
                        )}

                        {c.status === "queued" && !c.text && (
                          <div className="text-xs text-zinc-600 italic py-2">
                            Queued for execution permit...
                          </div>
                        )}
                      </div>

                      {c.finishReason && (
                        <div className="mt-4 pt-2 border-t border-zinc-800/60 text-[10px] text-zinc-500 font-mono flex items-center justify-between">
                          <span>finish: {c.finishReason}</span>
                          {c.usage && (
                            <span>prompt: {c.usage.input_tokens} tok</span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </section>
        )}
      </main>

      {/* Modern Footer */}
      <footer className="border-t border-zinc-800/70 py-4 px-6 text-center text-xs text-zinc-500 bg-zinc-950/80">
        VersusLab • Multiplexed SSE Stream • Fair RAG Context • Sub-second Live Telemetry
      </footer>
    </div>
  );
}
