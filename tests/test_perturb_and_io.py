import copy

import pytest

import gsivt as g
from gsivt.perturb import emc_land_use, perturbed


def test_identity_perturbation(model, example):
    s, rows = example
    assert g.evaluate(perturbed(model), s, rows)["total"]["bcr"] == pytest.approx(g.evaluate(model, s, rows)["total"]["bcr"], rel=1e-14)


def test_cost_multiplier_scales_cost_npv(model, example):
    s, rows = example
    a = g.evaluate(model, s, rows)["total"]["cnpv"]
    b = g.evaluate(perturbed(model, capx=2.0, omx=2.0), s, rows)["total"]["cnpv"]
    assert b == pytest.approx(2 * a, rel=1e-12)          # land cost is zero in the example


def test_split_emc_multiplier(model, example):
    s, rows = example
    base = g.evaluate(model, s, rows)["total"]
    same = g.evaluate(perturbed(model, emc=1.3, emc_p=1.3), s, emc_land_use(rows))["total"]
    assert same["tnr"] == pytest.approx(1.3 * base["tnr"], rel=1e-12)


def test_rule_tables_shared_not_copied(model):
    assert perturbed(model, capx=2).ret is model.ret


def test_write_read_roundtrip(tmp_path, wb, example):
    s, rows = example
    rows2 = copy.deepcopy(rows)
    rows2[0]["area"] = 12.5
    out = tmp_path / "copy.xlsx"
    g.write_inputs(wb, out, dict(s, Period=30), rows2)
    s3, rows3 = g.read_inputs(out)
    assert s3["Period"] == 30 and rows3[0]["area"] == 12.5
