"""Scoring against the answer key. STUBS: remove @skip as p4maint/scoring is built."""

import unittest

TODO = unittest.skip("TODO(scoring): needs p4maint.scoring")


class TestScoring(unittest.TestCase):
    @TODO
    def test_lead_time_arithmetic(self):
        """failure_t_s 12600 and first predictive warning at 10500 -> lead time 2100 s."""

    @TODO
    def test_missed_fault(self):
        """No predictive warning before failure_t_s -> lead time None and counted as missed."""

    @TODO
    def test_wrong_diagnosis_is_flagged(self):
        """A warning whose fault_mode differs from the injected fault_type counts as a
        warning but diagnosis_correct = false."""

    @TODO
    def test_false_positive_count(self):
        """Work orders on robots with no injected fault are counted as false positives."""


if __name__ == "__main__":
    unittest.main()
