/**
 * enrichmentService.ts
 *
 * Frontend client for the optional English-only enrichment endpoints:
 *   - A2: POST /api/tts       (Amazon Polly)      -> MP3 audio
 *   - A3: POST /api/analyze   (Amazon Comprehend) -> sentiment + key phrases
 *
 * Both call `authenticatedFetch`, so a Cognito bearer token is attached when
 * accounts are enabled (they work anonymously otherwise). The controls are
 * shown only when the matching VITE flag is set, mirroring the backend flags.
 */

import { authenticatedFetch } from './authService';

const PRODUCTION_BACKEND_ORIGIN = 'https://dpeohr327wt9l.cloudfront.net';
const CUSTOM_FRONTEND_HOST = 'livecap.logantai.com';

function apiBaseUrl(): string {
  const configured = import.meta.env.VITE_API_BASE_URL ?? '';
  if (configured.trim() !== '') return configured.replace(/\/$/, '');
  if (window.location.hostname === CUSTOM_FRONTEND_HOST) return PRODUCTION_BACKEND_ORIGIN;
  return '';
}

export function isTtsEnabled(): boolean {
  return import.meta.env.VITE_ENABLE_TTS === 'true';
}

export function isAnalysisEnabled(): boolean {
  return import.meta.env.VITE_ENABLE_ANALYSIS === 'true';
}

export class EnrichmentError extends Error {
  constructor(message: string, public readonly statusCode?: number) {
    super(message);
    this.name = 'EnrichmentError';
  }
}

/** A2 — synthesize English speech (Amazon Polly). Returns an MP3 blob. */
export async function synthesizeSpeech(text: string): Promise<Blob> {
  let response: Response;
  try {
    response = await authenticatedFetch(`${apiBaseUrl()}/api/tts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
  } catch (err) {
    throw new EnrichmentError(`Network error: ${(err as Error).message}`);
  }
  if (!response.ok) {
    throw new EnrichmentError(`Text-to-speech failed (${response.status})`, response.status);
  }
  return response.blob();
}

export interface AnalyzeResult {
  sentiment: string;
  sentiment_scores: Record<string, number>;
  key_phrases: string[];
}

/** A3 — sentiment + key phrases on English text (Amazon Comprehend). */
export async function analyzeText(text: string): Promise<AnalyzeResult> {
  let response: Response;
  try {
    response = await authenticatedFetch(`${apiBaseUrl()}/api/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text }),
    });
  } catch (err) {
    throw new EnrichmentError(`Network error: ${(err as Error).message}`);
  }
  if (!response.ok) {
    throw new EnrichmentError(`Text analysis failed (${response.status})`, response.status);
  }
  return (await response.json()) as AnalyzeResult;
}
