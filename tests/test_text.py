from folio.chunking import chunks, context_label
from folio.extract import ExtractPool, extract
from folio.textnorm import split_name, words


def test_split_name():
    assert split_name("rapport2024_finalV2.pdf") == "rapport 2024 final V 2 pdf"
    assert split_name("FactureEDF20240312.pdf") == "Facture EDF 2024 03 12 pdf"
    assert split_name("myHTTPServer.py") == "my HTTP Server py"
    assert words("Relevé-de-compte (3).pdf") == ["releve", "de", "compte", "3", "pdf"]


def test_chunks_cover_text_with_overlap():
    text = " ".join(f"Phrase numéro {i} sur un sujet donné." for i in range(400))
    spans = chunks(text, max_chunks=100)
    assert spans[0][0] == 0
    assert spans[-1][1] == len(text)
    for (a1, b1), (a2, _) in zip(spans, spans[1:]):
        assert a2 < b1  # overlap
        assert a2 > a1
    assert len(chunks(text, max_chunks=3)) == 3


def test_context_label():
    assert context_label("devis_cuisine.pdf", "Travaux/Maison") == "devis cuisine — Travaux / Maison"


def test_extract_text_and_docx(tmp_path):
    import zipfile

    (tmp_path / "a.md").write_text("# Titre\n\nUn   paragraphe.")
    assert extract(str(tmp_path / "a.md"), "md", 1000) == "# Titre\n\nUn paragraphe."
    docx = tmp_path / "b.docx"
    with zipfile.ZipFile(docx, "w") as z:
        z.writestr(
            "word/document.xml",
            "<w:document><w:body><w:p><w:r><w:t>Bonjour</w:t></w:r></w:p><w:p><w:r><w:t>le monde &amp; co</w:t></w:r></w:p></w:body></w:document>",
        )
    assert extract(str(docx), "docx", 1000).split() == ["Bonjour", "le", "monde", "&", "co"]


def test_pool_survives_bad_files(tmp_path):
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    good = tmp_path / "good.txt"
    good.write_text("contenu")
    pool = ExtractPool(workers=1, timeout=10)
    try:
        res = {r.key: r for r in pool.map([(1, str(bad), "pdf", 100), (2, str(good), "txt", 100)])}
    finally:
        pool.close()
    assert res[1].status == "error"
    assert res[2].status == "ok" and res[2].text == "contenu"
