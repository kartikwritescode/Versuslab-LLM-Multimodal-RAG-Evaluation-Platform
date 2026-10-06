import logging

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.service import (
    mark_model_finished,
    mark_model_started,
    mark_race_finished,
)
from app.evaluation.citation_check import verify_citations
from app.evaluation.cost import calculate_costs
from app.race.events import RaceEvent

logger = logging.getLogger(__name__)


class RacePersistenceTracker:
    """Tracks streaming events and asynchronously updates PostgreSQL without blocking SSE delivery."""

    def __init__(
        self,
        race_id: str,
        session_factory: async_sessionmaker[AsyncSession],
        valid_citation_ids: set[str] | None = None,
    ) -> None:
        self.race_id = race_id
        self.session_factory = session_factory
        self.valid_citation_ids = valid_citation_ids
        self.start_times_ns: dict[str, int] = {}
        self.first_token_times_ns: dict[str, int] = {}
        self.accumulated_text: dict[str, str] = {}
        self.chunk_counts: dict[str, int] = {}

    async def record_event(self, event: RaceEvent) -> None:
        """Processes a RaceEvent. Yielded to SSE client before calling this method."""
        try:
            if event.type == "model.started" and event.model_id:
                self.start_times_ns[event.model_id] = event.timestamp_ns
                self.accumulated_text[event.model_id] = ""
                self.chunk_counts[event.model_id] = 0
                async with self.session_factory() as session:
                    await mark_model_started(session, self.race_id, event.model_id)

            elif event.type == "model.delta" and event.model_id:
                # Accumulate text, count chunks, and record first token timestamp without touching DB
                if event.text:
                    self.accumulated_text[event.model_id] = (
                        self.accumulated_text.get(event.model_id, "") + event.text
                    )
                    self.chunk_counts[event.model_id] = (
                        self.chunk_counts.get(event.model_id, 0) + 1
                    )
                    if event.model_id not in self.first_token_times_ns:
                        self.first_token_times_ns[event.model_id] = event.timestamp_ns

            elif (
                event.type
                in (
                    "model.completed",
                    "model.error",
                    "model.timeout",
                    "model.cancelled",
                )
                and event.model_id
            ):
                mid = event.model_id
                start_ns = self.start_times_ns.get(mid)
                first_ns = self.first_token_times_ns.get(mid)

                ttft_ms: int | None = None
                if start_ns is not None and first_ns is not None and first_ns >= start_ns:
                    ttft_ms = (first_ns - start_ns) // 1_000_000

                latency_ms: int | None = None
                if start_ns is not None and event.timestamp_ns >= start_ns:
                    latency_ms = (event.timestamp_ns - start_ns) // 1_000_000

                status_map = {
                    "model.completed": "done",
                    "model.error": "error",
                    "model.timeout": "timeout",
                    "model.cancelled": "cancelled",
                }
                status = status_map[event.type]
                text = self.accumulated_text.get(mid, "")
                chunk_count = self.chunk_counts.get(mid, 0)
                in_tokens = event.usage.input_tokens if event.usage else None
                out_tokens = event.usage.output_tokens if event.usage else None

                citations_valid: bool | None = None
                invalid_citations: list[str] | None = None
                if self.valid_citation_ids is not None and event.type == "model.completed":
                    citations_valid, invalid_citations = verify_citations(
                        text, self.valid_citation_ids
                    )

                in_cost, out_cost, total_cost = calculate_costs(mid, in_tokens, out_tokens)

                async with self.session_factory() as session:
                    await mark_model_finished(
                        session=session,
                        race_id=self.race_id,
                        model_id=mid,
                        status=status,
                        ttft_ms=ttft_ms,
                        latency_ms=latency_ms,
                        input_tokens=in_tokens,
                        output_tokens=out_tokens,
                        finish_reason=event.finish_reason,
                        error_message=event.error,
                        response_text=text,
                        citations_valid=citations_valid,
                        invalid_citations=invalid_citations,
                        input_cost=in_cost,
                        output_cost=out_cost,
                        total_cost=total_cost,
                        chunk_count=chunk_count,
                    )

            elif event.type in ("race.completed", "race.cancelled"):
                status = "completed" if event.type == "race.completed" else "cancelled"
                async with self.session_factory() as session:
                    await mark_race_finished(session, self.race_id, status)

        except Exception as exc:  # noqa: BLE001
            # Rule 3: Errors are data — DB failures log cleanly and never disrupt the SSE stream
            logger.warning(
                "Failed to persist race event %s for race %s: %s",
                event.type,
                self.race_id,
                exc,
            )
