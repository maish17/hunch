"""Mission 3 - Catch It Before It Breaks. STUBS: remove @skip as p4maint/predict is built.

Recognise a developing trend and warn BEFORE the failure threshold. Headline metric:
warning lead time, measured against the answer key by p4maint/scoring.
"""

import unittest

TODO = unittest.skip("TODO(Mission 3): needs p4maint.predict and p4maint.scoring")


class TestMission3CatchItBeforeItBreaks(unittest.TestCase):
    @TODO
    def test_bearing_wear_warned_at_least_15_minutes_early(self):
        """Run scenarios/bearing_wear_p2_02.json; score.json lead time for F1 >= 900 s
        (true failure at 12600 s, so the first predictive warning must be by 11700 s)."""

    @TODO
    def test_warning_precedes_critical_status(self):
        """The first predictive warning for P2-02 comes before any CRITICAL channel status."""

    @TODO
    def test_ttf_estimate_and_interval_reported(self):
        """The prediction has predicted_ttf_s, an 80% interval with low <= ttf <= high, and
        predicted_failure_t_s = made_at_t_s + predicted_ttf_s."""

    @TODO
    def test_flat_signal_gives_no_prediction(self):
        """Noise around baseline -> trend_for_channel returns None (fit not significant)."""

    @TODO
    def test_mode_change_is_not_a_trend(self):
        """A TRAVERSE_EMPTY -> TRAVERSE_LOADED step in raw current is not extrapolated,
        because trends are fitted on deviation from the mode baseline."""

    @TODO
    def test_trend_away_from_limit_is_ignored(self):
        """A falling temperature never yields a time-to-failure on the high limit."""


if __name__ == "__main__":
    unittest.main()
