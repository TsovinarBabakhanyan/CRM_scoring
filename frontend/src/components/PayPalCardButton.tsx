import { useEffect, useRef, useState } from "react";
import { startPayPalCheckout } from "../api";
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
    createSubscription: () => Promise<string>;
    onApprove: (data: { subscriptionID: string }) => void;
    onError: () => void;
  }): PayPalButton;
}

declare global {
  interface Window {
    paypal?: PayPalSdk;
  }
}

const LOCALES: Record<string, string> = { ru: "ru_RU", en: "en_US" };
let sdk: Promise<PayPalSdk> | null = null;

// PayPal's script loads once, the first time a checkout opens.
function loadSdk(clientId: string, currency: string, lang: string): Promise<PayPalSdk> {
  if (!sdk) {
    sdk = new Promise((resolve, reject) => {
      const params = new URLSearchParams({
        "client-id": clientId,
        vault: "true",
        intent: "subscription",
        components: "buttons",
        currency,
      });
      if (LOCALES[lang]) params.set("locale", LOCALES[lang]);
      const script = document.createElement("script");
      script.src = `https://www.paypal.com/sdk/js?${params}`;
      script.onload = () => (window.paypal ? resolve(window.paypal) : reject(new Error("PayPal didn't load")));
      script.onerror = () => {
        sdk = null;
        reject(new Error("PayPal didn't load"));
      };
      document.head.appendChild(script);
    });
  }
  return sdk;
}

interface Props {
  clientId: string;
  currency: string;
  tier: PaidTier;
  interval: BillingInterval;
  disabled: boolean;
  onError: (message: string) => void;
}

// PayPal's "Debit or Credit Card" button: the buyer types their card in here,
// no PayPal account needed, and the money goes to the PayPal account. Our
// server starts the subscription (same plan and price as the PayPal button),
// so PayPal only collects the card. Renders nothing where PayPal doesn't
// offer card payment.
export function PayPalCardButton({ clientId, currency, tier, interval, disabled, onError }: Props) {
  const { t, lang } = useI18n();
  const container = useRef<HTMLDivElement>(null);
  const [eligible, setEligible] = useState(false);
  const errorRef = useRef(onError);
  errorRef.current = onError;

  useEffect(() => {
    let cancelled = false;
    let button: PayPalButton | null = null;
    loadSdk(clientId, currency, lang).then(
      (paypal) => {
        if (cancelled || !container.current) return;
        button = paypal.Buttons({
          fundingSource: paypal.FUNDING.CARD,
          createSubscription: async () => (await startPayPalCheckout(tier, interval)).subscription_id,
          onApprove: ({ subscriptionID }) => {
            window.location.assign(`/?paypal=1&subscription_id=${encodeURIComponent(subscriptionID)}`);
          },
          onError: () => errorRef.current(t("sub.paypalCardError")),
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
  }, [clientId, currency, lang, tier, interval, t]);

  return (
    <div hidden={!eligible} className={`mt-3 w-full max-w-sm ${disabled ? "pointer-events-none opacity-50" : ""}`}>
      <p className="mb-2 text-xs text-text/75">{t("sub.paypalCardFine")}</p>
      <div ref={container} />
    </div>
  );
}
