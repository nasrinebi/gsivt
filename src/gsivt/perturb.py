"""Perturbed copies of a Model for sensitivity and benchmark analyses (no counterpart in the workbook)."""
from __future__ import annotations

import copy
from dataclasses import replace

from .model import Model

PONDS = ("Wet pond", "Dry detention pond", "Constructed wetland")


def perturbed(m: Model, capx: float = 1.0, omx: float = 1.0, emc: float = 1.0, rain: float = 1.0,
              capx_p: float | None = None, omx_p: float | None = None, emc_p: float | None = None,
              eff: dict | None = None) -> Model:
    """Return a Model whose unit costs, EMCs and rainfall are scaled.

    capx, omx: multipliers of capital and O&M unit costs (published and Florida values); with capx_p / omx_p the ponds and
    wetland get their own multiplier. emc scales every land-use EMC; with emc_p, rows of ponds and wetland use a separate
    multiplier (implemented by duplicating each land use with a suffix, see emc_land_use). eff: {bmp: {tn|tp|tss: value}}.
    The large rule tables are shared, not copied."""
    bm = copy.deepcopy(m.bmps)
    for name, b in bm.items():
        pond = name in PONDS
        cx = capx_p if (pond and capx_p is not None) else capx
        ox = omx_p if (pond and omx_p is not None) else omx
        b["capital"] *= cx; b["om"] *= ox
        if isinstance(b["flcap"], (int, float)):
            b["flcap"] *= cx; b["flom"] *= ox
        for k, v in (eff or {}).get(name, {}).items():
            b[k] = v
    lu = {k: tuple(c * emc for c in v) for k, v in m.landuse.items()}
    if emc_p is not None:
        lu.update({k + " [pond]": tuple(c * emc_p for c in v) for k, v in m.landuse.items()})
    st = {k: v * rain for k, v in m.stations.items()}
    return replace(m, bmps=bm, landuse=lu, stations=st)


def emc_land_use(rows: list[dict]) -> list[dict]:
    """Point pond and wetland rows to the separately scaled land uses created by perturbed(..., emc_p=...)."""
    out = []
    for r in rows:
        r = dict(r)
        if r["bmp"] in PONDS:
            r["lu"] = r["lu"] + " [pond]"
        out.append(r)
    return out
