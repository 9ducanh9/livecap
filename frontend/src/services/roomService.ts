import type { Segment } from '../types';
import { authenticatedFetch } from './authService';

export interface HostedRoom {
  roomCode: string;
  hostToken: string;
  joinUrl: string;
  title: string;
  status: 'live' | 'ended';
  createdAt: string;
  liveExpiresAt: string;
  expiresAt: string;
}

export interface RoomSnapshot {
  roomCode: string;
  title: string;
  status: 'live' | 'ended';
  viewerCount: number;
  sequence: number;
  segments: Segment[];
}

export function isSharedRoomsEnabled(): boolean {
  return String(import.meta.env.VITE_ENABLE_SHARED_ROOMS ?? '').toLowerCase() === 'true';
}

export async function createSharedRoom(title: string): Promise<HostedRoom> {
  const response = await authenticatedFetch(`${apiBaseUrl()}/api/rooms`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) {
    throw new Error(await roomError(response, 'Could not create a caption room.'));
  }
  const payload = await response.json() as Record<string, unknown>;
  const roomCode = requiredString(payload, 'room_code');
  return {
    roomCode,
    hostToken: requiredString(payload, 'host_token'),
    joinUrl: `${window.location.origin}/rooms/${roomCode}`,
    title: requiredString(payload, 'title'),
    status: payload['status'] === 'ended' ? 'ended' : 'live',
    createdAt: requiredString(payload, 'created_at'),
    liveExpiresAt: requiredString(payload, 'live_expires_at'),
    expiresAt: requiredString(payload, 'expires_at'),
  };
}

export async function closeSharedRoom(room: HostedRoom): Promise<void> {
  const response = await fetch(
    `${apiBaseUrl()}/api/rooms/${encodeURIComponent(room.roomCode)}/close`,
    {
      method: 'POST',
      headers: { 'X-LiveCap-Room-Token': room.hostToken },
    },
  );
  if (!response.ok && response.status !== 404) {
    throw new Error(await roomError(response, 'Could not close the caption room.'));
  }
}

export function buildRoomWebSocketUrl(roomCode: string): string {
  const configured = String(import.meta.env.VITE_ROOMS_WS_URL ?? '').trim();
  const base = configured || `${apiBaseUrl() || window.location.origin}/ws/rooms`;
  const url = new URL(`${base.replace(/\/$/, '')}/${encodeURIComponent(roomCode)}`);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  return url.toString();
}

export function segmentFromWire(value: unknown): Segment | null {
  if (typeof value !== 'object' || value === null) return null;
  const item = value as Record<string, unknown>;
  if (
    typeof item['segment_id'] !== 'string'
    || typeof item['speaker_label'] !== 'string'
    || typeof item['text_vi'] !== 'string'
    || typeof item['text_en'] !== 'string'
    || (item['spoken_language'] !== 'vi' && item['spoken_language'] !== 'en')
    || typeof item['timestamp_start'] !== 'number'
    || typeof item['timestamp_end'] !== 'number'
  ) return null;
  return {
    segmentId: item['segment_id'],
    speakerLabel: item['speaker_label'],
    textVi: item['text_vi'],
    textEn: item['text_en'],
    spokenLanguage: item['spoken_language'],
    isFinal: true,
    timestampStart: item['timestamp_start'],
    timestampEnd: item['timestamp_end'],
  };
}

function apiBaseUrl(): string {
  return String(import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/$/, '');
}

function requiredString(payload: Record<string, unknown>, key: string): string {
  const value = payload[key];
  if (typeof value !== 'string' || value.trim() === '') {
    throw new Error('The room service returned an invalid response.');
  }
  return value;
}

async function roomError(response: Response, fallback: string): Promise<string> {
  try {
    const payload = await response.json() as { detail?: unknown };
    return typeof payload.detail === 'string' ? payload.detail : fallback;
  } catch {
    return fallback;
  }
}
