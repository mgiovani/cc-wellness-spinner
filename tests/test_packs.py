import unicodedata

import pytest

from cc_wellness_spinner import load_pack

PACKS = [
    ("en", "Working. "),
    ("pt-BR", "Trabalhando. "),
]

LANG_CODES = [code for code, _ in PACKS]


@pytest.mark.parametrize("lang", LANG_CODES)
def test_pack_shape(lang):
    pack = load_pack(lang)
    assert set(["name", "code", "verbs"]) <= set(pack.keys())
    assert pack["code"] == lang
    assert isinstance(pack["verbs"], list)


@pytest.mark.parametrize("lang", LANG_CODES)
def test_entry_count(lang):
    pack = load_pack(lang)
    assert 40 <= len(pack["verbs"]) <= 50


@pytest.mark.parametrize("lang,prefix", PACKS)
def test_entries_start_with_prefix(lang, prefix):
    pack = load_pack(lang)
    for verb in pack["verbs"]:
        assert verb.startswith(prefix), verb


@pytest.mark.parametrize("lang", LANG_CODES)
def test_entries_max_length(lang):
    pack = load_pack(lang)
    for verb in pack["verbs"]:
        assert len(verb) <= 64, verb


@pytest.mark.parametrize("lang", LANG_CODES)
def test_entries_no_trailing_punctuation(lang):
    pack = load_pack(lang)
    for verb in pack["verbs"]:
        assert verb[-1] not in ".!…?", verb


@pytest.mark.parametrize("lang", LANG_CODES)
def test_entries_no_emoji(lang):
    pack = load_pack(lang)
    for verb in pack["verbs"]:
        for ch in verb:
            assert unicodedata.category(ch) not in ("So", "Sk"), verb
            assert ord(ch) <= 0xFFFF, verb


@pytest.mark.parametrize("lang", LANG_CODES)
def test_entries_no_double_spaces(lang):
    pack = load_pack(lang)
    for verb in pack["verbs"]:
        assert "  " not in verb, verb


@pytest.mark.parametrize("lang", LANG_CODES)
def test_entries_unique_case_insensitive(lang):
    pack = load_pack(lang)
    lowered = [verb.lower() for verb in pack["verbs"]]
    assert len(lowered) == len(set(lowered))
