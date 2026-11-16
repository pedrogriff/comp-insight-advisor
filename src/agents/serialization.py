"""Exact JSON round trip for squad state.

encode() turns dataclasses, tuples, sets, dates and dicts with non-string keys
into tagged JSON-plain values. decode() restores them. A checkpoint written to
SQLite, or carried through a LangGraph channel, therefore comes back equal to
the state that was saved, with tuples still tuples and dataclasses still typed.

Only dataclasses defined under the ``src`` package are rebuilt, so a tampered
checkpoint cannot make decode() import and call code from anywhere else.
"""

from __future__ import annotations

import dataclasses
from datetime import date, datetime
import importlib
import json
from pathlib import Path, PurePath
from typing import Any

TAG = "__kind__"
ALLOWED_MODULE_PREFIX = "src."


class StateEncodingError(TypeError):
    """Raised when a value has no exact JSON form or a checkpoint names a foreign type."""


def encode(obj: Any) -> Any:
    """Returns a JSON-plain copy of obj that decode() turns back into an equal value."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        cls = type(obj)
        return {
            TAG: "dataclass",
            "type": f"{cls.__module__}:{cls.__qualname__}",
            "fields": {f.name: encode(getattr(obj, f.name)) for f in dataclasses.fields(obj)},
        }
    if isinstance(obj, list):
        return [encode(item) for item in obj]
    if isinstance(obj, tuple):
        return {TAG: "tuple", "items": [encode(item) for item in obj]}
    if isinstance(obj, (set, frozenset)):
        items = sorted((encode(item) for item in obj), key=lambda v: json.dumps(v, sort_keys=True))
        return {TAG: "frozenset" if isinstance(obj, frozenset) else "set", "items": items}
    if isinstance(obj, dict):
        if all(isinstance(key, str) for key in obj) and TAG not in obj:
            return {key: encode(value) for key, value in obj.items()}
        return {TAG: "dict", "items": [[encode(key), encode(value)] for key, value in obj.items()]}
    if isinstance(obj, datetime):
        return {TAG: "datetime", "value": obj.isoformat()}
    if isinstance(obj, date):
        return {TAG: "date", "value": obj.isoformat()}
    if isinstance(obj, PurePath):
        return {TAG: "path", "value": str(obj)}
    raise StateEncodingError(f"No exact JSON form for {type(obj).__module__}.{type(obj).__qualname__}")


def _resolve_dataclass(type_name: str) -> type:
    module_name, _, qualname = type_name.partition(":")
    if not module_name.startswith(ALLOWED_MODULE_PREFIX):
        raise StateEncodingError(f"Refusing to rebuild {type_name!r}: only {ALLOWED_MODULE_PREFIX}* types are allowed")
    target: Any = importlib.import_module(module_name)
    for part in qualname.split("."):
        target = getattr(target, part)
    if not (isinstance(target, type) and dataclasses.is_dataclass(target)):
        raise StateEncodingError(f"{type_name!r} is not a dataclass")
    return target


def decode(obj: Any) -> Any:
    """Inverse of encode()."""
    if isinstance(obj, list):
        return [decode(item) for item in obj]
    if not isinstance(obj, dict):
        return obj
    kind = obj.get(TAG)
    if kind is None:
        return {key: decode(value) for key, value in obj.items()}
    if kind == "dataclass":
        cls = _resolve_dataclass(obj["type"])
        return cls(**{name: decode(value) for name, value in obj["fields"].items()})
    if kind == "tuple":
        return tuple(decode(item) for item in obj["items"])
    if kind == "set":
        return {decode(item) for item in obj["items"]}
    if kind == "frozenset":
        return frozenset(decode(item) for item in obj["items"])
    if kind == "dict":
        return {decode(key): decode(value) for key, value in obj["items"]}
    if kind == "datetime":
        return datetime.fromisoformat(obj["value"])
    if kind == "date":
        return date.fromisoformat(obj["value"])
    if kind == "path":
        return Path(obj["value"])
    raise StateEncodingError(f"Unknown tag {kind!r} in checkpoint")


def dumps(obj: Any) -> str:
    """encode() as compact JSON text. Dict keys keep their insertion order."""
    return json.dumps(encode(obj), separators=(",", ":"))


def loads(text: str) -> Any:
    """Inverse of dumps()."""
    return decode(json.loads(text))
