"""Randomized differential testing of the workbook against the gsivt engine.

For each case a random but valid set of Calculator inputs (18 settings and 12 practice rows) is written into a copy of
the workbook, the copy is recalculated in LibreOffice Calc, and every Calculator, totals and Scenarios value is compared
with the engine. Cases 0 to 7 force edge conditions; the remaining cases sample all dropdown options uniformly.

usage: python scripts/differential_test.py WORKBOOK N_CASES OUTDIR [SEED]
"""
import json
import math
import random
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import gsivt as g  # noqa: E402

# Recalculation command. The workbook copy must be recalculated and saved by a spreadsheet application before its cached
# values can be read. Set GSIVT_RECALC to a command that takes the file path as its last argument, recalculates all
# formulas (for example a LibreOffice headless macro that calls calculateAll() and stores the file) and prints a JSON
# status object with "status" and "total_errors". The tests in this repository do not need it.
import os, shlex
RECALC = shlex.split(os.environ.get("GSIVT_RECALC", "python3 recalc.py"))
RECALC_CWD = os.environ.get("GSIVT_RECALC_CWD") or None


def random_case(m: g.Model, rng: random.Random, k: int) -> tuple[dict, list]:
    L = m.lists
    s = dict(ProjectName=f"Differential test case {k}",
             Station=rng.choice(list(m.stations)), County=rng.choice(list(m.counties)),
             RunoffMethod=rng.choice(L["MethodList"]), Level=rng.choice(L["LevelList"]), WQBasis=rng.choice(L["WQBasisList"]),
             ValueSource=rng.choice(L["ValueSourceList"]), IncludeRunoff=rng.choice(L["YesNo"]),
             BaseYear=rng.choice(L["BaseYearList"]), Period=rng.choice(L["PeriodList"]), DiscRate=rng.choice(L["RateList"]),
             VisitGrowth=rng.choice(L["GrowthList"]), IncludeRec=rng.choice(L["YesNo"]), DesignDepth=rng.choice(L["DepthList"]),
             PermitPct=rng.choice(L["PermitList"]), LandPerAcre=0 if rng.random() < 0.5 else round(rng.uniform(0, 5e5), 2),
             EOS=rng.choice(L["OnOff"]), CostIndex=round(rng.uniform(0.5, 2.0), 2), CostBasis=rng.choice(L["CostBasisList"]))
    rows = []
    for i in range(12):
        status = rng.choice(L["StatusList"])
        area = round(math.exp(rng.uniform(math.log(0.05), math.log(500))), 3)
        u = rng.random()
        imp = 0 if u < 0.05 else 100 if u < 0.10 else rng.choice(range(0, 101, 5)) if u < 0.25 else round(rng.uniform(0, 100), 2)
        fp = round(math.exp(rng.uniform(math.log(50), math.log(2e5))), 1)
        if rng.random() < 0.05:
            fp = round(area * 43560 * 1.2, 1)       # footprint larger than drainage area (row check)
        rows.append(dict(inc="Yes" if rng.random() < 0.75 else "No", strat=rng.choice(L["StrategyList"]), bmp=rng.choice(list(m.bmps)),
                         status=status, age=(rng.randint(0, 60) if status == "Existing" else 0), lu=rng.choice(list(m.landuse)),
                         area=area, imp=imp, fp=fp, design=rng.choice(L["DesignList"]), rdep=rng.choice(L["RetDepthList"]),
                         rtime=rng.choice([rng.randint(1, 60), rng.randint(1, 365), round(rng.uniform(1, 250), 1)]),
                         soil=rng.choice(list(m.soils)), access=rng.choice(L["YesNo"])))
    if all(r["inc"] == "No" for r in rows):
        rows[0]["inc"] = "Yes"
    # forced edge cases
    bmps = list(m.bmps)
    if k < len(bmps):                                   # one case per BMP type, all rows of that type
        for r in rows:
            r["bmp"] = bmps[k]; r["inc"] = "Yes"
    if k == 0:
        s.update(RunoffMethod=L["MethodList"][1], EOS="On", BaseYear=2009)
    if k == 1:
        for j, r in enumerate(rows):
            r["imp"] = [0, 100, 5, 95, 0.4, 99.6, 50, 2.5, 97.5, 100, 0, 37.5][j]
    if k == 2:
        for j, r in enumerate(rows):
            r["rdep"] = L["RetDepthList"][j]
    if k == 4:
        for j, r in enumerate(rows):
            r["rtime"] = [1, 200, 201, 365, 0.5, 14, 30, 100, 250, 7, 3, 60][j]
    if k == 5:
        for r in rows:
            r["status"] = "Existing"; r["age"] = rng.choice([0, 1, 22, 23, 30, 45, 59])
    return s, rows


def recalc(path: Path) -> dict:
    p = subprocess.run(RECALC + [str(path.resolve()), "180"], cwd=RECALC_CWD, capture_output=True, text=True, timeout=600)
    try:
        return json.loads(p.stdout[p.stdout.index("{"):])
    except ValueError:
        return {"status": "parse_error", "stdout": p.stdout[-500:], "stderr": p.stderr[-500:]}


def main():
    wb, n, outdir = sys.argv[1], int(sys.argv[2]), Path(sys.argv[3])
    seed = int(sys.argv[4]) if len(sys.argv) > 4 else 20261016
    outdir.mkdir(parents=True, exist_ok=True)
    m = g.Model.from_workbook(wb)
    rng = random.Random(seed)
    log = []
    for k in range(n):
        s, rows = random_case(m, rng, k)
        f = outdir / f"case_{k:03d}.xlsx"
        g.write_inputs(wb, f, s, rows)
        t0 = time.time()
        rc = recalc(f)
        t_rc = time.time() - t0
        t0 = time.time()
        res = g.evaluate(m, s, rows)
        t_ev = time.time() - t0
        c = g.compare(res, g.read_results(f))
        rec = dict(case=k, n=c["n"], max_rel=c["max_rel"], at=c.get("max_rel_at"), mismatches=c["mismatches"][:20],
                   n_mismatch=len(c["mismatches"]), recalc_status=rc.get("status"), formula_errors=rc.get("total_errors"),
                   recalc_s=t_rc, engine_s=t_ev, settings=s, rows=rows,
                   n_included=sum(r["inc"] == "Yes" for r in rows), bcr=res["total"]["bcr"],
                   checks=sorted({o["check"] for o in res["rows"]}))
        log.append(rec)
        json.dump(log, open(outdir / "differential_log.json", "w"), indent=1, default=str)
        print(k, c["n"], f"{c['max_rel']:.2e}", len(c["mismatches"]), rc.get("status"), rc.get("total_errors"), f"{t_rc:.1f}s", flush=True)
        if k >= 20:              # keep a few recalculated workbooks as fixtures; delete the rest to save disk
            f.unlink()


if __name__ == "__main__":
    main()
