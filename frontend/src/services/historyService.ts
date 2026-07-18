import { authenticatedFetch } from './authService';

const PRODUCTION_BACKEND_ORIGIN = 'https://dpeohr327wt9l.cloudfront.net';
const CUSTOM_FRONTEND_HOST = 'livecap.logantai.com';

function apiBaseUrl(): string {
  const configured = String(import.meta.env.VITE_API_BASE_URL ?? '').trim();
  if (configured) return configured.replace(/\/$/, '');
  return window.location.hostname === CUSTOM_FRONTEND_HOST ? PRODUCTION_BACKEND_ORIGIN : '';
}

export interface TranscriptHistoryItem { history_id: string; session_id: string; created_at: string; segment_count: number; }

export async function getTranscriptHistory(): Promise<TranscriptHistoryItem[]> {
  const response = await authenticatedFetch(`${apiBaseUrl()}/api/transcripts`);
  if (!response.ok) throw new Error('Transcript history is unavailable.');
  const body = await response.json() as { items?: TranscriptHistoryItem[] };
  return body.items ?? [];
}

export async function getHistoryDownloadUrl(historyId: string): Promise<string> {
  const response = await authenticatedFetch(`${apiBaseUrl()}/api/transcripts/${encodeURIComponent(historyId)}/download`);
  if (!response.ok) throw new Error('Transcript download is unavailable.');
  return (await response.json() as { download_url: string }).download_url;
}
