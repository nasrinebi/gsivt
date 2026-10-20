"""Properties of the economic and crediting calculations."""
import copy

import pytest

import gsivt as g
from gsivt.model import INF


def run(model, s, rows, **kw):
    return g.evaluate(model, s, rows, **kw)


def test_annuity_matches_explicit_sum():
    for r in (0.015, 0.03, 0.07):
        for n in (10, 20, 50):
            assert g.annuity(r, n) == pytest.approx(sum((1 + r) ** -t for t in range(1, n + 1)), rel=1e-12)
    assert g.annuity(0, 20) == 20


def test_growth_annuity_matches_explicit_sum_and_limit():
    r, gr, n = 0.03, 0.01, 20
    explicit = sum((1 + gr) ** (t - 1) / (1 + r) ** t for t in range(1, n + 1))
    assert g.growth_annuity(r, gr, n) == pytest.approx(explicit, rel=1e-12)
    assert g.growth_annuity(0.03, 0.03, 20) == pytest.approx(20 / 1.03)


def test_cpi_identity_and_unknown_years(model):
    assert model.cpi_factor(2024, 2024) == 1
    assert model.cpi_factor(2024, "n/s") == 1          # undated values are not adjusted (IFERROR in the workbook)
    assert model.cpi_factor(2024, 1990) == 1           # years outside the CPI table are not adjusted
    assert model.cpi_factor(2024, 2011) == pytest.approx(model.cpi[2024] / model.cpi[2011])


def test_example_bcr(model, example):
    s, rows = example
    assert run(model, s, rows)["total"]["bcr"] == pytest.approx(0.9508756976093912, rel=1e-12)


def test_excluded_rows_contribute_nothing(model, example):
    s, rows = example
    rows2 = copy.deepcopy(rows)
    for r in rows2:
        r["inc"] = "No"
    res = run(model, s, rows2)
    assert all(res["total"][k] == 0 for k in ("bnpv", "cnpv", "tnr", "tpr", "upf"))
    assert res["total"]["bcr"] == 0


def test_largest_pollutant_basis_bounded_by_sum(model, example):
    s, rows = example
    sc = run(model, s, rows)["scenarios"]["wq_basis"]
    largest, total = sc["Largest single pollutant"]["wq"], sc["Sum of TN, TP and TSS"]["wq"]
    assert largest <= total
    assert largest >= max(sc["TN only"]["wq"], sc["TP only"]["wq"]) - 1e-9     # row-wise maximum bounds each single basis


def test_existing_assets_have_no_upfront_cost(model, example):
    s, rows = example
    rows2 = copy.deepcopy(rows)
    for r in rows2:
        r["status"], r["age"] = "Existing", 5
    res = run(model, s, rows2)
    assert res["total"]["upf"] == 0
    assert res["total"]["cnpv"] > 0


def test_replacement_timing(model, example):
    s, rows = example
    r0 = next(r for r in rows if r["inc"] == "Yes")
    o = run(model, dict(s, Period=50), [dict(r0)])["rows"][0]
    life = model.bmps[r0["bmp"]]["life"]
    n_rep = sum(1 for k in range(5) if life + k * life < 50)
    expected = o["cons"] * sum(1.03 ** -(life + k * life) for k in range(n_rep))
    assert o["rep"] == pytest.approx(expected, rel=1e-12)


def test_infiltrating_rows_remove_the_captured_load(model, example):
    s, rows = example
    for r in rows:
        if model.bmps[r["bmp"]]["method"].startswith("Retention"):
            o = run(model, s, [dict(r, inc="Yes", design=INF)])["rows"][0]
            assert o["infd"] == 1
            assert o["etn"] == pytest.approx(o["cap"]) and o["etp"] == pytest.approx(o["cap"])
            assert o["vr"] == pytest.approx(o["vt"])


def test_bcr_is_ratio_of_npvs_and_strategies_partition(model, example):
    s, rows = example
    res = run(model, s, rows)
    t, st = res["total"], res["scenarios"]["strategies"]
    assert t["bcr"] == pytest.approx(t["bnpv"] / t["cnpv"])
    if not any(r["strat"] == "A + B" for r in rows if r["inc"] == "Yes"):
        assert st["A"]["cnpv"] + st["B"]["cnpv"] == pytest.approx(t["cnpv"])
        assert st["A"]["bnpv"] + st["B"]["bnpv"] == pytest.approx(t["bnpv"])


def test_selected_scenarios_match_totals(model, example):
    s, rows = example
    res = run(model, s, rows)
    sc, t = res["scenarios"], res["total"]
    assert sc["levels"][s["Level"]]["bnpv"] == pytest.approx(t["bnpv"], rel=1e-12)
    assert sc["discount"][s["DiscRate"]]["bcr"] == pytest.approx(t["bcr"], rel=1e-12)
    assert sc["om"][1.0]["bcr"] == pytest.approx(t["bcr"], rel=1e-12)
    assert sc["wq_basis"][s["WQBasis"]]["bnpv"] == pytest.approx(t["bnpv"], rel=1e-12)


def test_value_source_switch_is_symmetric(model, example):
    s, rows = example
    a = run(model, s, rows)["scenarios"]["value_source"]
    other = [v for v in model.lists["ValueSourceList"] if v != s["ValueSource"]][0]
    b = run(model, dict(s, ValueSource=other), rows)["scenarios"]["value_source"]
    assert a["other"]["bnpv"] == pytest.approx(b["selected"]["bnpv"], rel=1e-12)


def test_coefficient_override(model, example):
    s, rows = example
    base = run(model, s, rows)["total"]
    hi = run(model, s, rows, coef_override={"Val_TN": 2 * g.coefficients(model, s)["Val_TN"]})["total"]
    assert hi["bnpv"] >= base["bnpv"] and hi["cnpv"] == base["cnpv"]


def test_blank_age_and_residence_time_count_as_zero(model, example):
    s, rows = example
    r = dict(next(r for r in rows if r["bmp"] == "Wet pond"), inc="Yes", rtime=None, status="Existing", age=None)
    o = g.evaluate(model, s, [r])["rows"][0]
    assert o["tday"] == 1 and o["check"] == "Existing asset: enter its age"
