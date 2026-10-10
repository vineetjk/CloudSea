from datetime import date

from cloudsea import plan, writer


def facts(**over) -> writer.Facts:
    base = dict(day_label="Sun 11 Oct", verdict="SKIP", probability_pct=8, sunrise="06:09", first_light="05:46",
                area_label="Electronics City", drive_minutes=95, buffer_minutes=20, leave_by="03:20",
                summit_temp_c=17, wind_kmh=9, rain_chance_pct=10, carry=["Light jacket (summit about 17°C)", "Water"])
    base.update(over)
    return writer.Facts(**base)


def test_good_draft_passes():
    text = "SKIP for Sun 11 Oct: 8% chance of a cloud sea. Sunrise 06:09. Leave Electronics City by 03:20. Carry a light jacket."
    assert writer.check(text, facts()) == []


def test_invented_number_is_caught():
    text = "SKIP for Sun 11 Oct: 8% chance. Sunrise 06:09. Leave by 03:20. It will be 12°C at the top."
    assert any("numbers not from tools" in p for p in writer.check(text, facts()))


def test_dropped_leading_zero_in_times_is_fine():
    text = "SKIP for Sun 11 Oct, 8% chance of a cloud sea. Sunrise 6:09. Leave by 3:20. Carry water."
    assert writer.check(text, facts()) == []


def test_missing_verdict_or_probability_is_caught():
    problems = writer.check("Sunrise 06:09. Leave by 03:20. Carry water.", facts())
    assert "verdict missing" in problems and "probability missing" in problems


def test_hurry_language_is_caught():
    text = "GO for Sun 11 Oct, 8% chance. Sunrise 06:09. Leave by 03:20 and drive fast."
    assert "hurry language" in writer.check(text, facts(verdict="GO"))


def test_too_long_is_caught():
    text = "SKIP 8% 06:09 03:20 " + "word " * 50
    assert any("words" in p for p in writer.check(text, facts()))


def test_template_always_passes_its_own_guardrail():
    for verdict, pct in [("GO", 72), ("MAYBE", 41), ("SKIP", 3)]:
        f = facts(verdict=verdict, probability_pct=pct)
        assert writer.check(writer.template(f), f) == []


def test_leave_by_includes_buffer_and_arrives_before_sunrise():
    sun = plan.sun_times(date(2026, 10, 11))
    assert sun["first_light"] < sun["sunrise"]
    assert 5 <= sun["sunrise"].hour <= 6
    for row in plan.leave_by(sun["sunrise"]):
        assert row["buffer_minutes"] == plan.BUFFER_MIN
        assert row["leave_by"] < f"{sun['sunrise']:%H:%M}"


def test_degree_sign_does_not_smuggle_in_zero():
    assert "0" not in facts().allowed_numbers()
    text = "SKIP for Sun 11 Oct: 8% chance, 0 seas expected. Sunrise 06:09. Leave by 03:20."
    assert any("numbers not from tools" in p for p in writer.check(text, facts()))
