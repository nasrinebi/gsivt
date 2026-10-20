# gsivt: GSI Monetary Valuation Tool, version 3.3

The GSI Monetary Valuation Tool estimates annual runoff and nutrient load reductions of green stormwater infrastructure
(GSI) and conventional practices with the methods of the Florida Environmental Resource Permit Applicant's Handbook
Volume I (2024), Appendices N and O, and converts them, with co-benefits and lifecycle costs, into net present values
and benefit-cost ratios. It was developed for the Florida Department of Environmental Protection under Agreement NF116
(Task 2).

The tool is distributed as a macro-free Excel workbook (`src/gsivt/data/GSI-Monetary-Tool-v3.3.xlsx`). This repository
adds a Python package that

* reads the workbook (rule tables, coefficients and Calculator inputs) and recomputes every Calculator, totals and
  Scenarios value with an independent implementation (`gsivt.evaluate`);
* compares the Python results with the values a spreadsheet application has cached in a workbook (`gsivt check`);
* supports batch, sensitivity and benchmark analyses that the workbook cannot run (`gsivt.perturb`);
* contains the test suite and the randomized differential test used to verify the workbook.

## Installation

```
pip install .            # engine and command-line interface (requires Python 3.10 or later and openpyxl)
pip install .[test]      # adds pytest and pytest-cov
pip install .[analysis]  # adds NumPy, pandas and SALib for the sensitivity analyses
```

## Use

```
gsivt run                       # the example portfolio in the distributed workbook
gsivt run my_project.xlsx       # any copy of the workbook with your inputs
gsivt check my_project.xlsx     # compare the engine with the values saved by Excel or LibreOffice
```

```python
import gsivt as g
wb = "my_project.xlsx"
m = g.Model.from_workbook(wb)
settings, rows = g.read_inputs(wb)
res = g.evaluate(m, settings, rows)
print(res["total"]["bcr"], res["scenarios"]["strategies"]["B"]["bcr"])
```

## Verification

* `pytest` runs 49 tests: rule-table checks (node reproduction, interpolation, monotonicity, wet detention maxima),
  economic identities, a regression test against the distributed workbook (930 values) and 20 stored cases of the
  randomized differential test. Statement coverage of the package is reported with `pytest --cov=gsivt`.
* `scripts/differential_test.py WORKBOOK N OUTDIR` writes N random input configurations into copies of the workbook,
  recalculates them with LibreOffice Calc and compares every value with the engine. Set the environment variable
  `GSIVT_RECALC` to the recalculation command (see the comment at the top of the script).

## Citation

Alamdari, N. (2026). GSI Monetary Valuation Tool (gsivt), version 3.3.0. Source code: https://github.com/nasrinebi/gsivt. The archived release and its DOI are on Zenodo; see `CITATION.cff`.

## Licence

Released under the MIT License (see `LICENSE`). The manuals, validation workbook, evaluation scripts and derived data are archived separately on Zenodo under the Creative Commons Attribution 4.0 International licence (CC BY 4.0).
