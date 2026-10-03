from findspade.details import find_details


def details(description: str, title: str = "Roman brooch", specifics: dict | None = None):
    return find_details(title, description, specifics or {})


def test_pas_number_after_mention_in_various_wordings():
    assert details("Recorded with the PAS: NMS-6C1F05.").pas_number == "NMS-6C1F05"
    assert details("pas number SUR-A1B2C3").pas_number == "SUR-A1B2C3"
    found = details("Found in Kent.\nPortable Antiquities Scheme record LIN-D92EE4")
    assert found.pas == "Portable Antiquities Scheme record LIN-D92EE4"
    assert found.pas_number == "LIN-D92EE4"
    # "P.A.S." ends a sentence; the id in the next sentence is still found.
    assert details("Recorded with the P.A.S. Ref WMID-3F6A21").pas_number == "WMID-3F6A21"


def test_pas_mentioned_without_a_number():
    found = details("This has been recorded on the Portable Antiquity database.")
    assert found.pas == "This has been recorded on the Portable Antiquity database."
    assert found.pas_number is None


def test_id_like_text_without_a_pas_mention_is_not_a_pas_number():
    found = details("Stock code ABC-123456. Pas de problème.")
    assert found.pas is None
    assert found.pas_number is None


def test_pas_in_title_or_item_specifics():
    assert details("", title="Roman coin PAS recorded").pas == "Roman coin PAS recorded"
    found = details("", specifics={"PAS Number": "NMS-6C1F05"})
    assert found.pas_number == "NMS-6C1F05"


def test_export_licence_and_provenance_sentences():
    found = details(
        "A fine bronze axe head. Provenance: ex old Sussex collection, found 1970s.\n"
        "No export licence required for the USA! Postage is tracked."
    )
    assert found.provenance == "Provenance: ex old Sussex collection, found 1970s."
    assert found.export_licence == "No export licence required for the USA!"


def test_description_preferred_over_item_specifics():
    found = details("Provenance unknown.", specifics={"Provenance": "Roman"})
    assert found.provenance == "Provenance unknown."
    assert details("", specifics={"Provenance": "Roman"}).provenance == "Provenance: Roman"


def test_nothing_found():
    found = details("A lovely brooch, posted first class.")
    assert (found.pas, found.pas_number, found.export_licence, found.provenance) == (None,) * 4
