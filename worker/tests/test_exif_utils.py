from app.exif_utils import _as_float, _gps_to_decimal, _shutter_speed_label


def test_gps_to_decimal_positive_ref() -> None:
    assert _gps_to_decimal((51.0, 30.0, 0.0), "N") == 51.5


def test_gps_to_decimal_negative_ref() -> None:
    assert _gps_to_decimal((51.0, 30.0, 0.0), "S") == -51.5


def test_gps_to_decimal_missing_coord() -> None:
    assert _gps_to_decimal((), "N") is None


def test_shutter_speed_label_fast() -> None:
    assert _shutter_speed_label(0.005) == "1/200s"


def test_shutter_speed_label_slow() -> None:
    assert _shutter_speed_label(2.0) == "2.0s"


def test_shutter_speed_label_none() -> None:
    assert _shutter_speed_label(None) is None


def test_as_float_none() -> None:
    assert _as_float(None) is None


def test_as_float_coerces() -> None:
    assert _as_float(3) == 3.0
