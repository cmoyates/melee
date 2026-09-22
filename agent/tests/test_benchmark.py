"""Latency reports distinguish failures, completion throughput and useful age."""

import unittest

from melee_agent.benchmark import summarize


class BenchmarkTests(unittest.TestCase):
    def rows(self, latency=.4):
        return [{"attempt": i + 1, "target_hz": 2, "candidate_count": 5, "question_count": 1,
            "status": "success", "submitted": True, "scheduled_seconds": i / 2,
            "finished_seconds": i / 2 + latency, "latency_seconds": latency} for i in range(100)]

    def test_report_counts_failed_and_not_submitted_attempts(self):
        rows = self.rows()
        rows.extend([{**rows[-1], "status": "failed", "latency_seconds": 3, "finished_seconds": 53},
                        {**rows[-1], "status": "not_submitted", "submitted": False, "finished_seconds": 54}])
        report = summarize(rows)
        self.assertEqual((report["attempts"], report["submitted"], report["successful"]), (102, 101, 100))
        self.assertEqual(report["latency_seconds"], {"p50": .4, "p95": .4, "p99": .4})
        self.assertEqual(report["accepted_by_age_seconds"]["0.25"], 0)
        self.assertEqual(report["accepted_by_age_seconds"]["0.5"], 100)
        self.assertLess(report["phases"]["2"]["successful_per_second"], 2)
        self.assertEqual(report["recommendation"], "proceed_at_1hz")
        self.assertFalse(report["gameplay_verified"])

    def test_small_sample_blocks_and_slow_results_reduce_cadence(self):
        self.assertEqual(summarize(self.rows()[:99])["recommendation"], "block")
        self.assertEqual(summarize(self.rows(1.5))["recommendation"], "reduce_cadence")
        self.assertEqual(summarize([])["status"], "fail")

    def test_topup_does_not_inflate_the_initial_sweep_duration(self):
        rows = self.rows()
        rows.append({**rows[0], "attempt": 121, "target_hz": 2, "scheduled_seconds": 200,
                        "finished_seconds": 200.4})
        report = summarize(rows)
        self.assertEqual(report["phases"]["2"]["attempts"], 100)
        self.assertAlmostEqual(report["phases"]["2"]["duration_seconds"], 49.9)
        self.assertEqual(report["phases"]["topup"]["attempts"], 1)

    def test_response_contract_failures_require_explicit_fallback_recommendation(self):
        rows = self.rows()
        rows.append({**rows[-1], "status": "failed", "reason": "invalid_distribution_sum"})
        report = summarize(rows)
        self.assertEqual(report["failure_reasons"], {"invalid_distribution_sum": 1})
        self.assertEqual(report["recommendation"], "proceed_at_1hz_with_strict_fallback")
