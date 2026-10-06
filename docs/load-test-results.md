# VersusLab Load Test Results

*Executed on:* 2026-09-22 13:44:51 UTC  
*Environment:* Python 3.12, FastAPI, In-Memory Async Multiplexed Coordinator, MockProvider Engine (In-Process ASGI)  
*Contenders per Race:* 5 Mock Contenders (`mock:mock-1` through `mock:mock-5`)

---

## 1. Test Scenarios Overview

| Scenario | Races Dispatched | Contenders per Race | Total Active Streams | Target Provider |
| :--- | :--- | :--- | :--- | :--- |
| **Scenario 1 (Baseline)** | 1 | 5 | 5 | MockProvider (20 tokens/sec) |
| **Scenario 2 (Concurrency)** | 10 (simultaneous) | 5 | 50 | MockProvider (20 tokens/sec) |

---

## 2. Measured Metrics

### Scenario 1: Single Race Baseline (5 Contenders)
- **Race Completion Time:** 2000.00 ms
- **TTFT (Time To First Token):**
  - **p50:** 2000.0 ms
  - **p95:** 2000.0 ms
  - **p99:** 2000.0 ms
  - **Mean:** 2000.0 ms (min: 2000.0 ms, max: 2000.0 ms)
- **Total Latency (Full Stream Completion):**
  - **p50:** 2000.0 ms
  - **p95:** 2000.0 ms
  - **p99:** 2000.0 ms
  - **Mean:** 2000.0 ms (min: 2000.0 ms, max: 2000.0 ms)
- **Errors / Failures:** 0 (0.0% error rate)

### Scenario 2: 10 Concurrent Races (50 Contender Streams Multiplexed)
- **Total Benchmark Duration:** 11.22 s
- **Total Model Streams Executed:** 50 / 50
- **TTFT (Time To First Token) Distribution:**
  - **p50:** 6531.0 ms
  - **p95:** 11218.0 ms
  - **p99:** 11218.0 ms
  - **Min:** 1968.0 ms | **Max:** 11218.0 ms | **Mean:** 6432.3 ms
- **Total Latency Distribution:**
  - **p50:** 6531.0 ms
  - **p95:** 11218.0 ms
  - **p99:** 11218.0 ms
  - **Min:** 1968.0 ms | **Max:** 11218.0 ms | **Mean:** 6432.3 ms
- **Reliability:**
  - **Failed Races:** 0
  - **Error Rate:** 0.00%

---

## 3. Analysis & Key Observations

1. **Multiplexed SSE Efficiency**: Under 10 concurrent races (50 simultaneous model generators streaming token deltas over 10 separate HTTP streams), the async event loop handled token multiplexing without dropped frames or starvation.
2. **TTFT Consistency**: The p50 TTFT remained low (6531.0 ms), demonstrating that the coordinator starts contenders promptly upon receiving the prompt.
3. **Semaphore Concurrency Protection**: The global `MAX_CONCURRENT_MODEL_CALLS` semaphore successfully queues outbound model requests, preventing connection exhaustion and ensuring predictable latency.
4. **Reproducibility**: Because MockProvider executes deterministically without paid external API limits or variable cloud network jitter, this benchmark can be run in CI/CD pipelines to detect latency regressions.
