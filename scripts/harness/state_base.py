from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Generic, TypeVar

from scripts.harness import (
    HarnessError,
    atomic_write_json_unlocked,
    load_json,
    locked_state_file,
    now_iso,
)

T = TypeVar("T", bound=dict)

class StateDoc(Generic[T]):
    def __init__(
        self,
        path_func: Callable[[Path], Path],
        validator: Callable[[T], list[str]],
        default_func: Callable[[str], T] | None = None,
    ):
        self.path_func = path_func
        self.validator = validator
        self.default_func = default_func

    def load(self, root: Path) -> T:
        path = self.path_func(root)
        fallback = self.default_func(root.name) if self.default_func else None
        data = load_json(path, fallback=fallback)
        if not isinstance(data, dict):
            raise HarnessError(f"{path} must contain a JSON object.")
        self.validator(data)
        return data

    def mutate(self, root: Path, mutator: Callable[[T], None]) -> T:
        path = self.path_func(root)
        with locked_state_file(path):
            data = self.load(root)
            mutator(data)
            if "last_updated" in data or hasattr(data, "last_updated"):
                data["last_updated"] = now_iso()
            self.validator(data)
            atomic_write_json_unlocked(path, data)
            return data
