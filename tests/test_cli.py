from findspade.cli import main


def test_urls_prints_one_line_per_term(capsys):
    main(["urls", "--terms", '"roman coin","bronze age axe"'])
    lines = capsys.readouterr().out.splitlines()
    assert [line.split("\t")[0] for line in lines] == ["roman coin", "bronze age axe"]
