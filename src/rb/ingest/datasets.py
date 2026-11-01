"""Descrizione di dataset tabellari (CSV, TSV, Parquet) e gerarchici (HDF5, NeXus)."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from rb.ingest.quantities import dimensionality_of, unit_from_label

MAX_STATS_ELEMENTS = 5_000_000


@dataclass
class Variable:
    name: str
    path: str
    dtype: str
    shape: list[int]
    unit: str | None = None
    dimensionality: str | None = None
    stats: dict = field(default_factory=dict)
    attrs: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _stats(arr: np.ndarray) -> dict:
    if arr.size == 0 or arr.size > MAX_STATS_ELEMENTS or not np.issubdtype(arr.dtype, np.number):
        return {}
    a = arr.astype(float, copy=False)
    finite = a[np.isfinite(a)]
    if finite.size == 0:
        return {"n_nan": int(a.size)}
    return {
        "min": float(finite.min()),
        "max": float(finite.max()),
        "mean": float(finite.mean()),
        "std": float(finite.std()),
        "n_nan": int(a.size - finite.size),
    }


def describe_table(path: str | Path) -> dict:
    p = Path(path)
    suffix = p.suffix.lower()
    if suffix == ".parquet":
        df = pd.read_parquet(p)
    else:
        df = pd.read_csv(p, sep="\t" if suffix == ".tsv" else None, engine="python")
    variables = []
    for col in df.columns:
        name, unit = unit_from_label(str(col))
        variables.append(Variable(
            name=name, path=str(col), dtype=str(df[col].dtype), shape=[len(df)],
            unit=unit, dimensionality=dimensionality_of(unit), stats=_stats(df[col].to_numpy()),
        ))
    return {"format": suffix.lstrip("."), "n_rows": len(df), "variables": [v.to_dict() for v in variables]}


def _clean_attr(value):
    if isinstance(value, bytes):
        return value.decode(errors="replace")
    if isinstance(value, np.ndarray):
        return value.tolist() if value.size <= 16 else f"array{list(value.shape)}"
    if isinstance(value, np.generic):
        return value.item()
    return value if isinstance(value, (str, int, float, bool)) else str(value)


def describe_hdf5(path: str | Path) -> dict:
    import h5py

    variables: list[Variable] = []
    groups: list[str] = []

    def visit(name, obj):
        if isinstance(obj, h5py.Group):
            groups.append(name)
            return
        if not isinstance(obj, h5py.Dataset):
            return
        attrs = {k: _clean_attr(v) for k, v in obj.attrs.items()}
        unit = attrs.get("units") or attrs.get("unit")
        unit = str(unit) if unit is not None else None
        data = obj[()] if obj.size <= MAX_STATS_ELEMENTS else np.empty(0)
        variables.append(Variable(
            name=name.split("/")[-1], path="/" + name, dtype=str(obj.dtype), shape=list(obj.shape),
            unit=unit, dimensionality=dimensionality_of(unit),
            stats=_stats(np.asarray(data)) if obj.dtype.kind in "iuf" else {}, attrs=attrs,
        ))

    with h5py.File(path, "r") as f:
        root_attrs = {k: _clean_attr(v) for k, v in f.attrs.items()}
        f.visititems(visit)
    return {"format": "hdf5", "root_attrs": root_attrs, "groups": groups, "variables": [v.to_dict() for v in variables]}
