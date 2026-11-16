from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.mt5 import MT5Adapter
from app.api import routes


class DemoTerminal:
    ACCOUNT_TRADE_MODE_DEMO = 0
    ACCOUNT_TRADE_MODE_REAL = 2

    def __init__(self, *, mode=0, server="HFMarketsGlobal-Demo", company="HF Markets (SV) Ltd", trade_allowed=True, tradeapi_disabled=False, symbol_available=True, currency="USD", balance=10000.25, equity=10012.50):
        self.mode = mode
        self.server = server
        self.company = company
        self.trade_allowed = trade_allowed
        self.tradeapi_disabled = tradeapi_disabled
        self.symbol_available = symbol_available
        self.currency = currency
        self.balance = balance
        self.equity = equity

    def initialize(self, **_kwargs):
        return True

    def terminal_info(self):
        return SimpleNamespace(connected=True, trade_allowed=self.trade_allowed, tradeapi_disabled=self.tradeapi_disabled)

    def symbol_info(self, symbol):
        return SimpleNamespace(name=symbol) if self.symbol_available and symbol == "XAUUSD" else None

    def account_info(self):
        return SimpleNamespace(
            login=12345678,
            server=self.server,
            company=self.company,
            trade_mode=self.mode,
            trade_allowed=self.trade_allowed,
            trade_expert=self.trade_allowed,
            currency=self.currency,
            balance=self.balance,
            equity=self.equity,
        )


def test_hfm_demo_ready_only_for_the_bound_demo_account():
    adapter = MT5Adapter()
    adapter._mt5 = DemoTerminal()

    status = adapter.hfm_demo_status("XAUUSD", expected_login="12345678", expected_server="HFMarketsGlobal-Demo")

    assert status.ready is True
    assert status.account_mode == "DEMO"
    assert status.broker_server == "HFMarketsGlobal-Demo"
    assert status.reason_codes == []
    assert "12345678" not in status.model_dump_json()


def test_hfm_demo_rejects_real_account_even_when_binding_matches():
    adapter = MT5Adapter()
    adapter._mt5 = DemoTerminal(mode=DemoTerminal.ACCOUNT_TRADE_MODE_REAL)

    status = adapter.hfm_demo_status("XAUUSD", expected_login="12345678", expected_server="HFMarketsGlobal-Demo")

    assert status.ready is False
    assert "HFM_DEMO_ACCOUNT_REQUIRED" in status.reason_codes


def test_hfm_demo_rejects_missing_or_mismatched_account_binding():
    adapter = MT5Adapter()
    adapter._mt5 = DemoTerminal()

    unbound = adapter.hfm_demo_status("XAUUSD", expected_login=None, expected_server=None)
    wrong = adapter.hfm_demo_status("XAUUSD", expected_login="98765432", expected_server="HFMarketsGlobal-Demo")

    assert unbound.ready is False
    assert "DEMO_ACCOUNT_BINDING_NOT_CONFIGURED" in unbound.reason_codes
    assert wrong.ready is False
    assert "DEMO_ACCOUNT_BINDING_MISMATCH" in wrong.reason_codes


def test_hfm_demo_rejects_non_hfm_company_or_disabled_terminal_trading():
    adapter = MT5Adapter()
    adapter._mt5 = DemoTerminal(company="Another Broker")
    wrong_broker = adapter.hfm_demo_status("XAUUSD", expected_login="12345678", expected_server="HFMarketsGlobal-Demo")
    adapter._mt5 = DemoTerminal(trade_allowed=False)
    trade_disabled = adapter.hfm_demo_status("XAUUSD", expected_login="12345678", expected_server="HFMarketsGlobal-Demo")

    assert wrong_broker.ready is False
    assert "HFM_BROKER_NOT_VERIFIED" in wrong_broker.reason_codes
    assert trade_disabled.ready is False
    assert "TERMINAL_OR_ACCOUNT_TRADING_DISABLED" in trade_disabled.reason_codes


def test_hfm_demo_rejects_disabled_python_trading_or_missing_exact_symbol():
    adapter = MT5Adapter()
    adapter._mt5 = DemoTerminal(tradeapi_disabled=True)
    api_disabled = adapter.hfm_demo_status("XAUUSD", expected_login="12345678", expected_server="HFMarketsGlobal-Demo")
    adapter._mt5 = DemoTerminal(symbol_available=False)
    missing_symbol = adapter.hfm_demo_status("XAUUSD", expected_login="12345678", expected_server="HFMarketsGlobal-Demo")

    assert api_disabled.ready is False
    assert "MT5_TRADE_API_DISABLED" in api_disabled.reason_codes
    assert missing_symbol.ready is False
    assert "EXACT_BROKER_SYMBOL_UNAVAILABLE" in missing_symbol.reason_codes


