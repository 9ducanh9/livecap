const DEFAULT_HEALTH_TIMEOUT_MS = 120_000;
const DEFAULT_HEALTH_POLL_INTERVAL_MS = 5_000;
const PRODUCTION_BACKEND_ORIGIN = 'https://dpeohr327wt9l.cloudfront.net';
const CUSTOM_FRONTEND_HOST = 'livecap.logantai.com';

export interface WakeBackendOptions {
  wakeUrl?: string;
  apiBaseUrl?: string;
  timeoutMs?: number;
  pollIntervalMs?: number;
}

export async function wakeBackendIfConfigured({
  wakeUrl = configuredWakeBackendUrl(),
  apiBaseUrl = import.meta.env.VITE_API_BASE_URL,
  timeoutMs = configuredWakeTimeoutMs(),
  pollIntervalMs = DEFAULT_HEALTH_POLL_INTERVAL_MS,
}: WakeBackendOptions = {}): Promise<void> {
  const normalizedWakeUrl = normalizeOptionalUrl(wakeUrl);
  if (normalizedWakeUrl === null) return;

  const healthUrl = configuredHealthUrl(apiBaseUrl);

  const wakeResponse = await fetch(normalizedWakeUrl, {
    method: 'POST',
  });

  if (!wakeResponse.ok) {
    throw new Error(`Wake endpoint returned HTTP ${wakeResponse.status}`);
  }

  await waitForBackendHealth(healthUrl, timeoutMs, pollIntervalMs);
}

export function isWakeBackendConfigured(): boolean {
  return normalizeOptionalUrl(configuredWakeBackendUrl()) !== null;
}

function configuredWakeBackendUrl(): string | undefined {
  return (
    import.meta.env.VITE_WAKE_BACKEND_URL ||
    import.meta.env.VITE_WAKE_API_URL ||
    undefined
  );
}

function configuredHealthUrl(apiBaseUrl: unknown): string {
  const explicitHealthUrl = normalizeOptionalUrl(
    import.meta.env.VITE_BACKEND_HEALTH_URL
  );
  return explicitHealthUrl ?? productionBackendUrl('/api/health') ?? buildHealthUrl(apiBaseUrl);
}

function productionBackendUrl(path: string): string | null {
  return window.location.hostname === CUSTOM_FRONTEND_HOST
    ? `${PRODUCTION_BACKEND_ORIGIN}${path}`
    : null;
}

function configuredWakeTimeoutMs(): number {
  const raw = import.meta.env.VITE_BACKEND_WAKE_TIMEOUT_SECONDS;
  if (typeof raw !== 'string' || raw.trim() === '') {
    return DEFAULT_HEALTH_TIMEOUT_MS;
  }
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return DEFAULT_HEALTH_TIMEOUT_MS;
  }
  return parsed * 1_000;
}

function normalizeOptionalUrl(value: unknown): string | null {
  if (typeof value !== 'string') return null;
  const trimmed = value.trim();
  return trimmed.length > 0 ? trimmed : null;
}

function buildHealthUrl(apiBaseUrl: unknown): string {
  const base =
    typeof apiBaseUrl === 'string' && apiBaseUrl.trim().length > 0
      ? apiBaseUrl.trim()
      : window.location.origin;
  return new URL('/api/health', ensureTrailingSlash(base)).toString();
}

function ensureTrailingSlash(value: string): string {
  return value.endsWith('/') ? value : `${value}/`;
}

async function waitForBackendHealth(
  healthUrl: string,
  timeoutMs: number,
  pollIntervalMs: number
): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown = null;

  while (Date.now() < deadline) {
    try {
      const response = await fetch(healthUrl, {
        method: 'GET',
        cache: 'no-store',
      });
      if (response.ok) return;
      lastError = new Error(`Health check returned HTTP ${response.status}`);
    } catch (err) {
      lastError = err;
    }

    await sleep(Math.min(pollIntervalMs, Math.max(0, deadline - Date.now())));
  }

  throw new Error(
    `Backend did not become healthy before timeout: ${formatError(lastError)}`
  );
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function formatError(value: unknown): string {
  if (value instanceof Error) return value.message;
  if (typeof value === 'string') return value;
  return 'unknown error';
}
