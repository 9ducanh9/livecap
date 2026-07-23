/** Browser-only Cognito Hosted UI client using Authorization Code + PKCE. */

export interface AuthSession {
  accessToken: string;
  idToken: string;
  refreshToken?: string;
  expiresAt: number;
}

interface AuthConfig {
  enabled: boolean;
  domain: string;
  clientId: string;
  redirectUri: string;
}

const SESSION_KEY = 'livecap.auth.session';
const PKCE_VERIFIER_KEY = 'livecap.auth.pkce_verifier';
const OAUTH_STATE_KEY = 'livecap.auth.oauth_state';

function config(): AuthConfig {
  const domain = String(import.meta.env.VITE_COGNITO_DOMAIN ?? '').trim().replace(/\/$/, '');
  const clientId = String(import.meta.env.VITE_COGNITO_CLIENT_ID ?? '').trim();
  const explicitlyEnabled = String(import.meta.env.VITE_AUTH_ENABLED ?? '').toLowerCase() === 'true';
  const requiredHosts = String(import.meta.env.VITE_AUTH_REQUIRED_HOSTS ?? '')
    .split(',')
    .map((host) => host.trim().toLowerCase())
    .filter(Boolean);
  const hostAllowed = requiredHosts.length === 0
    || requiredHosts.includes(window.location.hostname.toLowerCase());
  return {
    enabled: explicitlyEnabled && hostAllowed && domain !== '' && clientId !== '',
    domain: domain.startsWith('http') ? domain : `https://${domain}`,
    clientId,
    redirectUri: String(import.meta.env.VITE_COGNITO_REDIRECT_URI ?? `${window.location.origin}/app`).trim(),
  };
}

export function isAuthConfigured(): boolean { return config().enabled; }

export function getAuthSession(): AuthSession | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    const value = JSON.parse(raw) as AuthSession;
    return value.accessToken && value.idToken && value.expiresAt > Date.now() ? value : null;
  } catch { return null; }
}

function setSession(session: AuthSession): void { sessionStorage.setItem(SESSION_KEY, JSON.stringify(session)); }
export function getAccessToken(): string | null { return getAuthSession()?.accessToken ?? null; }
export function clearAuthSession(): void {
  sessionStorage.removeItem(SESSION_KEY);
  sessionStorage.removeItem(PKCE_VERIFIER_KEY);
  sessionStorage.removeItem(OAUTH_STATE_KEY);
}

function base64Url(bytes: Uint8Array): string {
  let binary = '';
  bytes.forEach((byte) => { binary += String.fromCharCode(byte); });
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
}
function randomBase64Url(byteLength: number): string {
  const bytes = new Uint8Array(byteLength); crypto.getRandomValues(bytes); return base64Url(bytes);
}
async function sha256Base64Url(value: string): Promise<string> {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return base64Url(new Uint8Array(digest));
}

export async function beginSignIn(identityProvider?: string): Promise<void> {
  const current = config();
  if (!current.enabled) return;
  const verifier = randomBase64Url(64);
  const state = randomBase64Url(24);
  sessionStorage.setItem(PKCE_VERIFIER_KEY, verifier);
  sessionStorage.setItem(OAUTH_STATE_KEY, state);
  const params = new URLSearchParams({
    response_type: 'code', client_id: current.clientId, redirect_uri: current.redirectUri,
    scope: 'openid email profile aws.cognito.signin.user.admin', state,
    code_challenge: await sha256Base64Url(verifier), code_challenge_method: 'S256',
  });
  if (identityProvider) params.set('identity_provider', identityProvider);
  window.location.assign(`${current.domain}/oauth2/authorize?${params.toString()}`);
}

export async function completeSignInFromRedirect(): Promise<boolean> {
  const current = config();
  if (!current.enabled) return false;
  const url = new URL(window.location.href);
  const code = url.searchParams.get('code');
  if (!code) return false;
  const expectedState = sessionStorage.getItem(OAUTH_STATE_KEY);
  if (!expectedState || expectedState !== url.searchParams.get('state')) {
    clearAuthSession(); throw new Error('Sign-in verification failed. Please try again.');
  }
  const verifier = sessionStorage.getItem(PKCE_VERIFIER_KEY);
  if (!verifier) throw new Error('Sign-in session expired. Please try again.');
  const body = new URLSearchParams({
    grant_type: 'authorization_code', client_id: current.clientId, code,
    redirect_uri: current.redirectUri, code_verifier: verifier,
  });
  const response = await fetch(`${current.domain}/oauth2/token`, {
    method: 'POST', headers: { 'Content-Type': 'application/x-www-form-urlencoded' }, body,
  });
  if (!response.ok) throw new Error('Could not complete sign in. Please try again.');
  const tokens = await response.json() as { access_token: string; id_token: string; refresh_token?: string; expires_in: number };
  setSession({
    accessToken: tokens.access_token, idToken: tokens.id_token, refreshToken: tokens.refresh_token,
    expiresAt: Date.now() + Math.max(60, tokens.expires_in) * 1_000,
  });
  sessionStorage.removeItem(PKCE_VERIFIER_KEY); sessionStorage.removeItem(OAUTH_STATE_KEY);
  window.history.replaceState({}, document.title, `${url.pathname}${url.hash}`);
  return true;
}

/** Check if the current authenticated user belongs to the Cognito "admin" group. */
export function isAdminUser(): boolean {
  const session = getAuthSession();
  if (!session?.idToken) return false;
  try {
    const payloadB64 = session.idToken.split('.')[1];
    if (!payloadB64) return false;
    const payload = JSON.parse(atob(payloadB64.replace(/-/g, '+').replace(/_/g, '/'))) as Record<string, unknown>;
    const groups = payload['cognito:groups'];
    if (Array.isArray(groups)) {
      return groups.includes('admin');
    }
    return false;
  } catch {
    return false;
  }
}

export function signOut(): void {
  const current = config(); clearAuthSession();
  if (!current.enabled) return;
  const params = new URLSearchParams({ client_id: current.clientId, logout_uri: current.redirectUri });
  window.location.assign(`${current.domain}/logout?${params.toString()}`);
}

export async function authenticatedFetch(input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> {
  const token = getAccessToken();
  const headers = new Headers(init.headers);
  if (token) headers.set('Authorization', `Bearer ${token}`);
  return fetch(input, { ...init, headers });
}
