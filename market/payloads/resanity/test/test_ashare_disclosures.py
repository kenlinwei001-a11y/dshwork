from __future__ import annotations

from datetime import date, datetime, timezone
import importlib.util
import json
from pathlib import Path
import unittest
from urllib import parse


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/ashare_disclosures.py"


def load_module():
    spec = importlib.util.spec_from_file_location("resanity_ashare_disclosures", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load A-share disclosure indexer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def timestamp(value: str) -> int:
    instant = datetime.combine(
        date.fromisoformat(value), datetime.min.time(), tzinfo=timezone.utc
    )
    return int(instant.timestamp() * 1000)


class FakeResponse:
    def __init__(self, payload):
        self.payload = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.payload


class FakeCninfo:
    def __init__(self, periodic_date="2026-03-31"):
        self.periodic_date = periodic_date
        self.requests = []

    def __call__(self, req, timeout):
        self.requests.append((req, timeout))
        if "szse_stock.json" in req.full_url:
            return FakeResponse(
                [
                    {
                        "code": "002015",
                        "zwjc": "协鑫能科",
                        "orgId": "gssz0002015",
                        "plate": "szse",
                    }
                ]
            )
        form = parse.parse_qs(req.data.decode("utf-8"))
        if form["seDate"][0].startswith("2024-"):
            raise AssertionError("unexpected discovery window")
        if len(self.requests) == 2:
            return FakeResponse(
                {
                    "announcements": [
                        {
                            "announcementId": "periodic-1",
                            "announcementTime": timestamp(self.periodic_date),
                            "announcementTitle": "协鑫能科：2025年年度报告",
                            "adjunctUrl": "finalpage/2026/periodic.PDF",
                        }
                    ],
                    "hasMore": False,
                    "totalAnnouncement": 1,
                }
            )
        return FakeResponse(
            {
                "announcements": [
                    {
                        "announcementId": "event-2",
                        "announcementTime": timestamp("2026-07-01"),
                        "announcementTitle": "关于为子公司提供担保的公告",
                        "adjunctUrl": "finalpage/2026/two.PDF",
                    },
                    {
                        "announcementId": "periodic-1",
                        "announcementTime": timestamp(self.periodic_date),
                        "announcementTitle": "<em>协鑫能科</em>：2025年年度报告",
                        "adjunctUrl": "finalpage/2026/periodic.PDF",
                    },
                    {
                        "announcementId": "event-1",
                        "announcementTime": timestamp("2026-05-01"),
                        "announcementTitle": "关于股份回购进展的公告",
                        "adjunctUrl": "finalpage/2026/one.PDF",
                    },
                ],
                "hasMore": False,
                "totalAnnouncement": 3,
            }
        )


class AShareDisclosureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = load_module()

    def test_index_covers_latest_periodic_report_or_120_days_whichever_longer(self):
        fake = FakeCninfo(periodic_date="2026-03-31")
        payload = self.module.build_index(
            "002015", date(2026, 8, 19), opener=fake
        )
        self.assertEqual(payload["status"], "OK")
        self.assertEqual(payload["coverage_from"], "2026-03-31")
        self.assertEqual(payload["coverage_through"], "2026-08-19")
        self.assertEqual(payload["latest_periodic_report"]["announcement_id"], "periodic-1")
        self.assertEqual(payload["announcement_count"], 3)
        self.assertEqual(
            [row["announcement_id"] for row in payload["announcements"]],
            ["event-2", "event-1", "periodic-1"],
        )
        self.assertEqual(payload["announcements"][0]["category"], "guarantee")
        self.assertEqual(payload["announcements"][1]["category"], "repurchase")
        coverage_form = parse.parse_qs(fake.requests[2][0].data.decode("utf-8"))
        self.assertEqual(coverage_form["seDate"], ["2026-03-31~2026-08-19"])
        self.assertEqual(coverage_form["stock"], ["002015,gssz0002015"])

    def test_120_day_window_wins_when_periodic_report_is_more_recent(self):
        fake = FakeCninfo(periodic_date="2026-06-30")
        payload = self.module.build_index(
            "002015", date(2026, 8, 19), opener=fake
        )
        self.assertEqual(payload["coverage_from"], "2026-04-21")

    def test_explicit_start_skips_periodic_discovery(self):
        fake = FakeCninfo()
        payload = self.module.build_index(
            "002015",
            date(2026, 8, 19),
            date_from=date(2026, 8, 1),
            opener=fake,
        )
        self.assertEqual(len(fake.requests), 2)
        self.assertEqual(payload["coverage_from"], "2026-08-01")
        self.assertIsNone(payload["latest_periodic_report"])

    def test_resolution_fails_closed_on_ambiguous_or_missing_match(self):
        def empty(req, timeout):
            return FakeResponse([])

        with self.assertRaises(self.module.DisclosureUnavailable):
            self.module.resolve_company("002015", opener=empty)

    def test_title_classification_does_not_treat_summary_as_full_periodic_report(self):
        self.assertEqual(
            self.module.classify_title("协鑫能科：2025年年度报告"),
            "periodic_report",
        )
        self.assertEqual(
            self.module.classify_title("协鑫能科：2025年年度报告摘要"),
            "other",
        )
        self.assertEqual(
            self.module.classify_title("协鑫能科：2026年一季度报告"),
            "periodic_report",
        )


if __name__ == "__main__":
    unittest.main()
