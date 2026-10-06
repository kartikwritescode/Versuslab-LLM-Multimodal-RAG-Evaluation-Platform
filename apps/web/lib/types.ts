// CRITICAL CONTRACT: Keep in exact sync with apps/api/app/race/events.py

export type EventType =
  | "race.started"
  | "model.started"
  | "model.delta"
  | "model.completed"
  | "model.error"
  | "model.timeout"
  | "model.cancelled"
  | "race.completed"
  | "race.cancelled";

export interface Usage {
  input_tokens: number;
  output_tokens: number;
}

export interface RaceEvent {
  type: EventType;
  race_id: string;
  sequence: number;
  timestamp_ns: number;
  model_id?: string | null;
  text?: string | null;
  finish_reason?: string | null;
  usage?: Usage | null;
  error?: string | null;
}

export interface RaceRequest {
  prompt: string;
  models: string[];
  temperature?: number;
  max_tokens?: number | null;
  document_id?: string | null;
}

export interface DocumentItem {
  id: string;
  filename: string;
  content_hash: string;
  mime_type: string;
  chunk_count: number;
  created_at: string | null;
  deduplicated?: boolean;
}

export interface DocumentChunkItem {
  id: string;
  chunk_index: number;
  text: string;
}

export interface DocumentDetail extends DocumentItem {
  chunks: DocumentChunkItem[];
}

export type ModelStatus =
  | "queued"
  | "streaming"
  | "done"
  | "error"
  | "timeout"
  | "cancelled";

export interface ContenderState {
  modelId: string;
  status: ModelStatus;
  text: string;
  ttftMs: number | null;
  elapsedMs: number;
  startTime: number | null;
  firstTokenTime: number | null;
  endTime: number | null;
  finishReason: string | null;
  usage: Usage | null;
  error: string | null;
}

export interface RaceListItem {
  id: string;
  prompt: string;
  temperature: number;
  max_tokens: number | null;
  status: string;
  model_count: number;
  created_at: string | null;
  finished_at: string | null;
}

export interface RaceListResponse {
  items: RaceListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface EvaluationDetail {
  id: string;
  metric: string;
  score: number;
  judge_model?: string | null;
  reason?: string | null;
  created_at?: string | null;
}

export interface ModelRunDetail {
  id: string;
  model_id: string;
  status: string;
  context_hash?: string | null;
  citations_valid?: boolean | null;
  invalid_citations?: string[] | null;
  ttft_ms: number | null;
  latency_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  input_cost?: number | null;
  output_cost?: number | null;
  total_cost?: number | null;
  finish_reason: string | null;
  error_message: string | null;
  response_text: string;
  evaluations?: EvaluationDetail[];

  // Performance metrics
  tokens_per_second?: number | null;
  time_per_output_token?: number | null;
  input_tokens_per_second?: number | null;

  // Cost efficiency metrics
  cost_per_1k_tokens?: number | null;
  cost_per_second?: number | null;

  // Response length statistics
  response_word_count?: number | null;
  response_char_count?: number | null;
  response_sentence_count?: number | null;

  // Quality & certainty metrics
  aggregate_quality_score?: number | null;
  confidence_score?: number | null;
  qualifier_count?: number | null;

  // Context utilization
  context_utilization_percent?: number | null;
  model_max_context?: number | null;

  // Streaming stability metrics
  streaming_chunk_count?: number | null;
  avg_chunk_size?: number | null;

  // Cost vs Quality tradeoff
  cost_quality_ratio?: number | null;
}

export interface RaceDetailResponse {
  id: string;
  prompt: string;
  temperature: number;
  max_tokens: number | null;
  status: string;
  shared_context_hash?: string | null;
  document_id?: string | null;
  created_at: string | null;
  finished_at: string | null;
  model_runs: ModelRunDetail[];
}

export interface BenchmarkCase {
  id: string;
  category: string;
  question: string;
  expected_answer?: string | null;
  gold_chunk_ids?: string[] | null;
}

export interface BenchmarkDataset {
  id: string;
  name: string;
  version: number;
  description?: string | null;
  case_count?: number;
  created_at?: string | null;
  cases?: BenchmarkCase[];
}

export interface ExperimentSummary {
  id: string;
  name: string;
  dataset_id: string;
  dataset_name: string;
  dataset_version: number;
  models: string[];
  model_count: number;
  status: string;
  git_commit?: string | null;
  include_llm_judge: boolean;
  created_at: string | null;
  finished_at?: string | null;
}

export interface ModelComparisonStats {
  model_id: string;
  runs_count: number;
  successful_runs: number;
  error_rate: number;
  timeout_rate: number;
  mean_ttft_ms?: number | null;
  mean_latency_ms?: number | null;
  mean_tokens_per_sec?: number | null;
  total_input_tokens: number;
  total_output_tokens: number;
  total_cost: number;
  mean_metrics: Record<string, number>;
}

export interface ParetoPoint {
  model_id: string;
  quality_score: number;
  total_cost: number;
  mean_latency_ms: number;
}

export interface CaseBreakdownItem {
  case_id: string;
  category: string;
  question: string;
  expected_answer?: string | null;
  race_id: string;
  models: Record<
    string,
    {
      status: string;
      response_text?: string;
      ttft_ms?: number | null;
      latency_ms?: number | null;
      evaluations?: Record<string, number>;
    }
  >;
}

export interface ExperimentResultsResponse {
  experiment_id: string;
  name: string;
  dataset_id: string;
  dataset_name: string;
  dataset_version: number;
  status: string;
  git_commit?: string | null;
  include_llm_judge: boolean;
  created_at?: string | null;
  finished_at?: string | null;
  total_cases: number;
  models_stats: ModelComparisonStats[];
  pareto_points: ParetoPoint[];
  cases: CaseBreakdownItem[];
}

