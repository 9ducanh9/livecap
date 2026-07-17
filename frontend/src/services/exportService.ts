/**
 * exportService.ts
 *
 * Serializes finalized segments to TXT and posts them to the backend export
 * endpoint (POST /api/sessions/{session_id}/export).
 *
 * Requirements: 7.1, 7.2, 7.3, 8.5, 9.2
 */

import type { Segment, SessionSummary } from '../types';

const PRODUCTION_BACKEND_ORIGIN = 'https://dpeohr327wt9l.cloudfront.net';
const CUSTOM_FRONTEND_HOST = 'livecap.logantai.com';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Shape of the segment payload sent in the export request body. */
interface ExportSegmentPayload {
  segment_id: string;
  speaker_label: string;
  text_vi: string;
  text_en: string;
  spoken_language: 'vi' | 'en';
  timestamp_start: number;
  timestamp_end: number;
}

/** Request body for POST /api/sessions/{session_id}/export */
interface ExportRequestBody {
  segments: ExportSegmentPayload[];
  summary_text?: string;
}

/** Successful response from the export endpoint. */
export interface ExportResponse {
  download_url: string;
  expires_at: string;
}

/** Error thrown when the export request fails. */
export class ExportError extends Error {
  constructor(
    message: string,
    public readonly statusCode?: number,
  ) {
    super(message);
    this.name = 'ExportError';
  }
}

function resolveApiBaseUrl(baseUrl?: string): string {
  const configuredUrl = baseUrl ?? import.meta.env.VITE_API_BASE_URL ?? '';
  if (configuredUrl.trim() !== '') {
    return configuredUrl.replace(/\/$/, '');
  }
  if (window.location.hostname === CUSTOM_FRONTEND_HOST) {
    return PRODUCTION_BACKEND_ORIGIN;
  }
  return '';
}

// ---------------------------------------------------------------------------
// TXT serialisation (Req 7.1, 7.2, 7.3)
// ---------------------------------------------------------------------------

/**
 * Serialize an ordered list of finalized segments to the TXT format:
 *   [Speaker Label] VI: {text_vi} | EN: {text_en}
 *
 * Segments are written one per line in the order supplied (finalization
 * sequence — Correctness Property CP-4, Req 7.2). An empty array produces
 * an empty string (Req 7.3).
 */
export function serializeSegmentsToTxt(segments: Segment[]): string {
  return segments
    .filter((s) => s.isFinal)
    .map((s) => `[${s.speakerLabel}] VI: ${s.textVi} | EN: ${s.textEn}`)
    .join('\n');
}

/**
 * Render a SessionSummary into the plain-text block prepended to the exported
 * transcript. Mirrors the backend `summary_to_text` layout. Returns an empty
 * string when the summary has no content.
 */
export function buildSummaryText(summary: SessionSummary): string {
  const parts: string[] = [];
  if (summary.summary_en.trim()) parts.push(`Summary (EN):\n${summary.summary_en.trim()}`);
  if (summary.summary_vi.trim()) parts.push(`Tóm tắt (VI):\n${summary.summary_vi.trim()}`);
  const block = (title: string, items: string[]): void => {
    if (items.length > 0) parts.push(`${title}:\n${items.map((i) => `  - ${i}`).join('\n')}`);
  };
  block('Key points', summary.key_points);
  block('Decisions', summary.decisions);
  block('Action items', summary.action_items);
  if (summary.topics.length > 0) parts.push(`Topics: ${summary.topics.join(', ')}`);
  if (parts.length === 0) return '';
  return `=== MEETING SUMMARY ===\n\n${parts.join('\n\n')}\n\n${'='.repeat(24)}`;
}

// ---------------------------------------------------------------------------
// API call (Req 8.5, 9.2)
// ---------------------------------------------------------------------------

/**
 * Post finalized segments to the backend export endpoint.
 *
 * @param sessionId  The Session_ID for the current session.
 * @param segments   The full segment list; non-final segments are ignored.
 * @param baseUrl    Optional base URL override (useful for testing/dev proxy).
 *
 * @returns The export response containing `download_url` and `expires_at`.
 * @throws  {ExportError} on network failure or non-2xx HTTP status.
 */
export async function exportTranscript(
  sessionId: string,
  segments: Segment[],
  summaryText?: string | null,
  baseUrl?: string,
): Promise<ExportResponse> {
  const finalizedSegments = segments.filter((s) => s.isFinal);

  const payload: ExportRequestBody = {
    segments: finalizedSegments.map((s) => ({
      segment_id: s.segmentId,
      speaker_label: s.speakerLabel,
      text_vi: s.textVi,
      text_en: s.textEn,
      spoken_language: s.spokenLanguage,
      timestamp_start: s.timestampStart,
      timestamp_end: s.timestampEnd,
    })),
  };
  if (summaryText && summaryText.trim() !== '') {
    payload.summary_text = summaryText;
  }

  const apiBaseUrl = resolveApiBaseUrl(baseUrl);
  const url = `${apiBaseUrl}/api/sessions/${encodeURIComponent(sessionId)}/export`;

  let response: Response;
  try {
    response = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
  } catch (networkError) {
    throw new ExportError(
      `Network error while exporting transcript: ${(networkError as Error).message}`,
    );
  }

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      if (typeof body?.detail === 'string') detail = body.detail;
    } catch {
      // ignore JSON parse failure — use statusText
    }
    throw new ExportError(
      `Export failed (${response.status}): ${detail}`,
      response.status,
    );
  }

  const data = await response.json() as ExportResponse;
  return data;
}
