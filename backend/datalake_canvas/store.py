"""Workflow persistence: one JSON file per workflow in a directory (a Docker volume)."""

from __future__ import annotations

import logging
import os
import re
import threading
import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from .models import Workflow, WorkflowIn, WorkflowSummary

logger = logging.getLogger(__name__)

_ID = re.compile(r"^[0-9a-f]{32}$")  # also guarantees ids can never escape the directory


class WorkflowNotFound(KeyError):
    pass


class WorkflowStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _path(self, workflow_id: str) -> Path:
        if not _ID.match(workflow_id):
            raise WorkflowNotFound(workflow_id)
        return self.directory / f"{workflow_id}.json"

    def _write(self, workflow: Workflow) -> None:
        path = self._path(workflow.id)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(workflow.model_dump_json(indent=2))
        os.replace(tmp, path)  # atomic: readers never see a half-written file

    def create(self, data: WorkflowIn) -> Workflow:
        now = datetime.now(UTC)
        workflow = Workflow(
            id=uuid.uuid4().hex, created_at=now, updated_at=now, **data.model_dump()
        )
        with self._lock:
            self._write(workflow)
        return workflow

    def get(self, workflow_id: str) -> Workflow:
        path = self._path(workflow_id)
        try:
            return Workflow.model_validate_json(path.read_text())
        except FileNotFoundError:
            raise WorkflowNotFound(workflow_id) from None

    def update(self, workflow_id: str, data: WorkflowIn) -> Workflow:
        with self._lock:
            existing = self.get(workflow_id)
            workflow = Workflow(
                id=workflow_id,
                created_at=existing.created_at,
                updated_at=datetime.now(UTC),
                **data.model_dump(),
            )
            self._write(workflow)
        return workflow

    def delete(self, workflow_id: str) -> None:
        with self._lock:
            try:
                self._path(workflow_id).unlink()
            except FileNotFoundError:
                raise WorkflowNotFound(workflow_id) from None

    def list(self) -> list[WorkflowSummary]:
        summaries = []
        for path in self.directory.glob("*.json"):
            try:
                wf = Workflow.model_validate_json(path.read_text())
            except (ValidationError, OSError):
                logger.warning("skipping unreadable workflow file %s", path)
                continue
            summaries.append(
                WorkflowSummary(
                    id=wf.id, name=wf.name, node_count=len(wf.nodes), updated_at=wf.updated_at
                )
            )
        return sorted(summaries, key=lambda s: s.updated_at, reverse=True)
