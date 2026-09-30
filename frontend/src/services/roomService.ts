import type { Segment } from '../types';
import { authenticatedFetch, getAuthSession } from './authService';

export const HOSTED_ROOM_STORAGE_KEY = 'livecap.hosted-room.v1';

export interface HostedRoom {
  roomCode: string;
  hostToken: string;
  joinUrl: string;
  title: string;
  status: 'live' | 'ended';
  createdAt: string;
  liveExpiresAt: string;
  expiresAt: string;
  mediaStatus: 'idle' | 'live';
}

export interface RoomSnapshot {
  roomCode: string;
  title: string;
  status: 'live' | 'ended';
  viewerCount: number;
  sequence: number;
  segments: Segment[];
}

function currentOwner(): string | null {
  const token = getAuthSession()?.idToken;
  if (!token) return null;
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/'))) as { sub?: unknown };
    return typeof payload.sub === 'string' ? payload.sub : null;
  } catch { return null; }
}

export function rememberHostedRoom(room: HostedRoom): void {
  try {
    localStorage.setItem(HOSTED_ROOM_STORAGE_KEY, JSON.stringify({ owner: currentOwner(), room }));
  } catch { /* Private browsing may block persistent storage. */ }
}

export function forgetHostedRoom(): void {
  try { localStorage.removeItem(HOSTED_ROOM_STORAGE_KEY); } catch { /* Storage unavailable. */ }
}

export function hasSavedHostedRoom(): boolean {
  try { return localStorage.getItem(HOSTED_ROOM_STORAGE_KEY) !== null; } catch { return false; }
}

export async function restoreHostedRoom(): Promise<HostedRoom | null> {
  let saved: { owner: string | null; room: HostedRoom };
  try {
    const raw = localStorage.getItem(HOSTED_ROOM_STORAGE_KEY);
    if (!raw) return null;
    saved = JSON.parse(raw) as typeof saved;
    const room = saved.room;
    if (saved.owner !== currentOwner()
      || !room || !/^[A-Z]{6}$/.test(room.roomCode)
      || typeof room.hostToken !== 'string' || !room.hostToken
      || !Number.isFinite(Date.parse(room.liveExpiresAt))
      || Date.parse(room.liveExpiresAt) <= Date.now()) {
      forgetHostedRoom();
      return null;
    }
  } catch {
    forgetHostedRoom();
    return null;
  }
  const response = await authenticatedFetch(`${apiBaseUrl()}/api/rooms/${saved.room.roomCode}`);
  if (response.status === 404) { forgetHostedRoom(); return null; }
  if (!response.ok) throw new Error('Could not check the saved room.');
  const snapshot = await response.json() as Record<string, unknown>;
  if (snapshot['status'] !== 'live') { forgetHostedRoom(); return null; }
  return { ...saved.room, mediaStatus: snapshot['media_status'] === 'live' ? 'live' : 'idle' };
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
    mediaStatus: payload['media_status'] === 'live' ? 'live' : 'idle',
  };
}

export function isRoomScreenShareEnabled(): boolean {
  return String(import.meta.env.VITE_ENABLE_ROOM_SCREEN_SHARE ?? '').toLowerCase() === 'true';
}

export async function roomExists(roomCode: string): Promise<boolean> {
  const response = await fetch(`${apiBaseUrl()}/api/rooms/${encodeURIComponent(roomCode)}`);
  if (response.status === 404) return false;
  if (!response.ok) throw new Error(await roomError(response, 'Could not verify the room code.'));
  return true;
}

export async function createHostMediaToken(room: HostedRoom): Promise<string> {
  const response = await authenticatedFetch(
    `${apiBaseUrl()}/api/rooms/${encodeURIComponent(room.roomCode)}/media/host-token`,
    { method: 'POST', headers: { 'X-LiveCap-Room-Token': room.hostToken } },
  );
  if (!response.ok) throw new Error(await roomError(response, 'Could not start screen sharing.'));
  return requiredString(await response.json() as Record<string, unknown>, 'token');
}

export async function createViewerMediaToken(roomCode: string): Promise<string> {
  const response = await fetch(
    `${apiBaseUrl()}/api/rooms/${encodeURIComponent(roomCode)}/media/viewer-token`,
    { method: 'POST' },
  );
  if (!response.ok) throw new Error(await roomError(response, 'Could not join screen sharing.'));
  return requiredString(await response.json() as Record<string, unknown>, 'token');
}

export async function stopRoomMedia(room: HostedRoom): Promise<void> {
  const response = await authenticatedFetch(
    `${apiBaseUrl()}/api/rooms/${encodeURIComponent(room.roomCode)}/media/stop`,
    { method: 'POST', headers: { 'X-LiveCap-Room-Token': room.hostToken } },
  );
  if (!response.ok && response.status !== 404) {
    throw new Error(await roomError(response, 'Could not stop screen sharing.'));
  }
}

export async function closeSharedRoom(room: HostedRoom): Promise<void> {
  const response = await authenticatedFetch(
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

export function buildRoomWebSocketUrl(roomCode: string, hostToken?: string): string {
  const configured = String(import.meta.env.VITE_ROOMS_WS_URL ?? '').trim();
  const base = configured || `${apiBaseUrl() || window.location.origin}/ws/rooms`;
  const url = new URL(`${base.replace(/\/$/, '')}/${encodeURIComponent(roomCode)}`);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  if (hostToken) url.searchParams.set('host_token', hostToken);
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

export function partialFromWire(value: unknown): Segment | null {
  if (typeof value !== 'object' || value === null) return null;
  const item = value as Record<string, unknown>;
  if (
    typeof item['segment_id'] !== 'string'
    || typeof item['speaker_label'] !== 'string'
    || typeof item['text_vi'] !== 'string'
    || typeof item['text_en'] !== 'string'
    || (item['spoken_language'] !== 'vi' && item['spoken_language'] !== 'en')
    || item['is_final'] !== false
  ) return null;
  return {
    segmentId: item['segment_id'],
    speakerLabel: item['speaker_label'],
    textVi: item['text_vi'],
    textEn: item['text_en'],
    spokenLanguage: item['spoken_language'],
    isFinal: false,
    timestampStart: 0,
    timestampEnd: 0,
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
