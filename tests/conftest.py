import pytest

import gsivt as g
from gsivt.cli import default_workbook


@pytest.fixture(scope="session")
def wb():
    return default_workbook()


@pytest.fixture(scope="session")
def model(wb):
    return g.Model.from_workbook(wb)


@pytest.fixture(scope="session")
def example(wb):
    return g.read_inputs(wb)
