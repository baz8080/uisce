"""The rules extractor: template coverage, and above all its abstentions.

The contract under test is rules.py's: extract() answers only when a known
template matches, and the only classes it may ever emit are completion_update
and scheduled_end_with_time. Everything surprising abstains — a wrong answer
here is worse than no answer, because abstention falls back to the LLM while
a wrong answer lands in the site's numbers.
"""

import pytest

from uisce.rules import RULES_VERSION, extract

START = "2026-07-01T10:00:00+00:00"

BOILERPLATE = (
    " We recommend that you allow 3-4 hours after the estimated restoration "
    "time for your supply to fully return. Please take note of the following "
    "reference number: GAL00111111. LA01"
)


def test_rules_version_is_stamped():
    assert RULES_VERSION == "rules-v2"


class TestCompletionUpdates:
    def test_header_with_completion_phrase(self):
        result = extract(START, "<b>**Update 10:15am 18/05/2026**</b> Works are now "
                                "complete and supply should have returned." + BOILERPLATE)
        assert result["end_source"] == "completion_update"
        assert result["local_date"] == "2026-05-18"
        assert result["local_time"] == "10:15"
        assert result["recurrence"] == "none"

    def test_completion_beats_stale_schedule_below(self):
        result = extract(START, "**Update 4:51pm 15/7/2026** Works are now complete. "
                                "Works are scheduled to take place until 2pm on 15 July.")
        assert result["end_source"] == "completion_update"
        assert (result["local_date"], result["local_time"]) == ("2026-07-15", "16:51")

    def test_header_without_minutes(self):
        result = extract(START, "**Update 9am 15/07/2026** Works are now complete.")
        assert (result["local_date"], result["local_time"]) == ("2026-07-15", "09:00")

    def test_header_missing_closing_stars(self):
        result = extract(START, "**Update 2:42pm 02/07/2026 Works are now complete.")
        assert (result["local_date"], result["local_time"]) == ("2026-07-02", "14:42")

    def test_header_with_on_before_date(self):
        result = extract(START, "**Update 9:37am on 13/07/2026** Works are now completed.")
        assert (result["local_date"], result["local_time"]) == ("2026-07-13", "09:37")

    def test_header_with_dot_time(self):
        result = extract(START, "**Update 10.15am 18/05/2026** Works are now complete.")
        assert result["local_time"] == "10:15"

    def test_irish_header_meridiems(self):
        # "rn" is AM, "in" is PM, glued to the digits, no "update" word.
        result = extract(START, "**4:15in 16/07/2026** Works are now complete.")
        assert (result["local_date"], result["local_time"]) == ("2026-07-16", "16:15")
        result = extract(START, "**9:05rn 16/07/2026** Works are now complete.")
        assert result["local_time"] == "09:05"

    def test_completion_in_older_block_still_wins(self):
        result = extract(START, "**Update 8am 16/07/2026** Crews remain on site. "
                                "**Update 4:51pm 15/7/2026** Works are now complete.")
        assert result["end_source"] == "completion_update"
        assert (result["local_date"], result["local_time"]) == ("2026-07-15", "16:51")

    def test_headerless_completion_abstains(self):
        assert extract(START, "Works are now complete at 4:13pm on 28/04/2026.") is None

    def test_header_without_time_abstains(self):
        assert extract(START, "**Update am 15/07/2026** Works are now complete.") is None

    def test_twenty_four_hour_header_with_a_stray_pm(self):
        # case 245025
        result = extract(START, "**Update 16:59pm 23/09/2026** Works are now complete.")
        assert (result["local_date"], result["local_time"]) == ("2026-09-23", "16:59")

    def test_a_stray_am_on_a_twenty_four_hour_time_abstains(self):
        assert extract(START, "**Update 14:13am 06/06/2026** Works are now complete.") is None


IRISH_COMPLETION_BLOCK = (
    "Tá críoch leis an obair se o anois, agus beidh an soláthar uisce ar ais chomh "
    "luath agus is féidir.** Seans go mbeidh cur isteach ar an soláthar uisce i "
    "Shanbally. Beidh an obair seo ar siúl ó 2in go dtí 6:15in ar an 22ú Meán Fómhair. "
)
ENGLISH_ORIGINAL = (
    "Mains repair works may cause supply disruptions to Shanbally and surrounding "
    "areas in Co. Galway. Works are scheduled to take place from 2pm until 6:15pm on "
    "22 September." + BOILERPLATE
)


