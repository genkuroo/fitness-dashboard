"""Common interface every data source implements.

The three sources reach their data very differently (official API, manual CSV
export, unofficial private API), but the pipeline shouldn't care. Each one is a
Connector that knows how to `sync()` its own data into the shared tables. The
pipeline just loops over the enabled connectors and calls sync() on each,
isolating failures so one broken source never takes down the rest.
"""

from abc import ABC, abstractmethod


class Connector(ABC):
    #: short identifier, must match the key in config.json
    name: str = ""

    def __init__(self, config: dict):
        # The per-source block from config.json, e.g. {"enabled": true, ...}
        self.config = config or {}

    @property
    def enabled(self) -> bool:
        return bool(self.config.get("enabled", False))

    @abstractmethod
    def sync(self, conn) -> int:
        """Fetch/import this source's data, normalize it, write it to the
        shared SQLite tables via `conn`, and return the number of rows added
        or updated. Must be idempotent — safe to run repeatedly.
        """
        raise NotImplementedError
