from datetime import date

from neurai.fa import fa_normalize, gregorian_to_jalali, jalali_str
from neurai.fa.normalize import ZWNJ


def test_char_unification():
    assert fa_normalize("علي") == "علی"          # Arabic yeh → Persian
    assert fa_normalize("كتاب") == "کتاب"        # Arabic kaf → Persian


def test_digits():
    assert fa_normalize("٥ نفر") == "۵ نفر"       # Arabic-Indic → Persian


def test_zwnj_mi_prefix():
    assert fa_normalize("می خوایم") == f"می{ZWNJ}خوایم"
    assert fa_normalize("نمی دانم") == f"نمی{ZWNJ}دانم"


def test_zwnj_plural():
    assert fa_normalize("کتاب ها") == f"کتاب{ZWNJ}ها"


def test_punctuation_spacing():
    assert fa_normalize("چطور ؟") == "چطور؟"
    assert fa_normalize("بله،خوبم") == "بله، خوبم"


def test_jalali_known_dates():
    # Nowruz 1403 = 2024-03-20
    assert gregorian_to_jalali(2024, 3, 20) == (1403, 1, 1)
    assert gregorian_to_jalali(2026, 8, 8) == (1405, 5, 17)


def test_jalali_str():
    s = jalali_str(date(2024, 3, 20), persian_digits=False)
    assert "1403" in s and "فروردین" in s
