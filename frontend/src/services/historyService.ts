import { authenticatedFetch } from './authService';

const PRODUCTION_BACKEND_ORIGIN = 'https://dpeohr327wt9l.cloudfront.net';
const CUSTOM_FRONTEND_HOST = 'livecap.logantai.com';

function apiBaseUrl(): string {
  const configured = String(import.meta.env.VITE_API_BASE_URL ?? '').trim();
  if (configured) return configured.replace(/\/$/, '');
  return window.location.hostname === CUSTOM_FRONTEND_HOST ? PRODUCTION_BACKEND_ORIGIN : '';
}

export interface TranscriptHistoryItem { history_id: string; session_id: string; created_at: string; segment_count: number; }

/**
 * Thrown by history calls so the UI can tell an expired sign-in ("auth",
 * 401/403 — needs a fresh Cognito sign-in) apart from a transient failure
 * ("network", any other non-2xx or fetch error — safe to just retry).
 */
export class HistoryError extends Error {
  readonly kind: 'auth' | 'network';
  constructor(message: string, kind: 'auth' | 'network') {
    super(message);
    this.name = 'HistoryError';
    this.kind = kind;
  }
}

function errorKindForStatus(status: number): 'auth' | 'network' {
  return status === 401 || status === 403 ? 'auth' : 'network';
}

export async function getTranscriptHistory(): Promise<TranscriptHistoryItem[]> {
  let response: Response;
  try {
    response = await authenticatedFetch(`${apiBaseUrl()}/api/transcripts`);
  } catch {
    throw new HistoryError('Could not reach the server.', 'network');
  }
  if (!response.ok) throw new HistoryError('Transcript history is unavailable.', errorKindForStatus(response.status));
  const body = await response.json() as { items?: TranscriptHistoryItem[] };
  return body.items ?? [];
}

export async function getHistoryDownloadUrl(historyId: string): Promise<string> {
  let response: Response;
  try {
    response = await authenticatedFetch(`${apiBaseUrl()}/api/transcripts/${encodeURIComponent(historyId)}/download`);
  } catch {
    throw new HistoryError('Could not reach the server.', 'network');
  }
  if (!response.ok) throw new HistoryError('Transcript download is unavailable.', errorKindForStatus(response.status));
  return (await response.json() as { download_url: string }).download_url;
}
