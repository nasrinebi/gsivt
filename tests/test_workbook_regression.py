"""The engine reproduces every value cached in the distributed workbook."""
import gsivt as g


def test_example_workbook_matches_engine(model, example, wb):
    s, rows = example
    cmp = g.compare(g.evaluate(model, s, rows), g.read_results(wb))
    assert cmp["n"] >= 900
    assert not cmp["mismatches"], cmp["mismatches"][:5]
    assert cmp["max_rel"] < 1e-12
