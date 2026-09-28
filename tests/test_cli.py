from findspade.cli import main


def test_urls_prints_one_line_per_term(capsys):
    main(["urls", "--terms", '"uk antiquity",bronze age axe'])
    lines = capsys.readouterr().out.splitlines()
    assert [line.split("\t")[0] for line in lines] == ['"uk antiquity"', "bronze age axe"]
