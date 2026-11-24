import { useEffect, useRef, useState } from "react";
import { startPayPalCheckout, startPayPalOrder } from "../api";
import { useI18n } from "../i18n";
import type { BillingInterval, PaidTier } from "../types";

// The bits of PayPal's JS SDK this uses.
interface PayPalButton {
  isEligible(): boolean;
  render(container: HTMLElement): Promise<void>;
  close?(): Promise<void>;
}
interface PayPalSdk {
  FUNDING: { CARD: string };
  Buttons(options: {
    fundingSource: string;
    createSubscription?: () => Promise<string>;
    createOrder?: () => Promise<string>;
    onApprove: (data: { subscriptionID?: string; orderID?: string }) => void;
    onError: () => void;
  }): PayPalButton;
}

const LOCALES: Record<string, string> = { ru: "ru_RU", en: "en_US" };
const sdks: Record<string, Promise<PayPalSdk>> = {};

// A subscription and a one-off payment need PayPal's script loaded
// differently, so each loads once, under its own name.
function loadSdk(clientId: string, currency: string, lang: string, renew: boolean): Promise<PayPalSdk> {
  const name = renew ? "paypalRenew" : "paypalOnce";
  if (!(name in sdks)) {
    sdks[name] = new Promise((resolve, reject) => {
      const params = new URLSearchParams({ "client-id": clientId, components: "buttons", currency });
      if (renew) {
        params.set("vault", "true");
        params.set("intent", "subscription");
      } else {
        params.set("intent", "capture");
      }
      if (LOCALES[lang]) params.set("locale", LOCALES[lang]);
      const script = document.createElement("script");
      script.src = `https://www.paypal.com/sdk/js?${params}`;
      script.setAttribute("data-namespace", name);
      script.onload = () => {
        const loaded = (window as unknown as Record<string, PayPalSdk | undefined>)[name];
        if (loaded) resolve(loaded);
        else reject(new Error("PayPal didn't load"));
      };
      script.onerror = () => {
        delete sdks[name];
        reject(new Error("PayPal didn't load"));
      };
      document.head.appendChild(script);
    });
  }
  return sdks[name];
}

interface Props {
  clientId: string;
  currency: string;
  tier: PaidTier;
  interval: BillingInterval;
  // Subscription that renews, or one payment for one period.
  renew: boolean;
  disabled: boolean;
  onError: (message: string) => void;
}

// PayPal's "Debit or Credit Card" button: the buyer types their card in here,
// no PayPal account needed, and the money goes to the PayPal account. Our
// server starts the subscription (same plan and price as the PayPal button),
// so PayPal only collects the card. Renders nothing where PayPal doesn't
// offer card payment.
export function PayPalCardButton({ clientId, currency, tier, interval, renew, disabled, onError }: Props) {
  const { t, lang } = useI18n();
  const container = useRef<HTMLDivElement>(null);
  const [eligible, setEligible] = useState(false);
  const errorRef = useRef(onError);
  errorRef.current = onError;

  useEffect(() => {
    let cancelled = false;
    let button: PayPalButton | null = null;
    setEligible(false);
    loadSdk(clientId, currency, lang, renew).then(
      (paypal) => {
        if (cancelled || !container.current) return;
        container.current.innerHTML = "";
        const onError = () => errorRef.current(t("sub.paypalCardError"));
        button = renew
          ? paypal.Buttons({
              fundingSource: paypal.FUNDING.CARD,
              createSubscription: async () => (await startPayPalCheckout(tier, interval)).subscription_id,
              onApprove: ({ subscriptionID }) =>
                window.location.assign(`/?paypal=1&subscription_id=${encodeURIComponent(subscriptionID ?? "")}`),
              onError,
            })
          : paypal.Buttons({
              fundingSource: paypal.FUNDING.CARD,
              createOrder: async () => (await startPayPalOrder(tier, interval)).order_id,
              onApprove: ({ orderID }) =>
                window.location.assign(`/?paypal_order=1&token=${encodeURIComponent(orderID ?? "")}`),
              onError,
            });
        if (!button.isEligible()) return;
        setEligible(true);
        void button.render(container.current);
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
      void button?.close?.().catch(() => undefined);
    };
  }, [clientId, currency, lang, tier, interval, renew, t]);

  return (
    <div hidden={!eligible} className={`mt-3 w-full max-w-sm ${disabled ? "pointer-events-none opacity-50" : ""}`}>
      <p className="mb-2 text-xs text-text/75">{t("sub.paypalCardFine")}</p>
      <div ref={container} />
    </div>
  );
}
