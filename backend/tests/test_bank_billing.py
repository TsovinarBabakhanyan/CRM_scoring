"""Card payments through the bank's ArCa gateway (services/arca_billing.py behind routers/billing.py)."""

import json

import pytest

from app import storage
from app.routers import billing
from app.services import arca_billing
from app.services.arca_billing import ArcaBilling, order_created_at


class FakeGateway:
    """Answers ArcaBilling._req like the ArCa gateway would; records requests."""

    def __init__(self):
        self.requests = []
        self.orders = {}

    def __call__(self, method, params):
        self.requests.append((method, params))
        if method == "register.do":
            order_id = f"ord-{len(self.orders) + 1}"
            self.orders[order_id] = {
                "orderNumber": params["orderNumber"],
                "orderStatus": 0,
                "amount": int(params["amount"]),
                "currency": params["currency"],
                "merchantOrderParams": [{"name": k, "value": v} for k, v in json.loads(params["jsonParams"]).items()],
                "errorCode": "0",
            }
            return {"orderId": order_id, "formUrl": f"https://ipay.arca.am/payment/merchants/x/payment.html?mdOrder={order_id}"}
        if method == "getOrderStatusExtended.do":
            order = self.orders.get(params["orderId"])
            return order if order else {"errorCode": "6", "errorMessage": "Order not found"}
        raise AssertionError(f"unexpected gateway call {method}")

    def pay(self, order_id):
        self.orders[order_id]["orderStatus"] = 2


@pytest.fixture
def bank_mode(monkeypatch, tmp_path):
    fake = FakeGateway()
    monkeypatch.setattr(ArcaBilling, "_req", lambda self, method, params: fake(method, params))
    monkeypatch.setattr(billing, "ARCA_USERNAME", "merchant_api")
    monkeypatch.setattr(billing, "ARCA_PASSWORD", "top-secret")
    monkeypatch.setattr(billing, "_ISSUED_LICENSES_LOG", tmp_path / "issued.jsonl")
    billing.limiter.reset()
    issued = []

    def fake_issue(email, interval, tier, transaction_id):
        issued.append((transaction_id, email, tier, interval))
        with billing._ISSUED_LICENSES_LOG.open("a") as log:
            log.write(json.dumps({"transaction_id": transaction_id, "license_key": f"key-{len(issued)}"}) + "\n")
        return f"key-{len(issued)}"

    monkeypatch.setattr(billing, "_issue_and_deliver", fake_issue)
    fake.issued = issued
    return fake


def test_config_reports_bank_card(client, bank_mode):
    body = client.get("/api/billing/config").json()
    assert body["bank_card_available"] is True
    assert "top-secret" not in json.dumps(body)


def test_bank_card_unavailable_without_credentials(client, monkeypatch):
    monkeypatch.setattr(billing, "ARCA_USERNAME", "")
    assert client.get("/api/billing/config").json()["bank_card_available"] is False
    assert client.post("/api/billing/bank/checkout", json={"interval": "monthly"}).status_code == 503


def test_checkout_registers_order_in_usd_cents(client, bank_mode):
    resp = client.post(
        "/api/billing/bank/checkout",
        json={"tier": "advanced", "interval": "annual", "source": "site", "email": "buyer@example.com"},
    )
    assert resp.status_code == 200
    assert resp.json()["url"].startswith("https://ipay.arca.am/")
    method, params = bank_mode.requests[-1]
    assert method == "register.do"
    assert params["amount"] == "38400"
    assert params["currency"] == "840"
    assert params["returnUrl"].endswith("/thank-you.html?bank=1")
    assert json.loads(params["jsonParams"]) == {"tier": "advanced", "interval": "annual", "email": "buyer@example.com"}
    assert order_created_at(params["orderNumber"]) is not None


def test_unpaid_order_is_not_fulfilled(client, bank_mode):
    order_id = client.post("/api/billing/bank/checkout", json={"interval": "monthly"}).json()["order_id"]
    assert client.get(f"/api/billing/bank/order/{order_id}").status_code == 409
    assert bank_mode.issued == []


def test_paid_order_issues_one_key(client, bank_mode):
    order_id = client.post(
        "/api/billing/bank/checkout", json={"interval": "monthly", "email": "buyer@example.com"}
    ).json()["order_id"]
    bank_mode.pay(order_id)
    first = client.get(f"/api/billing/bank/order/{order_id}").json()
    again = client.get(f"/api/billing/bank/order/{order_id}").json()
    assert first["status"] == "ok" and first["license_key"] == "key-1"
    assert again["license_key"] == "key-1"
    assert len(bank_mode.issued) == 1
    assert bank_mode.issued[0][1:] == ("buyer@example.com", "pro", "monthly")


def test_order_for_wrong_amount_is_rejected(client, bank_mode):
    order_id = client.post("/api/billing/bank/checkout", json={"interval": "monthly"}).json()["order_id"]
    bank_mode.pay(order_id)
    bank_mode.orders[order_id]["amount"] = 100
    assert client.get(f"/api/billing/bank/order/{order_id}").status_code == 400
    assert bank_mode.issued == []


def test_unknown_order_is_404(client, bank_mode):
    assert client.get("/api/billing/bank/order/nope").status_code == 404


def test_paid_order_upgrades_workspace_until_period_end(client, bank_mode, monkeypatch):
    monkeypatch.setattr(billing, "HOSTED_MODE", True)
    tenant, api_key = storage.create_tenant("Buyer", email="buyer@example.com")
    order_id = client.post(
        "/api/billing/bank/checkout", json={"interval": "monthly"}, headers={"Authorization": f"Bearer {api_key}"}
    ).json()["order_id"]
    bank_mode.pay(order_id)
    body = client.get(f"/api/billing/bank/order/{order_id}").json()
    assert body["workspace_upgraded"] is True
    upgraded = storage.get_tenant_by_api_key(api_key)
    assert upgraded.plan == "pro"
    assert upgraded.plan_expires_at is not None
    # Nothing recurring, so there's nothing for the workspace to cancel.
    assert storage.get_tenant_subscription_id(tenant.id) is None


def test_gateway_currency_codes():
    assert arca_billing.CURRENCY_CODES["USD"] == "840"
    assert arca_billing.CURRENCY_CODES["AMD"] == "051"
