from gsivt.cli import main


def test_cli_run(capsys):
    assert main(["run", "--json"]) == 0
    assert '"bcr"' in capsys.readouterr().out


def test_cli_check(wb):
    assert main(["check", wb]) == 0
