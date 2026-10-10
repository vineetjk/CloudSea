from cloudsea.jobs.grader import training_label


def test_two_photo_voters_override_the_airport():
    assert training_label(0.0, {"majority": "cloud_sea", "counts": {"cloud_sea": 2}}) == (1.0, "photos")
    assert training_label(1.0, {"majority": "socked_in", "counts": {"socked_in": 2, "cloud_sea": 1}}) == (0.0, "photos")


def test_one_photo_is_not_enough():
    assert training_label(0.0, {"majority": "cloud_sea", "counts": {"cloud_sea": 1}}) == (0.0, "airport")


def test_partial_and_ties_keep_the_airport_label():
    assert training_label(1.0, {"majority": "partial", "counts": {"partial": 3}}) == (1.0, "airport")
    assert training_label(None, {"majority": None, "counts": {"cloud_sea": 1, "clear_no_sea": 1}}) == (None, "airport")
