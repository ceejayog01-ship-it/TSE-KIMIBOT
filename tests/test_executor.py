import os
import sys
import unittest
from pathlib import Path
from unittest import mock

# mt5_execute validates API_KEY at import time; use a non-secret test value.
os.environ.setdefault("API_KEY", "unit-test-key")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import mt5_execute as mx  # noqa: E402
from mt5_execute import AccountModeNotAllowed, assert_account_mode_allowed  # noqa: E402


class AccountModeGuardTests(unittest.TestCase):
    def test_accepts_demo(self):
        for mode in (0, 0.0, "0", "DEMO", "ACCOUNT_TRADE_MODE_DEMO"):
            with self.subTest(mode=mode):
                self.assertEqual(assert_account_mode_allowed({"trade_mode": mode}), "DEMO")

    def test_accepts_real(self):
        for mode in (2, 2.0, "2", "REAL", "real", "ACCOUNT_TRADE_MODE_REAL"):
            with self.subTest(mode=mode):
                self.assertEqual(assert_account_mode_allowed({"trade_mode": mode}), "REAL")

    def test_rejects_contest(self):
        for mode in (1, "1", "CONTEST", "ACCOUNT_TRADE_MODE_CONTEST"):
            with self.subTest(mode=mode):
                with self.assertRaises(AccountModeNotAllowed):
                    assert_account_mode_allowed({"trade_mode": mode})

    def test_rejects_missing_or_unknown_mode(self):
        for account in ({}, {"trade_mode": None}, {"trade_mode": 99}, {"trade_mode": True}, {"trade_mode": "LIVE"}, None):
            with self.subTest(account=account):
                with self.assertRaises(AccountModeNotAllowed):
                    assert_account_mode_allowed(account)


class BridgeFailureTests(unittest.TestCase):
    """A bridge error must surface as a failure, never be read as 'no positions'."""

    def test_positions_error_raises(self):
        with mock.patch.object(mx, "call", side_effect=RuntimeError("bridge down")):
            with self.assertRaises(RuntimeError):
                mx.find_position("EURUSD", "TSE-A-x")

    def test_manage_counts_position_read_failure(self):
        trades = [{"status": "OPEN", "symbol": "EURUSD", "ticket": 1, "design": "A", "side": "BUY"}]
        with mock.patch.object(mx, "call", side_effect=RuntimeError("bridge down")):
            self.assertEqual(mx.manage(trades), 1)
        self.assertEqual(trades[0]["status"], "OPEN")      # not wrongly marked closed

    def test_symbol_info_error_raises(self):
        mx._INFO.clear()
        with mock.patch.object(mx, "call", side_effect=RuntimeError("bridge down")):
            with self.assertRaises(RuntimeError):
                mx.sym_info("EURUSD")


class DesignABothTradeTests(unittest.TestCase):
    def _run(self, designs):
        mx._INFO.clear()
        placed, trades = [], []

        def fake_call(method, path, **kw):
            if path.startswith("/symbol_info_tick"):
                return {"bid": 1.1000, "ask": 1.1001}
            if path.startswith("/symbol_info/"):
                return {"trade_tick_size": 0.00001, "point": 0.00001, "trade_stops_level": 0,
                        "trade_tick_value": 1.0, "volume_min": 0.01, "volume_step": 0.01}
            if path == "/account_info":
                return {"equity": 10000}
            if path == "/order/open":
                placed.append(kw["json"])
                return {}
            return {}

        def fake_get_list(path, params=None):
            return [{"ticket": 100 + i, "symbol": "EURUSD", "comment": o["comment"], "price_open": 1.1001,
                     "sl": o["sl"], "tp": o.get("tp", 0)} for i, o in enumerate(placed)]

        with mock.patch.object(mx, "call", fake_call), mock.patch.object(mx, "get_list", fake_get_list), \
                mock.patch.object(mx, "send_telegram"), mock.patch.object(mx, "is_dry", return_value=False), \
                mock.patch.dict(os.environ, {"LOT_SIZE": "0.01"}), \
                mock.patch.object(mx, "COOLDOWN_FILE", "/tmp/_cd_test.json"), mock.patch.object(mx, "STATE_DIR", "/tmp"):
            for d in designs:
                sig = {"signal_id": f"TSE-{d}-EURUSD-202601011200-R01", "pair": "EURUSD", "side": "BUY", "design": d,
                       "entry": 1.1001, "sl_dist": 0.0020, "tp_dist": 0.0013 if d == "B" else 0.0,
                       "signal_ts": __import__("time").time()}
                self.assertEqual(mx.open_signal(sig, trades, 4, "", 25, 0.25), 0)
        return placed, trades

    def test_a_and_b_both_open_on_same_symbol(self):
        placed, trades = self._run(["A", "B"])
        self.assertEqual([t["design"] for t in trades], ["A", "B"])
        self.assertEqual(len(placed), 2)
        self.assertNotIn("tp", placed[0])
        self.assertIn("tp", placed[1])

    def test_cooldown_is_written(self):
        import json
        if os.path.exists("/tmp/_cd_test.json"):
            os.remove("/tmp/_cd_test.json")
        self._run(["A"])
        with open("/tmp/_cd_test.json") as f:
            self.assertIn("EURUSD", json.load(f))


if __name__ == "__main__":
    unittest.main()
