from urllib.parse import parse_qs, urlsplit

from findspade.terms import parse_terms_arg, read_terms_file, search_url, slugify


def query(url: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(url).query, keep_blank_values=True)


def test_parse_terms_arg_keeps_quotes_and_splits_only_outside_them():
    text = '"uk antiquity", bronze age axe ,"brooch, saxon",,'
    assert parse_terms_arg(text) == ['"uk antiquity"', "bronze age axe", '"brooch, saxon"']


def test_read_terms_file_skips_blanks_and_comments(tmp_path):
    path = tmp_path / "terms.txt"
    path.write_text("# metalwork\nroman coin\n\n  bronze age axe  \n# end\n", encoding="utf-8")
    assert read_terms_file(path) == ["roman coin", "bronze age axe"]


def test_search_url_sets_keywords_and_keeps_filters():
    q = query(search_url("roman coin"))
    assert q["_nkw"] == ["roman coin"]
    assert "_pgn" not in q
    # The filters that make this a UK-seller / US-buyer sold-items search.
    assert q["LH_Sold"] == ["1"]
    assert q["LH_LocatedIn"] == ["1"]
    assert q["_salic"] == ["3"]
    assert q["LH_ItemCondition"] == ["3000"]
    assert q["_ipg"] == ["240"]


def test_search_url_adds_page_number_after_first_page():
    assert query(search_url("roman coin", page=3))["_pgn"] == ["3"]


def test_search_url_uses_plus_for_spaces_and_keeps_user_quotes():
    assert "_nkw=UK+Antiquity&" in search_url("UK Antiquity")
    assert "_nkw=%22UK+Antiquity%22&" in search_url('"UK Antiquity"')


def test_slugify_keeps_distinct_terms_distinct():
    terms = ["roman coin", "roman-coin", '"roman coin"', "roman_coin", "roman  coin"]
    assert len({slugify(t) for t in terms}) == len(terms)
    assert slugify("Roman-Coin") == "roman_2dcoin"
