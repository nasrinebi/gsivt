"""Stored results of randomized workbook cases recalculated in LibreOffice Calc (scripts/differential_test.py).
Each fixture holds the inputs and the values read from the recalculated workbook, so the comparison runs without
a spreadsheet application."""
import json
from pathlib import Path

import pytest

import gsivt as g

FIX = sorted((Path(__file__).parent / "fixtures").glob("case_*.json"))


@pytest.mark.parametrize("path", FIX, ids=[p.stem for p in FIX])
def test_fixture_case(model, path):
    d = json.load(open(path))
    s, rows, expected = d["settings"], d["rows"], d["expected"]
    # JSON keys of numeric dictionaries are strings
    expected["scenarios"]["discount"] = {float(k): v for k, v in expected["scenarios"]["discount"].items()}
    expected["scenarios"]["om"] = {float(k): v for k, v in expected["scenarios"]["om"].items()}
    cmp = g.compare(g.evaluate(model, s, rows), expected)
    assert cmp["n"] >= 900
    assert not cmp["mismatches"], cmp["mismatches"][:5]


def test_fixtures_present():
    assert len(FIX) >= 10
