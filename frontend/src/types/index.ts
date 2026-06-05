// Shared frontend types for LiveCap.
// Mirrors the backend WebSocket message contracts and frontend state model.

// ---------------------------------------------------------------------------
// Domain Types
// ---------------------------------------------------------------------------

export interface Segment {
  segmentId: string;
  speakerLabel: string;
  textVi: string;
  textEn: string;
  spokenLanguage: 'vi' | 'en';
  isFinal: boolean;
  timestampStart: number;
  timestampEnd: number;
}

export interface AppState {
  isCapturing: boolean;
  isConnected: boolean;
  sessionId: string | null;
  segments: Segment[];
  currentPartial: Segment | null;
  error: string | null;
}

export type SourceLanguageCode = 'vi-VN' | 'en-US';
export type TargetLanguageCode = 'en' | 'vi';

export interface LanguageMode {
  label: string;
  source: SourceLanguageCode;
  target: TargetLanguageCode;
}

// ---------------------------------------------------------------------------
// WebSocket Messages — Backend → Frontend (discriminated union)
// ---------------------------------------------------------------------------

export interface SessionStartMessage {
  type: 'session_start';
  session_id: string;
}

export interface PartialSegmentMessage {
  type: 'partial_segment';
  segment_id: string;
  speaker_label: string;
  text_vi: string;
  text_en: string;
  spoken_language: 'vi' | 'en';
  is_final: false;
}

export interface FinalizedSegmentMessage {
  type: 'finalized_segment';
  segment_id: string;
  speaker_label: string;
  text_vi: string;
  text_en: string;
  spoken_language: 'vi' | 'en';
  is_final: true;
  timestamp_start: number;
  timestamp_end: number;
}

export interface ErrorMessage {
  type: 'error';
  message: string;
  code: string;
}

export interface SessionEndMessage {
  type: 'session_end';
  session_id: string;
}

/** Union of all messages the backend can send to the frontend. */
export type ServerMessage =
  | SessionStartMessage
  | PartialSegmentMessage
  | FinalizedSegmentMessage
  | ErrorMessage
  | SessionEndMessage;

// ---------------------------------------------------------------------------
// WebSocket Messages — Frontend → Backend (discriminated union)
// ---------------------------------------------------------------------------

export interface StopMessage {
  type: 'stop';
}

/** Union of all JSON messages the frontend can send to the backend.
 *  Binary audio chunks (ArrayBuffer) are sent as raw binary frames, not
 *  covered by this union. */
export type ClientMessage = StopMessage;
