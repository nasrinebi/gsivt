"""Calculation engine of the GSI Monetary Valuation Tool, v3.3.

A line-by-line re-implementation of the Calculator, totals and Scenarios formulas of the workbook. Function and
variable names follow the workbook column keys (rv, rd, rg, cap, ...), so each quantity can be traced to its
spreadsheet column. Equation numbers refer to the accompanying paper.
"""
from __future__ import annotations

import math
from typing import Any

from .model import (BAM, FIX, FL_COSTS, FL_SOURCE, IMP_BASIS, INF, LEVELS, RET, SIMPLE, WD, WQ_BASES, Model)

LEVEL_KEY = dict(zip(LEVELS, ("cons", "typ", "high")))
SENS_RATES = (0.015, 0.02, 0.03, 0.05, 0.07)
OM_MULTS = (0.25, 1.0, 4.0)


# ---------------------------------------------------------------------- coefficients
def coefficients(m: Model, s: dict, level: str | None = None, source: str | None = None) -> dict:
    """Values of every Coefficients-sheet parameter in base-year dollars for one valuation level (column E)."""
    level = level or s["Level"]
    source = source or s["ValueSource"]
    lk = LEVEL_KEY[level]
    out = {}
    for nm, c in m.coef.items():
        if nm in ("Val_TN", "Val_TP"):
            continue
        out[nm] = c[lk] * m.cpi_factor(s["BaseYear"], c["y" + lk])
    fl = source == FL_SOURCE
    out["Val_TN"] = out["Val_TN_FL"] if fl else out["Val_TN_Pub"]
    out["Val_TP"] = out["Val_TP_FL"] if fl else out["Val_TP_Pub"]
    return out


def annuity(rate: float, period: float) -> float:
    return period if rate <= 0 else (1 - (1 + rate) ** -period) / rate


def growth_annuity(rate: float, growth: float, period: float) -> float:
    if abs(rate - growth) < 1e-6:
        return period / (1 + rate)
    return (1 - ((1 + growth) / (1 + rate)) ** period) / (rate - growth)


# ---------------------------------------------------------------------- rule tables
def _cn_split(cn: float) -> tuple[int, float]:
    lo = max(30, min(90, int(math.floor(cn / 5)) * 5))
    return lo, min(1.0, max(0.0, (cn - lo) / 5))


def runoff_coefficient(m: Model, zone: int, cn: float, dcia: float) -> float:
    """AH Vol. I Appendix N, bilinear in CN and DCIA (Eq. 1)."""
    lo, wc = _cn_split(cn)
    dlo = max(0, min(95, int(math.floor(dcia / 5)) * 5)); wd = min(1.0, max(0.0, (dcia - dlo) / 5))
    t0, t1 = m.roc[(zone, lo)], m.roc[(zone, lo + 5)]
    return (1 - wc) * ((1 - wd) * t0[dlo] + wd * t0[dlo + 5]) + wc * ((1 - wd) * t1[dlo] + wd * t1[dlo + 5])


def retention_share(m: Model, zone: int, depth: float, cn: float, dcia: float) -> float:
    """AH Vol. I Appendix O retention efficiency as a fraction of annual load (bilinear in CN and DCIA)."""
    lo, wc = _cn_split(cn)
    d = f"{depth:.2f}"
    dlo = max(5, min(95, int(math.floor(dcia / 5)) * 5)); wd = min(1.0, max(0.0, (dcia - dlo) / 5))
    hi = min(100, dlo + 5)
    t0, t1 = m.ret[(zone, d, lo)], m.ret[(zone, d, lo + 5)]
    return ((1 - wc) * ((1 - wd) * t0[dlo] + wd * t0[hi]) + wc * ((1 - wd) * t1[dlo] + wd * t1[hi])) / 100


def wet_detention(cf: dict, t: float) -> tuple[float, float]:
    """AH Vol. I Appendix O wet detention equations (Eq. 4); t already limited to 1..WD_Tmax."""
    tn = cf["WD_TNa"] * t / (cf["WD_TNb"] + t) / 100
    tp = (cf["WD_TPa"] + cf["WD_TPb"] * math.log(t) + cf["WD_TPc"] * math.log(t) ** 2) / 100
    return tn, tp


