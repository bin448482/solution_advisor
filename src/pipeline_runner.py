from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Protocol

from src.models import StageMetrics


class Stage(Protocol):
    """A pipeline stage unit."""

    name: str

    def run(self, ctx: "PipelineContext") -> "StageResult":
        ...


@dataclass
class StageResult:
    success_count: int = 0
    failure_count: int = 0
    notes: Optional[str] = None


@dataclass
class PipelineContext:
    pptx_path: Path
    output_dir: Path
    settings: Any
    force_capture: bool = False
    force_interpret: bool = False
    no_vectordb: bool = False
    verbose: bool = False
    manifest_data: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    stage_metrics: List[StageMetrics] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)

    def log(self, msg: str) -> None:
        if self.verbose:
            print(msg)


class PipelineRunner:
    """Executes ordered stages and records metrics."""

    def __init__(self, stages: Iterable[Stage]):
        self.stages = list(stages)

    def run(self, ctx: PipelineContext) -> None:
        for stage in self.stages:
            start_time = time.time()
            started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_time))
            try:
                result = stage.run(ctx)
            except Exception as exc:  # noqa: BLE001
                ctx.errors.append({"stage": stage.name, "error": str(exc)})
                result = StageResult(success_count=0, failure_count=1, notes="exception")
            end_time = time.time()
            ended_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(end_time))
            ctx.stage_metrics.append(
                StageMetrics(
                    name=stage.name,
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_seconds=round(end_time - start_time, 2),
                    success_count=result.success_count,
                    failure_count=result.failure_count,
                    notes=result.notes,
                )
            )
