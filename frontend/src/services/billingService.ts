import { authenticatedFetch } from './authService';

function apiBaseUrl(): string {
  const configured = String(import.meta.env.VITE_API_BASE_URL ?? '').trim();
  return configured ? configured.replace(/\/$/, '') : '';
}

export class BillingError extends Error {}

async function redirectToUrl(response: Response, fallbackMessage: string): Promise<void> {
  if (!response.ok) throw new BillingError(fallbackMessage);
  const body = (await response.json()) as { url?: string };
  if (!body.url) throw new BillingError(fallbackMessage);
  window.location.assign(body.url);
}

/** Redirects the browser to Stripe Checkout for a new Pro/Business subscription. */
export async function startCheckout(tier: 'pro' | 'business'): Promise<void> {
  const response = await authenticatedFetch(`${apiBaseUrl()}/api/billing/checkout-session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tier }),
  });
  await redirectToUrl(response, 'Could not start checkout. Please try again.');
}

/** Redirects the browser to the Stripe Customer Portal to manage an existing subscription. */
export async function openBillingPortal(): Promise<void> {
  const response = await authenticatedFetch(`${apiBaseUrl()}/api/billing/portal-session`, {
    method: 'POST',
  });
  await redirectToUrl(response, 'Could not open the billing portal. Please try again.');
}
