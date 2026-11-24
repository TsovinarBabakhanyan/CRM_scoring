"""Card payments through an Armenian bank's ArCa payment gateway.

Inecobank, ACBA and most other Armenian banks sell internet acquiring on
the ArCa gateway (ipay.arca.am). The bank gives the merchant an API login
and password, a test one first and a live one once the site is approved,
and the money lands in the merchant's account at that bank. It converts
to AMD if the account is in drams.

Unlike Stripe and PayPal, these are one-off payments: each order buys one
month or one year of a plan. Nothing renews by itself, so there is
nothing to cancel. The buyer pays again for the next period. The plan,
interval and workspace travel with the order in its jsonParams, and the
order number starts with the time it was created, so the paid period can
always be worked out again from the order alone.

Like the other billing services, this hands back plain dicts and raises
BillingError on failure (404 if the gateway doesn't know the order).
"""

import json
import secrets
import time

import requests

from .stripe_billing import BillingError

_BASE = {
    "live": "https://ipay.arca.am/payment/rest",
    "test": "https://ipaytest.arca.am:8445/payment/rest",
}
# ISO 4217 numeric codes, which is what the gateway takes.
CURRENCY_CODES = {"USD": "840", "AMD": "051", "EUR": "978", "RUB": "643"}
# The gateway's orderStatus 2 means the money was taken.
_PAID = 2
_LANGS = {"hy", "ru", "en"}


def new_order_number() -> str:
    """Unique per order (the gateway refuses repeats). It starts with the
    creation time, which marks the start of the paid period."""
    return f"{int(time.time())}-{secrets.token_hex(6)}"


def order_created_at(order_number: str) -> int | None:
    head = (order_number or "").split("-", 1)[0]
    return int(head) if head.isdigit() else None


class ArcaBilling:
    def __init__(self, username: str, password: str, mode: str = "live", base_url: str = ""):
        self.username = username
        self.password = password
        self.base = (base_url or _BASE["test" if mode == "test" else "live"]).rstrip("/")

    def _req(self, method: str, params: dict) -> dict:
        data = {"userName": self.username, "password": self.password, **params}
        try:
            resp = requests.post(f"{self.base}/{method}", data=data, timeout=30)
        except requests.RequestException as exc:
            raise BillingError(502, f"Couldn't reach the bank's payment gateway: {exc!r}") from exc
        if resp.status_code >= 400:
            raise BillingError(502, f"Bank gateway answered {resp.status_code}.")
        try:
            return resp.json()
        except ValueError as exc:
            raise BillingError(502, "Bank gateway sent an unreadable answer.") from exc

    def create_order(
        self,
        *,
        amount: int,
        currency: str,
        description: str,
        metadata: dict,
        return_url: str,
        fail_url: str,
        email: str | None = None,
        lang: str = "en",
    ) -> dict:
        """Registers an order; returns its id, our order number and the
        bank's card page URL to send the buyer to."""
        code = CURRENCY_CODES.get(currency.upper())
        if code is None:
            raise BillingError(400, f"The bank gateway can't charge in {currency}.")
        order_number = new_order_number()
        params = {
            "orderNumber": order_number,
            "amount": str(amount),
            "currency": code,
            "returnUrl": return_url,
            "failUrl": fail_url,
            "description": description[:99],
            "language": lang if lang in _LANGS else "en",
            "jsonParams": json.dumps({k: v for k, v in {**metadata, "email": email or ""}.items() if v}),
        }
        if email:
            params["email"] = email
        result = self._req("register.do", params)
        if str(result.get("errorCode") or "0") != "0" or not result.get("formUrl"):
            raise BillingError(400, f"Bank gateway: {result.get('errorMessage') or 'order was refused'}")
        return {"id": result["orderId"], "order_number": order_number, "url": result["formUrl"]}

    def get_order(self, order_id: str) -> dict:
        """The order as {id, order_number, paid, amount, currency, metadata}."""
        result = self._req("getOrderStatusExtended.do", {"orderId": order_id})
        error = str(result.get("errorCode") or "0")
        if error == "6":  # unknown order
            raise BillingError(404, "Order not found at the bank gateway.")
        if error != "0":
            raise BillingError(502, f"Bank gateway: {result.get('errorMessage') or error}")
        params = {p.get("name"): p.get("value") for p in result.get("merchantOrderParams") or [] if p.get("name")}
        return {
            "id": order_id,
            "order_number": result.get("orderNumber") or "",
            "paid": result.get("orderStatus") == _PAID,
            "amount": result.get("amount"),
            "currency": str(result.get("currency") or ""),
            "metadata": params,
        }