def test_hfm_account_connection_identifies_demo_and_real_without_exposing_login():
    adapter = MT5Adapter()
    adapter._mt5 = DemoTerminal()
    demo = adapter.hfm_account_status("XAUUSD")
    adapter._mt5 = DemoTerminal(mode=DemoTerminal.ACCOUNT_TRADE_MODE_REAL, server="HFMarketsGlobal-Live1")
    real = adapter.hfm_account_status("XAUUSD")

    assert demo.connected is True and demo.account_mode == "DEMO"
    assert real.connected is True and real.account_mode == "LIVE"
    assert real.broker_server == "HFMarketsGlobal-Live1"
    assert demo.account_id_suffix == "5678"
    assert real.account_id_suffix == "5678"
    assert "12345678" not in real.model_dump_json()


def test_hfm_account_connection_rejects_another_broker_and_missing_session():
    adapter = MT5Adapter()
    adapter._mt5 = DemoTerminal(company="Another Broker")
    other = adapter.hfm_account_status("XAUUSD")
    adapter._mt5 = DemoTerminal()
    adapter._mt5.terminal_info = lambda: None
    missing = adapter.hfm_account_status("XAUUSD")

    assert other.connected is False
    assert other.account_id_suffix is None
    assert "HFM_BROKER_NOT_VERIFIED" in other.reason_codes
    assert missing.connected is False
    assert "MT5_ACCOUNT_INFORMATION_UNAVAILABLE" in missing.reason_codes


def test_hfm_usd_financials_require_verified_broker_and_usd_account():
    adapter = MT5Adapter()
    adapter._mt5 = DemoTerminal()

    verified = adapter.hfm_account_financials()
    assert verified.data_status.value == "LIVE"
    assert verified.balance == 10000.25
    assert verified.equity == 10012.50
    assert verified.currency == "USD"
    assert "12345678" not in verified.model_dump_json()

    adapter._mt5 = DemoTerminal(company="Another Broker")
    other_broker = adapter.hfm_account_financials()
    assert other_broker.balance is None and other_broker.equity is None
    assert "HFM_BROKER_NOT_VERIFIED" in other_broker.reason_codes

    adapter._mt5 = DemoTerminal(currency="EUR")
    non_usd = adapter.hfm_account_financials()
    assert non_usd.currency == "EUR"
    assert non_usd.balance is None and non_usd.equity is None
    assert "USD_ACCOUNT_CURRENCY_REQUIRED" in non_usd.reason_codes


def test_hfm_financials_hide_missing_or_nonfinite_values():
    adapter = MT5Adapter()
    adapter._mt5 = DemoTerminal(balance=float("nan"))
    invalid = adapter.hfm_account_financials()
    assert invalid.balance is None and invalid.equity is None
    assert "ACCOUNT_FINANCIALS_INVALID" in invalid.reason_codes

    adapter._mt5 = DemoTerminal()
    adapter._mt5.terminal_info = lambda: None
    disconnected = adapter.hfm_account_financials()
    assert disconnected.balance is None
    assert "MT5_ACCOUNT_INFORMATION_UNAVAILABLE" in disconnected.reason_codes


def test_hfm_financials_route_requires_local_operator_token(monkeypatch):
    adapter = MT5Adapter()
    adapter._mt5 = DemoTerminal()
    app = FastAPI()
    app.include_router(routes.router)
    app.state.live_service = SimpleNamespace(adapter=adapter)
    monkeypatch.setattr(routes, "settings", SimpleNamespace(operator_token="owner-token"))

    with TestClient(app) as client:
        assert client.get("/api/hfm/account/financials").status_code == 403
        assert client.get("/api/hfm/account/financials", headers={"X-Pyon-Operator-Token": "wrong"}).status_code == 403
        response = client.get("/api/hfm/account/financials", headers={"X-Pyon-Operator-Token": "owner-token"})

    assert response.status_code == 200
    assert response.json()["balance"] == 10000.25
    assert response.json()["currency"] == "USD"
    assert "12345678" not in response.text