class TestBilingualCompletions:
    def test_english_completion_below_an_irish_one_is_read(self):
        # case 244925
        result = extract("2026-09-22T13:18:00+00:00",
                         "**11:31rn 23/09/2026 - " + IRISH_COMPLETION_BLOCK
                         + "**Update 11:31am 23/09/2026** Works are now complete and "
                         "supply should have returned to all affected areas. "
                         + ENGLISH_ORIGINAL)
        assert result["end_source"] == "completion_update"
        assert (result["local_date"], result["local_time"]) == ("2026-09-23", "11:31")

    def test_the_english_header_wins_over_an_unparseable_irish_one(self):
        # case 244845: "9:38 rn" with a space does not parse
        result = extract("2026-09-21T12:23:25+00:00",
                         "** 9:38 rn 22/09/2026 - " + IRISH_COMPLETION_BLOCK
                         + "**Update 9:38am 22/09/2026** Works are now complete. "
                         + ENGLISH_ORIGINAL)
        assert (result["local_date"], result["local_time"]) == ("2026-09-22", "09:38")

    def test_the_english_header_wins_over_a_mistyped_irish_one(self):
        # case 232673: the Irish header says morning, the English one evening
        result = extract("2026-05-06T11:12:29+00:00",
                         "**8:17rn 07/05/2026** " + IRISH_COMPLETION_BLOCK
                         + "**Update 8:17pm 07/05/2026** Works are now complete. "
                         + ENGLISH_ORIGINAL)
        assert (result["local_date"], result["local_time"]) == ("2026-05-07", "20:17")

    def test_an_empty_duplicate_header_between_them_is_skipped(self):
        # case 243212
        result = extract("2026-09-01T14:52:15+00:00",
                         "**10:44rn 2/09/2026 - " + IRISH_COMPLETION_BLOCK
                         + "**Update 10:44am 2/09/2026** "
                         + "**Update 10:44am 2/09/2026** Works are now complete. "
                         + ENGLISH_ORIGINAL)
        assert (result["local_date"], result["local_time"]) == ("2026-09-02", "10:44")

    def test_an_irish_completion_over_a_stale_english_schedule_abstains(self):
        assert extract("2026-09-22T13:18:00+00:00",
                       "**11:31rn 23/09/2026 - " + IRISH_COMPLETION_BLOCK
                       + ENGLISH_ORIGINAL) is None

    def test_an_irish_header_with_a_dotted_time_is_dated_from_its_header(self):
        result = extract("2026-07-22T13:18:00+00:00",
                         "**10.15rn 23/07/2026** " + IRISH_COMPLETION_BLOCK
                         + "**Update 10:15am 23/07/2026** Works are now complete. "
                         + ENGLISH_ORIGINAL)
        assert (result["local_date"], result["local_time"]) == ("2026-07-23", "10:15")

    def test_an_irish_completion_does_not_read_an_older_english_update(self):
        assert extract("2026-07-21T13:18:00+00:00",
                       "**10in 23/07/2026** " + IRISH_COMPLETION_BLOCK
                       + "**Update 9am 22/07/2026** Works are now complete. "
                       + "**Update 8am 22/07/2026** Crews on site. " + ENGLISH_ORIGINAL) is None

    def test_an_irish_completion_over_an_english_update_without_one_abstains(self):
        assert extract("2026-09-22T13:18:00+00:00",
                       "**11:31rn 23/09/2026 - " + IRISH_COMPLETION_BLOCK
                       + "**Update 11:31am 23/09/2026** Crews remain on site. "
                       + "**Update 9am 23/09/2026** Works are now complete. "
                       + ENGLISH_ORIGINAL) is None


