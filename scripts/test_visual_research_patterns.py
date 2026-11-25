"""Deterministic checks for the compact feeds used by the visual dashboard."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import patch
from scripts import build_visual_research_patterns as builder


ROOT = Path(__file__).resolve().parents[1]
HORIZONS = [24, 48, 72, 120, 168]


def load(name: str) -> dict:
    return json.loads((ROOT / "assets" / "data" / name).read_text(encoding="utf-8"))


class VisualResearchPatternFeedTests(unittest.TestCase):
    def test_mucum_source_age_not_output_age_controls_probability(self):
        for stamp, available in [(datetime.now(timezone.utc).isoformat(), True),
                                 ("2020-01-01T00:00:00Z", False),
                                 ("2099-01-01T00:00:00Z", False), (None, False)]:
            def source(name):
                if "research_probability_" in name:
                    return {"generated_at_utc": stamp, "horizons": [{"hours": 24, "flood_probability_percent": 12}]}
                if "research_binary_" in name:
                    return {"decisions": [{"hours": 24, "decision": "NAO_VAI"}]}
                return {}
            with patch.object(builder, "load", side_effect=source):
                feed = builder.build_mucum()
            row = feed["horizons"][0]
            self.assertEqual(row["probability_percent"], 12 if available else None)
            self.assertEqual(row["decision"], "NAO_VAI" if available else None)
            self.assertEqual(feed["source_quality"]["probability"]["generated_at_utc"], stamp)

    def test_mucum_feed_contains_events_and_comparable_horizons(self) -> None:
        feed = load("research_visual_patterns_mucum_latest.json")
        self.assertEqual(feed["location"], "mucum")
        self.assertEqual(feed["threshold_cm"], 1800)
        self.assertEqual([row["hours"] for row in feed["horizons"]], HORIZONS)
        self.assertEqual(len(feed["events"]), 4)
        self.assertGreaterEqual(len(feed["models"]), 4)
        for row in feed["horizons"]:
            self.assertIn("probability_percent", row)
            self.assertIn("gefs_proxy_mm", row)
            self.assertIn("soil_moisture_m3m3", row)

    def test_santa_feed_keeps_model_disagreement_explicit(self) -> None:
        feed = load("research_visual_patterns_santa_tereza_latest.json")
        self.assertEqual(feed["location"], "santa_tereza")
        self.assertEqual([row["hours"] for row in feed["horizons"]], HORIZONS)
        self.assertEqual(feed["summary"]["model_card_event_count"], 5)
        self.assertEqual(len(feed["events"]), 4)
        for row in feed["horizons"]:
            self.assertIn("rna_score_percent", row)
            self.assertIn("probability_percent", row)
            self.assertIn("ifs_mean_mm", row)
        quality = feed.get("source_quality", {}).get("probability", {})
        if quality.get("state") == "stale":
            self.assertTrue(all(row["probability_percent"] is None for row in feed["horizons"]))
            self.assertTrue(all(row["decision"] is None for row in feed["horizons"]))
        else:
            self.assertIsNotNone(feed["horizons"][-1]["probability_percent"])


if __name__ == "__main__":
    unittest.main()