# ---------------------------------------------------------------------- one Calculator row
def _wq(basis: str, tnr: float, tpr: float, tssr: float, vtn: float, vtp: float, vtss: float) -> float:
    i = WQ_BASES.index(basis)
    if i == 0:
        return max(tnr * vtn, tpr * vtp, tssr * vtss)
    if i == 1:
        return tnr * vtn + tpr * vtp + tssr * vtss
    return tnr * vtn if i == 2 else tpr * vtp


def compute_row(m: Model, s: dict, row: dict, cf: dict, ctx: dict, idx: int = 0, n_inc_before: int = 0) -> dict:
    inc = row["inc"] == "Yes"
    b = m.bmps[row["bmp"]]
    o: dict[str, Any] = {}
    meth = b["method"] if inc else ""
    o["meth"] = meth
    cn = m.soils[row["soil"]] if inc else 0
    o["cn"] = cn
    imp, area, fp = row["imp"], row["area"], row["fp"]
    tday = min(cf["WD_Tmax"], max(1, row["rtime"] or 0)) if inc else 1   # blank cells count as 0, as in the workbook
    o["tday"] = tday
    simple = s["RunoffMethod"] == SIMPLE
    zone = ctx["zone"]
    if inc:
        o["rv"] = 0.05 + 0.009 * imp if simple else runoff_coefficient(m, zone, cn, imp)
        o["rd"] = ctx["rain"] * (cf["Pj"] if simple else 1) * o["rv"]
        o["rg"] = o["rd"] / 12 * area * cf["GalPerAcFt"]
    else:
        o["rv"] = o["rd"] = o["rg"] = 0.0
    o["reff"] = retention_share(m, zone, row["rdep"], cn, imp) if (inc and meth == RET) else 0.0
    o["cap"] = (o["reff"] if meth == RET else 1.0) if inc else 0.0
    o["infd"] = 1 if (inc and meth == RET and (b["always"] == 1 or row["design"] == INF)) else 0
    o["vt"] = o["rg"] * o["cap"]
    o["vr"] = o["vt"] if o["infd"] == 1 else 0.0
    if inc:
        tn_eq, tp_eq = wet_detention(cf, tday)
        if o["infd"] == 1:
            e = (1.0, 1.0, 1.0)
        else:
            etn = tn_eq if meth == WD else (cf["BAM_TN"] if (row["design"] == BAM and b["bam"] == 1) else b["tn"])
            etp = tp_eq if meth == WD else b["tp"]
            e = (etn, etp, b["tss"])
        o["etn"], o["etp"], o["etss"] = (o["cap"] * x for x in e)
        emc = m.landuse[row["lu"]]
        for k, c in zip(("tn", "tp", "tss"), emc):
            o[k + "l"] = cf["LoadK"] * o["rd"] * c * area
    else:
        o["etn"] = o["etp"] = o["etss"] = 0.0
        o["tnl"] = o["tpl"] = o["tssl"] = 0.0
    for k in ("tn", "tp", "tss"):
        o[k + "r"] = o[k + "l"] * o["e" + k]
    o["sw"] = o["vr"] * cf["StormPerGal"] if s["IncludeRunoff"] == "Yes" else 0.0
    o["tnv"], o["tpv"], o["tssv"] = o["tnr"] * cf["Val_TN"], o["tpr"] * cf["Val_TP"], o["tssr"] * cf["Val_TSS"]
    o["wqmax"] = max(o["tnv"], o["tpv"], o["tssv"])
    basis = s["WQBasis"]
    o["wq"] = _wq(basis, o["tnr"], o["tpr"], o["tssr"], cf["Val_TN"], cf["Val_TP"], cf["Val_TSS"])
    alt = ctx["cf_alt"]
    o["wqalt"] = _wq(basis, o["tnr"], o["tpr"], o["tssr"], alt["Val_TN"], alt["Val_TP"], cf["Val_TSS"])
    for kk, lv in zip(("wqc", "wqt", "wqh"), LEVELS):
        c2 = ctx["cf_level"][lv]
        o[kk] = _wq(basis, o["tnr"], o["tpr"], o["tssr"], c2["Val_TN"], c2["Val_TP"], c2["Val_TSS"])
    o["vega"] = fp * b["veg"] if inc else 0.0
    o["trees"] = (fp / cf["TreeBoxArea"] if b["tree"] == 1 else 0.0) if inc else 0.0
    o["herb"] = 0.0 if b["tree"] == 1 else o["vega"]
    o["gra"] = fp * b["energy"] if inc else 0.0
    o["co2"] = o["vega"] * cf["CO2Herb"] / 2204.62
    o["carb"] = o["co2"] * cf["CarbonPerTon"]
    o["air"] = o["herb"] * cf["AirHerb"] + o["trees"] * cf["TreeAir"]
    o["en"] = o["gra"] * cf["EnergyGR"]
    o["vis"] = fp / 43560 * cf["VisitRate"] if (inc and row["access"] == "Yes") else 0.0
    o["rec"] = o["vis"] * cf["ValVisit"] * (1 if s["IncludeRec"] == "Yes" else 0)
    o["ben"] = o["sw"] + o["wq"] + o["carb"] + o["air"] + o["en"] + o["rec"]
    # costs
    o["basis"] = b["basis"] if inc else ""
    o["qty"] = (area * imp / 100 if b["basis"] == IMP_BASIS else fp) if inc else 0.0
    if inc:
        o["sf"] = min(1.5, max(0.5, (1000 / fp) ** cf["ScaleExp"])) if (s["EOS"] == "On" and b["basis"] != IMP_BASIS and fp > 0) else 1.0
    else:
        o["sf"] = 0.0
    flon = s["CostBasis"] == FL_COSTS and isinstance(b["flcap"], (int, float))
    flf = m.cpi_factor(s["BaseYear"], 2024)
    capfac = m.cpi_factor(s["BaseYear"], b["capyr"]); omfac = m.cpi_factor(s["BaseYear"], b["omyr"])
    if inc:
        o["cons"] = (b["flcap"] * flf if flon else b["capital"] * capfac) * o["qty"] * o["sf"] * s["CostIndex"]
        o["upf"] = 0.0 if row["status"] == "Existing" else o["cons"] + s["LandPerAcre"] * fp / 43560 + o["cons"] * s["PermitPct"]
        o["om"] = (b["flom"] * flf if flon else b["om"] * omfac) * o["qty"] * s["CostIndex"]
        o["life"] = b["life"]
        o["t1"] = o["life"] - math.fmod(row["age"] or 0, o["life"]) if row["status"] == "Existing" else o["life"]
    else:
        o["cons"] = o["upf"] = o["om"] = 0.0
        o["life"] = o["t1"] = 0
    r_, P = s["DiscRate"], s["Period"]
    o["rep"] = o["cons"] * sum((1 + r_) ** -(o["t1"] + k * o["life"]) for k in range(5) if o["t1"] + k * o["life"] < P) if inc else 0.0
    A, GA = ctx["annuity"], ctx["growth_annuity"]
    o["cnpv"] = o["upf"] + o["om"] * A + o["rep"] if inc else 0.0
    o["bnpv"] = (o["ben"] - o["rec"]) * A + o["rec"] * GA if inc else 0.0
    o["net"] = o["bnpv"] - o["cnpv"]
    o["bcr"] = o["bnpv"] / o["cnpv"] if o["cnpv"] > 0 else 0.0
    o["ann"] = o["cnpv"] / A if inc else 0.0
    for k, num, den in (("ctn", "ann", "tnr"), ("ctp", "ann", "tpr"), ("captn", "cons", "tnr")):
        o[k] = (o[num] / o[den] if o[den] > 0 else "n/a") if inc else ""
    o["hab"] = fp / 43560 * b["habitat"] if inc else 0.0
    o["wqv"] = s["DesignDepth"] / 12 * o["rv"] * area * cf["GalPerAcFt"] if inc else 0.0
    o["grey"] = o["wqv"] * cf["GreyPerGal"] * s["CostIndex"]
    o["ina"] = 1 if inc and row["strat"] in ("A", "A + B") else 0
    o["inb"] = 1 if inc and row["strat"] in ("B", "A + B") else 0
    o["idx"] = n_inc_before + 1 if inc else 0
    o["check"] = row_check(row, b, o, cf)
    return o