class TestScheduledEnds:
    def test_until_time_on_date(self):
        result = extract(START, "Repairs to a burst water main may cause supply "
                                "disruptions. Works are scheduled to take place until "
                                "2pm on 28 April." + BOILERPLATE)
        assert result["end_source"] == "scheduled_end_with_time"
        assert (result["local_date"], result["local_time"]) == ("2026-04-28", "14:00")

    def test_from_until_same_day(self):
        result = extract(START, "Works are scheduled to take place from 10am until "
                                "7pm on 09 May." + BOILERPLATE)
        assert (result["local_date"], result["local_time"]) == ("2026-05-09", "19:00")

    def test_overnight_continuous_period(self):
        result = extract(START, "Works are scheduled to take place from 8pm on 06 July "
                                "until 11pm on 07 July." + BOILERPLATE)
        assert (result["local_date"], result["local_time"]) == ("2026-07-07", "23:00")

    def test_estimated_completion_time(self):
        result = extract(START, "Works now have an estimated completion time of 5pm "
                                "on 15 July." + BOILERPLATE)
        assert (result["local_date"], result["local_time"]) == ("2026-07-15", "17:00")

    def test_time_words(self):
        result = extract(START, "Works are scheduled to take place until midday on 3 July.")
        assert result["local_time"] == "12:00"
        result = extract(START, "Works are scheduled to take place from 4pm until "
                                "midnight on 30 April.")
        assert (result["local_date"], result["local_time"]) == ("2026-05-01", "00:00")

    def test_24_hour_time(self):
        result = extract(START, "Works are scheduled to take place until 17:00 on 3 July.")
        assert result["local_time"] == "17:00"

    def test_unil_typo(self):
        result = extract(START, "Works are scheduled to take place unil 2pm on 28 April.")
        assert (result["local_date"], result["local_time"]) == ("2026-04-28", "14:00")

    def test_numeric_date(self):
        result = extract(START, "Works are scheduled to take place until 2pm on 28/04/2026.")
        assert result["local_date"] == "2026-04-28"

    def test_year_resolves_forward_across_new_year(self):
        result = extract("2026-12-28T10:00:00+00:00",
                         "Works are scheduled to take place until 2pm on 3 January.")
        assert result["local_date"] == "2027-01-03"

    def test_newest_update_block_owns_the_schedule(self):
        result = extract(START, "**Update 8am 10/07/2026** Works are extended until 9pm "
                                "on 10 July. **Update 7am 09/07/2026** Works are "
                                "scheduled to take place until 2pm on 09 July.")
        assert (result["local_date"], result["local_time"]) == ("2026-07-10", "21:00")

    def test_same_day_midnight_is_the_end_of_that_day(self):
        # case 244089: midnight read as the start of 11 September ended the
        # works fourteen hours before they began
        result = extract("2026-09-11T12:58:09+00:00",
                         "Works are scheduled to take place from 2pm until midnight "
                         "on 11 September." + BOILERPLATE)
        assert (result["local_date"], result["local_time"]) == ("2026-09-12", "00:00")

    def test_same_day_midnight_rolls_over_a_month_end(self):
        # case 245031, spelled as 12am
        result = extract("2026-09-28T13:41:25+00:00",
                         "Works are scheduled to take place from 8pm until 12am on "
                         "30 September." + BOILERPLATE)
        assert (result["local_date"], result["local_time"]) == ("2026-10-01", "00:00")

    def test_same_day_midnight_with_the_date_on_both_ends(self):
        result = extract(START, "Works are scheduled to take place from 2pm on 11 July "
                                "until midnight on 11 July." + BOILERPLATE)
        assert (result["local_date"], result["local_time"]) == ("2026-07-12", "00:00")

    def test_midnight_after_a_start_the_day_before_stays_on_its_day(self):
        # case 233690
        result = extract("2026-05-21T10:00:00+00:00",
                         "Works are scheduled to take place from 9pm on 21 May until "
                         "12am on 22 May." + BOILERPLATE)
        assert (result["local_date"], result["local_time"]) == ("2026-05-22", "00:00")

    def test_tanker_hours_beside_the_works_end_abstain(self):
        # never the end themselves, and never simply dropped either: see below
        assert extract(START, "Works are scheduled to take place until 6pm on 22 July. "
                              "An alternative water supply will be available at the "
                              "school car park from 4:30pm until 11:59pm on 22 July."
                              + BOILERPLATE) is None

    def test_tanker_hours_in_a_revising_update_do_not_leave_the_stale_schedule(self):
        assert extract(START, "**Update 3:15pm 22/07/2026** Works are taking longer than "
                              "expected. An alternative water supply is available at the "
                              "GAA grounds until 9pm on 22 July. Works are scheduled to "
                              "take place from 9am until 5pm on 22 July.") is None

    def test_a_wastewater_station_is_not_an_alternative_supply(self):
        result = extract(START, "Works at the wastewater station may cause disruption "
                                "from 9am until 5pm on 22 July." + BOILERPLATE)
        assert (result["local_date"], result["local_time"]) == ("2026-07-22", "17:00")

    def test_midnight_after_an_evening_start_the_day_before_abstains_too(self):
        # 6h or 30h; only a literal "12am on D" names the start of D
        assert extract(START, "Works are scheduled to take place from 6pm on 21 July "
                              "until midnight on 22 July." + BOILERPLATE) is None

    def test_midnight_after_a_daytime_start_the_day_before_abstains(self):
        # 15h or 39h: the text does not say which
        assert extract(START, "Works are scheduled to take place from 9am on 21 July "
                              "until midnight on 22 July." + BOILERPLATE) is None

    def test_conflicting_schedules_in_one_block_abstain(self):
        # The original notice carries no header of its own, so a revising
        # update and the stale text below it share a segment; two different
        # ends there is ambiguity, and ambiguity is the model's job.
        assert extract(START, "**Update 8am 10/07/2026** Works are extended until 9pm "
                              "on 10 July. Works are scheduled to take place until "
                              "2pm on 09 July.") is None


