"""Pluggable registry of data sources (each one is an MCP server)."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path

from .mcp_client import MCPServerSpec

logger = logging.getLogger(__name__)

_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class UnknownDataSource(KeyError):
    pass


class ConfigError(ValueError):
    pass


def _expand(value: str, variables: Mapping[str, str]) -> str:
    """Substitute ``${NAME}`` from ``variables`` then the process environment."""

    def repl(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in variables:
            return variables[name]
        if name in os.environ:
            return os.environ[name]
        raise ConfigError(f"datasource config references undefined variable ${{{name}}}")

    return _VAR.sub(repl, value)


class DataSourceRegistry:
    def __init__(self, specs: Iterable[MCPServerSpec] = ()) -> None:
        self._specs: dict[str, MCPServerSpec] = {}
        for spec in specs:
            self.register(spec)

    def register(self, spec: MCPServerSpec) -> None:
        self._specs[spec.id] = spec

    def get(self, datasource_id: str) -> MCPServerSpec:
        try:
            return self._specs[datasource_id]
        except KeyError:
            raise UnknownDataSource(datasource_id) from None

    def has(self, datasource_id: str) -> bool:
        return datasource_id in self._specs

    def list(self) -> list[MCPServerSpec]:
        return list(self._specs.values())

    @classmethod
    def from_file(
        cls, path: Path, variables: Mapping[str, str] | None = None
    ) -> DataSourceRegistry:
        """Load specs from a JSON file: ``{"datasources": [{...MCPServerSpec...}]}``.

        ``${VAR}`` placeholders are expanded so secrets (e.g. a DSN) come from the
        environment and never live in the file. ``"command": "python"`` resolves to the
        interpreter running the backend, so servers share its virtualenv.
        """
        if not path.exists():
            logger.warning("datasources file %s not found; starting with no data sources", path)
            return cls()
        raw = json.loads(path.read_text())
        variables = variables or {}
        specs = []
        for item in raw.get("datasources", []):
            spec = MCPServerSpec.model_validate(item)
            spec.command = (
                sys.executable if spec.command == "python" else _expand(spec.command, variables)
            )
            spec.args = [_expand(a, variables) for a in spec.args]
            spec.env = {k: _expand(v, variables) for k, v in spec.env.items()}
            specs.append(spec)
        return cls(specs)
