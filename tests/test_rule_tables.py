"""AH Vol. I Appendix N and O tables and the wet detention equations."""
import math

import pytest

import gsivt as g


def test_table_sizes(model):
    assert len(model.roc) == 75                                   # 5 zones x 15 CN rows
    assert len({(z, d) for z, d, _ in model.ret}) == 80          # 5 zones x 16 retention depths
    assert sum(len(v) for v in model.ret.values()) == 22400      # values used by the workbook (CN 30 to 95)


def test_interpolation_reproduces_table_nodes(model):
    for (z, cn), row in model.roc.items():
        if cn > 95 or cn + 5 not in [c for zz, c in model.roc if zz == z]:
            continue
        for d, v in row.items():
            if d <= 95:
                assert g.runoff_coefficient(model, z, cn, d) == pytest.approx(v, abs=1e-12)
    for (z, dep, cn), row in model.ret.items():
        if cn >= 95:
            continue
        for d, v in row.items():
            if d <= 95:
                assert g.retention_share(model, z, float(dep), cn, d) == pytest.approx(v / 100, abs=1e-12)


def test_interpolation_is_linear_between_nodes(model):
    a, b = g.runoff_coefficient(model, 1, 70, 30), g.runoff_coefficient(model, 1, 70, 35)
    assert g.runoff_coefficient(model, 1, 70, 32.5) == pytest.approx((a + b) / 2, abs=1e-12)
    a, b = g.runoff_coefficient(model, 2, 70, 40), g.runoff_coefficient(model, 2, 75, 40)
    assert g.runoff_coefficient(model, 2, 72.5, 40) == pytest.approx((a + b) / 2, abs=1e-12)


def test_runoff_coefficients_monotonic(model):
    zones = sorted({z for z, _ in model.roc})
    for z in zones:
        cns = sorted(c for zz, c in model.roc if zz == z)
        for cn in cns:
            row = model.roc[(z, cn)]
            ds = sorted(row)
            assert all(row[ds[i]] <= row[ds[i + 1]] + 1e-12 for i in range(len(ds) - 1))
        for d in range(0, 101, 5):
            col = [model.roc[(z, c)][d] for c in cns]
            assert all(col[i] <= col[i + 1] + 1e-12 for i in range(len(col) - 1))


def test_retention_efficiency_increases_with_depth(model):
    zones = sorted({k[0] for k in model.ret})
    depths = sorted({k[1] for k in model.ret}, key=float)
    cns = sorted({k[2] for k in model.ret})
    for z in zones:
        for cn in cns:
            for d in range(5, 101, 5):
                col = [model.ret[(z, dep, cn)][d] for dep in depths]
                assert all(col[i] <= col[i + 1] + 1e-9 for i in range(len(col) - 1))


def test_wet_detention_maxima(model, example):
    s, _ = example
    cf = g.coefficients(model, s)
    tn, tp = g.wet_detention(cf, 200)
    assert tp * 100 == pytest.approx(79.9, abs=0.05)               # AH Vol. I App. O stated maximum
    assert tn * 100 == pytest.approx(42.8, abs=0.05)
    tn1, tp1 = g.wet_detention(cf, 1)
    assert tp1 == pytest.approx(0.4013) and tn1 == pytest.approx(43.75 / 5.38 / 100)
    assert cf["WD_Tmax"] == 200