class TestAbstentions:
    @pytest.mark.parametrize("description", [
        None,
        "",
        # no usable signal
        "We are investigating reports of supply disruptions. More information to follow.",
        # recurring windows are model territory (site.py:recurring_events)
        "Works are scheduled to take place nightly from 10pm until 7am, "
        "from 08 July until 17 August.",
        "Works are scheduled to take place daily from 9am until 6pm "
        "from 12 June until 15 June.",
        # enumerated day lists are the recurring form RECURRENCE_TEXT misses
        "Works are scheduled to take place until 5pm on 26 May and 27 May.",
        "Works are scheduled to take place from 9am until 5pm on 17 June, "
        "18 June and19 June.",  # feed writes "and19" with no space (case 236066)
        "Works are scheduled to take place from 9am until 5pm on 26 and 27 May.",
        # double "until": garbled at source (case 232976) or a date range the
        # model reads as recurring (case 240600)
        "Works are scheduled to take place until 6pm on 9 May until 9pm 13 May.",
        "Works are scheduled to take place from 8am until 5pm on 05 August "
        "until 07 August.",
        "A Boil Water Notice remains in place until further notice.",
        # lift wording is lifted_immediate territory
        "The Boil Water Notice which has been in place is now lifted with "
        "immediate effect.",
        # a date without its time must never become scheduled_end_date_only
        "Works are scheduled to take place until 28 April.",
        # an invalid date is a typo the model should read, not a rule
        "Works are scheduled to take place until 2pm on 31/09/2026.",
        # Irish-only completion: the English half below is stale
        "Meastar go mbeidh críoch leis an obair seo ag a 9in ar an 1ú Bealtaine. "
        "Works are scheduled to take place until 9pm on 1 May.",
        # "until midnight on D" with no start: the start or the end of D
        # (cases 232957, 232219)
        "Works are scheduled to take place until midnight on 9 May." + BOILERPLATE,
        "Works are scheduled to take place until Midnight on 30 April." + BOILERPLATE,
        "Works are scheduled to take place from until midnight on 23 July.",
        "Works now have an estimated completion time of midnight on 29 July.",
        # a start two days earlier: midnight on the last day is still either end
        "Works are scheduled to take place from 1:25pm on 17 July until midnight "
        "on 19 July.",
        # the hours an alternative supply is open, not the works' end (case 239696)
        "A pump failure may cause supply disruptions to Dundalk. Crews are working to "
        "restore supply as soon as possible. An alternative water supply will be "
        "available at the school car park in Kilcurly from 4:30pm until 11:59pm on "
        "22 July. Please boil the water before use." + BOILERPLATE,
        "Water tankers are available at Sladagh until 1pm on 28 May.",
        "Bottled water will be available at Woodview Housing Estate until 10pm on 18 July.",
        # two different schedules in one block
        "Works are scheduled to take place until 2pm on 28 April. Works are "
        "scheduled to take place until 5pm on 29 April.",
    ])
    def test_abstains(self, description):
        assert extract(START, description) is None

    def test_missing_start_date_abstains_when_year_is_needed(self):
        assert extract(None, "Works are scheduled to take place until 2pm on 28 April.") is None
        # ... but an explicit year needs no start_date to resolve
        result = extract(None, "Works are scheduled to take place until 2pm on 28/04/2026.")
        assert result["local_date"] == "2026-04-28"


# Shapes drawn from every template family above plus the known-hostile ones.
# Whatever these rules come to match in future versions, the only classes
# they may ever emit are the two below, with no window fields — emitting
# scheduled_end_date_only would silently shift ends to 23:59:59
# (build.py:reported_end_utc), and window values are the model's job.
GUARD_INPUTS = [
    "**Update 10:15am 18/05/2026** Works are now complete." + BOILERPLATE,
    "Works are scheduled to take place until 2pm on 28 April." + BOILERPLATE,
    "Works are scheduled to take place until 28 April.",
    "Works are scheduled to take place nightly from 10pm until 7am, "
    "from 08 July until 17 August.",
    "The notice has been lifted with immediate effect.",
    "We are investigating reports of supply disruptions.",
    "Due to elevated turbidity, a Boil Water Notice is issued with immediate "
    "effect until further notice.",
    "**Update 9am 2/06/2026** Works are now complete.",
    "Works now have an estimated completion time of 3pm on 29 May.",
]


class TestEmissionGuard:
    @pytest.mark.parametrize("description", GUARD_INPUTS)
    def test_only_two_classes_ever_emitted(self, description):
        result = extract(START, description)
        if result is None:
            return
        assert result["end_source"] in {"completion_update", "scheduled_end_with_time"}
        assert result["local_date"] and result["local_time"]
        assert result["recurrence"] == "none"
        assert result["window_open"] is None
        assert result["window_close"] is None
        assert result["window_first_date"] is None
        assert result["notes"].startswith("rules:")
