"""One-off PayPal payments without renewal (Orders API behind /api/billing/paypal/order)."""

import json

import pytest

from app import storage
from app.routers import billing
from app.services.paypal_billing import PayPalBilling
from app.services.stripe_billing import BillingError


class FakeOrders:
    """Answers PayPalBilling._req for the Orders API; records requests."""

    def __init__(self):
        self.requests = []
        self.orders = {}

    def __call__(self, method, path, **kwargs):
        self.requests.append((method, path, kwargs.get("json")))
        if path == "/v2/checkout/orders" and method == "POST":
            order_id = f"ORDER{len(self.orders) + 1}"
            unit = kwargs["json"]["purchase_units"][0]
            self.orders[order_id] = {
                "id": order_id,
                "status": "CREATED",
                "create_time": "2026-11-25T10:00:00Z",
                "purchase_units": [{"custom_id": unit["custom_id"], "amount": unit["amount"]}],
            }
            return {"id": order_id, "links": [{"rel": "payer-action", "href": f"https://www.paypal.com/checkoutnow?token={order_id}"}]}
        if path.startswith("/v2/checkout/orders/"):
            order_id = path.split("/")[4]
            if order_id not in self.orders:
                raise BillingError(404, "Not found at PayPal.")
            order = self.orders[order_id]
            if path.endswith("/capture"):
                if order["status"] != "APPROVED":
                    raise BillingError(400, "PayPal: ORDER_NOT_APPROVED")
                unit = order["purchase_units"][0]
                order["status"] = "COMPLETED"
                order["payer"] = {"email_address": "buyer@example.com"}
                unit["payments"] = {"captures": [{"status": "COMPLETED", "amount": unit["amount"]}]}
            return order
        raise AssertionError(f"unexpected PayPal call {method} {path}")

    def approve(self, order_id):
        self.orders[order_id]["status"] = "APPROVED"


@pytest.fixture
def orders(monkeypatch, tmp_path):
    fake = FakeOrders()
    monkeypatch.setattr(PayPalBilling, "_req", lambda self, method, path, **kw: fake(method, path, **kw))
    monkeypatch.setattr(billing, "PAYPAL_CLIENT_ID", "client")
    monkeypatch.setattr(billing, "PAYPAL_CLIENT_SECRET", "top-secret")
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


def test_order_is_one_payment_at_the_plan_price(client, orders):
    resp = client.post("/api/billing/paypal/order", json={"tier": "pro", "interval": "annual", "source": "site"})
    assert resp.status_code == 200
    assert resp.json()["url"].startswith("https://www.paypal.com/")
    _, path, body = orders.requests[-1]
    assert path == "/v2/checkout/orders"
    assert body["intent"] == "CAPTURE"
    assert body["purchase_units"][0]["amount"] == {"currency_code": "USD", "value": "192.00"}
    assert body["payment_source"]["paypal"]["experience_context"]["return_url"].endswith("/thank-you.html?paypal_order=1")


def test_unapproved_order_takes_no_money(client, orders):
    order_id = client.post("/api/billing/paypal/order", json={"interval": "monthly"}).json()["order_id"]
    assert client.get(f"/api/billing/paypal/order/{order_id}").status_code == 409
    assert orders.issued == []


def test_approved_order_is_captured_once_and_issues_one_key(client, orders):
    order_id = client.post("/api/billing/paypal/order", json={"interval": "monthly"}).json()["order_id"]
    orders.approve(order_id)
    first = client.get(f"/api/billing/paypal/order/{order_id}").json()
    again = client.get(f"/api/billing/paypal/order/{order_id}").json()
    assert first["license_key"] == "key-1" and again["license_key"] == "key-1"
    assert [p for m, p, _ in orders.requests if p.endswith("/capture")] == [f"/v2/checkout/orders/{order_id}/capture"]
    assert orders.issued[0][1:] == ("buyer@example.com", "pro", "monthly")


def test_order_for_wrong_amount_is_rejected(client, orders):
    order_id = client.post("/api/billing/paypal/order", json={"interval": "monthly"}).json()["order_id"]
    orders.orders[order_id]["purchase_units"][0]["amount"] = {"currency_code": "USD", "value": "1.00"}
    orders.approve(order_id)
    assert client.get(f"/api/billing/paypal/order/{order_id}").status_code == 400
    assert orders.issued == []


def test_order_upgrades_workspace_without_a_subscription_to_cancel(client, orders, monkeypatch):
    monkeypatch.setattr(billing, "HOSTED_MODE", True)
    tenant, api_key = storage.create_tenant("Buyer", email="buyer@example.com")
    order_id = client.post(
        "/api/billing/paypal/order", json={"tier": "advanced", "interval": "monthly"},
        headers={"Authorization": f"Bearer {api_key}"},
    ).json()["order_id"]
    orders.approve(order_id)
    assert client.get(f"/api/billing/paypal/order/{order_id}").json()["workspace_upgraded"] is True
    upgraded = storage.get_tenant_by_api_key(api_key)
    assert upgraded.plan == "advanced"
    assert upgraded.plan_expires_at is not None
    assert storage.get_tenant_subscription_id(tenant.id) is None