def row_check(row: dict, b: dict, o: dict, cf: dict) -> str:
    if row["inc"] != "Yes":
        return "Not included"
    if o["infd"] == 1 and row["soil"].startswith("HSG D"):
        return "HSG D: confirm 72-hour recovery or choose Filtering"
    if row["status"] == "Existing" and (row["age"] or 0) <= 0:
        return "Existing asset: enter its age"
    if row["fp"] > row["area"] * 43560:
        return "Check: footprint larger than drainage area"
    if o["meth"] == WD and (row["rtime"] or 0) > cf["WD_Tmax"]:
        return "Residence time capped at 200 days"
    if row["design"] == BAM and o["meth"] == RET and b["bam"] == 0 and b["always"] == 0:
        return "BAM option applies to bioretention, tree box and swale; conventional filtering used"
    return "OK"


# ---------------------------------------------------------------------- portfolio, totals and scenarios
SUM_KEYS = ("rg", "vt", "vr", "tnl", "tnr", "tpl", "tpr", "tssl", "tssr", "sw", "wq", "co2", "carb", "air", "en", "vis", "rec",
            "ben", "cons", "upf", "om", "rep", "cnpv", "bnpv", "net", "ann", "hab", "wqv", "grey", "vega", "trees", "herb", "gra",
            "tnv", "tpv", "tssv", "wqmax", "wqc", "wqt", "wqh", "wqalt")


