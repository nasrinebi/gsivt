"""Command-line interface.

  gsivt run   [WORKBOOK]          compute a workbook's inputs with the Python engine and print totals and strategies
  gsivt check WORKBOOK            compare the engine with the values cached in a recalculated workbook
"""
from __future__ import annotations

import argparse
import json
import sys
from importlib.resources import files

from .engine import evaluate
from .model import Model, read_inputs
from .wbresults import compare, read_results


def default_workbook() -> str:
    return str(files("gsivt") / "data" / "GSI-Monetary-Tool-v3.3.xlsx")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="gsivt", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("workbook", nargs="?", default=None); r.add_argument("--json", action="store_true")
    c = sub.add_parser("check"); c.add_argument("workbook")
    a = ap.parse_args(argv)
    wb = a.workbook or default_workbook()
    m = Model.from_workbook(wb)
    s, rows = read_inputs(wb)
    res = evaluate(m, s, rows)
    if a.cmd == "run":
        t, st = res["total"], res["scenarios"]["strategies"]
        out = dict(benefit_npv=t["bnpv"], cost_npv=t["cnpv"], bcr=t["bcr"], tn_removed_lb_yr=t["tnr"], tp_removed_lb_yr=t["tpr"],
                   strategy_A_bcr=st["A"]["bcr"], strategy_B_bcr=st["B"]["bcr"])
        if a.json:
            print(json.dumps(out, indent=1))
        else:
            for k, v in out.items():
                print(f"{k:20s} {v:,.4f}")
        return 0
    cmp = compare(res, read_results(wb))
    print(f"compared {cmp['n']} values; largest relative difference {cmp['max_rel']:.3e}; mismatches {len(cmp['mismatches'])}")
    for mm in cmp["mismatches"][:20]:
        print("  ", mm)
    return 1 if cmp["mismatches"] else 0


if __name__ == "__main__":
    sys.exit(main())
