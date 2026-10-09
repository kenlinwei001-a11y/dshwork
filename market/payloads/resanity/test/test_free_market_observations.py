from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/free_market_observations.py"


def load_module():
    spec = importlib.util.spec_from_file_location("resanity_market_source_policy", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load free_market_observations")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class MarketSourcePriorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.market = load_module()

    def request(self, provider=None, override_reason=None):
        request = {
            "as_of_date": "2026-08-19",
            "lookback_calendar_days": 90,
            "candidate": {
                "name": "创业板指",
                "ticker": "399006",
                "exchange": "XSHE",
                "asset_type": "INDEX",
            },
            "benchmark": {
                "name": "沪深300",
                "ticker": "000300",
                "exchange": "XSHG",
                "asset_type": "INDEX",
            },
        }
        if provider is not None:
            request["provider"] = provider
        if override_reason is not None:
            request["provider_override_reason"] = override_reason
        return request

    def readiness(self, **overrides):
        values = {
            "TUSHARE": True,
            "BAOSTOCK": True,
            "AKSHARE_TENCENT": True,
        }
        values.update(overrides)
        return values

    def test_auto_selects_tushare_when_locally_ready(self) -> None:
        with mock.patch.object(
            self.market, "_local_provider_readiness", return_value=self.readiness()
        ):
            normalized = self.market._request(self.request())
        self.assertEqual(normalized["provider"], "TUSHARE")
        self.assertEqual(
            normalized["provider_policy"]["selection"],
            "AUTO_HIGHEST_LOCALLY_READY",
        )
        self.assertEqual(
            normalized["provider_policy"]["priority"],
            ["TUSHARE", "BAOSTOCK", "AKSHARE_TENCENT"],
        )

    def test_auto_uses_next_locally_ready_provider_without_network_fallback(self) -> None:
        with mock.patch.object(
            self.market,
            "_local_provider_readiness",
            return_value=self.readiness(TUSHARE=False),
        ):
            normalized = self.market._request(self.request("AUTO"))
        self.assertEqual(normalized["provider"], "BAOSTOCK")

    def test_lower_priority_provider_requires_explicit_reason(self) -> None:
        with mock.patch.object(
            self.market, "_local_provider_readiness", return_value=self.readiness()
        ):
            with self.assertRaises(self.market.AcquisitionError) as caught:
                self.market._request(self.request("BAOSTOCK"))
        self.assertEqual(caught.exception.status, "REQUEST_REJECTED")
        self.assertEqual(
            caught.exception.reason, "higher_priority_provider_available:TUSHARE"
        )

    def test_explicit_override_is_recorded_in_request_and_receipt(self) -> None:
        observations = [{"date": "2026-08-19", "close": 100.0}]
        series = {
            label: {
                "name": label,
                "ticker": "399006" if label == "candidate" else "000300",
                "exchange": "XSHE" if label == "candidate" else "XSHG",
                "source": "BaoStock",
                "source_class": "SECONDARY_MARKET_DATA",
                "source_url": "https://www.baostock.com/",
                "observations": observations,
            }
            for label in ("candidate", "benchmark")
        }
        with (
            mock.patch.object(
                self.market, "_local_provider_readiness", return_value=self.readiness()
            ),
            mock.patch.object(
                self.market,
                "_collect_baostock",
                return_value=(series, {"provider_version": "test"}),
            ),
        ):
            packet = self.market.collect(
                self.request("BAOSTOCK", "Tushare endpoint permission denied"),
                now=datetime(2026, 8, 19, tzinfo=timezone.utc),
            )
        policy = packet["acquisition_receipt"]["provider_policy"]
        self.assertEqual(policy["selection"], "EXPLICIT_OVERRIDE")
        self.assertEqual(
            policy["override_reason"], "Tushare endpoint permission denied"
        )
        self.assertEqual(packet["acquisition_receipt"]["attempted_providers"], ["BAOSTOCK"])
        self.assertFalse(packet["acquisition_receipt"]["fallback_attempted"])

    def test_selected_provider_failure_does_not_call_next_provider(self) -> None:
        with (
            mock.patch.object(
                self.market, "_local_provider_readiness", return_value=self.readiness()
            ),
            mock.patch.object(
                self.market,
                "_collect_tushare",
                side_effect=self.market.AcquisitionError(
                    "PROVIDER_PERMISSION_DENIED", "tushare_permission_denied:index_daily"
                ),
            ),
            mock.patch.object(self.market, "_collect_baostock") as baostock,
        ):
            with self.assertRaises(self.market.AcquisitionError):
                self.market.collect(self.request("AUTO"))
        baostock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