def evaluate(m: Model, s: dict, rows: list[dict], scenarios: bool = True, coef_override: dict | None = None) -> dict:
    """Compute every Calculator row, the totals row and (optionally) the six Scenarios tables.

    coef_override replaces selected base-year coefficient values (for example Val_TN) after the level and source
    selection; it is used by the sensitivity analyses and has no counterpart in the workbook."""
    cf = coefficients(m, s)
    if coef_override:
        cf.update(coef_override)
    other = [v for v in (FL_SOURCE, "Published studies (v3.2)") if v != s["ValueSource"]][0]
    ctx = dict(zone=m.counties[s["County"]], rain=m.stations[s["Station"]], cf_alt=coefficients(m, s, source=other),
               cf_level={lv: coefficients(m, s, level=lv) for lv in LEVELS},
               annuity=annuity(s["DiscRate"], s["Period"]),
               growth_annuity=growth_annuity(s["DiscRate"], s["VisitGrowth"], s["Period"]))
    out_rows, n_inc = [], 0
    for i, r in enumerate(rows):
        o = compute_row(m, s, r, cf, ctx, i, n_inc)
        n_inc += r["inc"] == "Yes"
        out_rows.append(o)
    tot = {k: sum(o[k] for o in out_rows) for k in SUM_KEYS}
    tot["area"] = sum(r["area"] for r in rows if r["inc"] == "Yes")
    tot["fp"] = sum(r["fp"] for r in rows if r["inc"] == "Yes")
    tot["bcr"] = tot["bnpv"] / tot["cnpv"] if tot["cnpv"] > 0 else 0.0
    tot["ctn"] = tot["ann"] / tot["tnr"] if tot["tnr"] > 0 else "n/a"
    tot["ctp"] = tot["ann"] / tot["tpr"] if tot["tpr"] > 0 else "n/a"
    tot["captn"] = tot["cons"] / tot["tnr"] if tot["tnr"] > 0 else "n/a"
    res = dict(rows=out_rows, total=tot, annuity=ctx["annuity"], growth_annuity=ctx["growth_annuity"], zone=ctx["zone"],
               rainfall=ctx["rain"], coefficients=cf)
    if scenarios:
        res["scenarios"] = _scenarios(s, rows, out_rows, tot, ctx)   # rates as in Scenarios!A22:A26
    return res


def _scenarios(s, rows, out_rows, tot, ctx, rates=SENS_RATES) -> dict:
    A, GA, P = ctx["annuity"], ctx["growth_annuity"], s["Period"]
    sc = {}
    # 1. valuation levels
    lv = {}
    for lev, wqk in zip(LEVELS, ("wqc", "wqt", "wqh")):
        c = ctx["cf_level"][lev]
        parts = [tot["sw"], tot[wqk], tot["co2"] * c["CarbonPerTon"], tot["herb"] * c["AirHerb"] + tot["trees"] * c["TreeAir"],
                 tot["gra"] * c["EnergyGR"], tot["vis"] * c["ValVisit"] * (1 if s["IncludeRec"] == "Yes" else 0)]
        bn = sum(parts[:5]) * A + parts[5] * GA
        lv[lev] = dict(parts=parts, ben=sum(parts), bnpv=bn, cnpv=tot["cnpv"], net=bn - tot["cnpv"],
                       bcr=bn / tot["cnpv"] if tot["cnpv"] > 0 else 0.0, jobs=tot["upf"] / 1e6 * c["JobsPerM"])
    sc["levels"] = lv
    # 2. discount rates
    dr = {}
    for r_ in rates:
        a = (1 - (1 + r_) ** -P) / r_
        ga = growth_annuity(r_, s["VisitGrowth"], P)
        bn = (tot["ben"] - tot["rec"]) * a + tot["rec"] * ga
        rep = sum(o["cons"] * sum(((o["t1"] + k * o["life"]) < P) / (1 + r_) ** (o["t1"] + k * o["life"]) for k in range(5)) for o in out_rows)
        cn = tot["upf"] + tot["om"] * a + rep
        dr[r_] = dict(bnpv=bn, cnpv=cn, net=bn - cn, bcr=bn / cn if cn > 0 else 0.0)
    sc["discount"] = dr
    # 3. strategies
    st = {}
    for lab, h in (("A", "ina"), ("B", "inb"), ("All", None)):
        w = [o[h] if h else (1 if r["inc"] == "Yes" else 0) for o, r in zip(out_rows, rows)]
        g = lambda k: sum(wi * (r[k] if k == "area" else o[k]) for wi, o, r in zip(w, out_rows, rows))
        d = dict(n=sum(w), area=g("area"), tnr=g("tnr"), tpr=g("tpr"), vr=g("vr"), upf=g("upf"), cnpv=g("cnpv"), bnpv=g("bnpv"))
        d["net"] = d["bnpv"] - d["cnpv"]
        d["bcr"] = d["bnpv"] / d["cnpv"] if d["cnpv"] > 0 else 0.0
        d["ctn"] = d["cnpv"] / A / d["tnr"] if d["tnr"] > 0 else "n/a"
        st[lab] = d
    sc["strategies"] = st
    # 4. water-quality basis
    wqb = {}
    for basis, v in zip(("Largest single pollutant", "Sum of TN, TP and TSS", "TN only", "TP only"),
                        (tot["wqmax"], tot["tnv"] + tot["tpv"] + tot["tssv"], tot["tnv"], tot["tpv"])):
        bn = tot["bnpv"] - tot["wq"] * A + v * A
        wqb[basis] = dict(wq=v, bnpv=bn, cnpv=tot["cnpv"], bcr=bn / tot["cnpv"] if tot["cnpv"] > 0 else 0.0)
    sc["wq_basis"] = wqb
    # 5. O&M multipliers
    sc["om"] = {mult: dict(om=tot["om"] * mult, bnpv=tot["bnpv"], cnpv=tot["cnpv"] + (mult - 1) * tot["om"] * A,
                           bcr=tot["bnpv"] / (tot["cnpv"] + (mult - 1) * tot["om"] * A) if tot["cnpv"] + (mult - 1) * tot["om"] * A > 0 else 0.0)
                for mult in OM_MULTS}
    # 6. dollar-value source
    bn_alt = tot["bnpv"] - tot["wq"] * A + tot["wqalt"] * A
    sc["value_source"] = dict(selected=dict(wq=tot["wq"], bnpv=tot["bnpv"], bcr=tot["bcr"]),
                              other=dict(wq=tot["wqalt"], bnpv=bn_alt, bcr=bn_alt / tot["cnpv"] if tot["cnpv"] > 0 else 0.0))
    return sc
