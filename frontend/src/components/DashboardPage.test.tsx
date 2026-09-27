import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import DashboardPage from './DashboardPage';

const mocks = vi.hoisted(() => ({
  connect: vi.fn<() => Promise<void>>(),
  disconnect: vi.fn(),
  disconnectAndWait: vi.fn<() => Promise<void>>(),
  pauseSharedAudioCaptions: vi.fn<() => Promise<void>>(),
  resumeSharedAudioCaptions: vi.fn<() => Promise<void>>(),
  stopScreenShare: vi.fn<() => Promise<void>>(),
  sendAudioChunk: vi.fn(),
  startCapture: vi.fn<() => Promise<void>>(),
  stopCapture: vi.fn(),
  wakeBackend: vi.fn<() => Promise<void>>(),
  waitForSignedInWake: vi.fn<() => Promise<void>>(),
  wakeConfigured: false,
  authConfigured: false,
  capturing: false,
  roomsEnabled: false,
  screenStatus: 'idle' as 'idle' | 'live',
  createRoom: vi.fn(),
  closeRoom: vi.fn(),
  webSocketOptions: undefined as unknown as {
    onSessionStart?: (sessionId: string, isReconnect: boolean) => void;
    onFinalizedSegment: (segment: Record<string, unknown>) => void;
    onSessionEnd: () => void;
  },
}));

vi.mock('../hooks/useWebSocket', () => ({
  useWebSocket: (options: typeof mocks.webSocketOptions) => {
    mocks.webSocketOptions = options;
    return {
      isConnectionLost: false,
      connectionStatus: 'idle',
      connect: mocks.connect,
      disconnect: mocks.disconnect,
      disconnectAndWait: mocks.disconnectAndWait,
      sendAudioChunk: mocks.sendAudioChunk,
    };
  },
}));

vi.mock('../hooks/useAudioCapture', () => ({
  useAudioCapture: () => ({
    isCapturing: mocks.capturing,
    permissionDenied: false,
    audioInputDevices: [],
    selectedDeviceId: '',
    setSelectedDeviceId: vi.fn(),
    refreshAudioInputDevices: vi.fn(),
    startCapture: mocks.startCapture,
    stopCapture: mocks.stopCapture,
  }),
}));

vi.mock('../hooks/useRoomScreenShare', () => ({
  useRoomScreenShare: () => ({
    status: mocks.screenStatus,
    audioCaptionsActive: false,
    error: null,
    start: vi.fn(),
    stop: mocks.stopScreenShare,
    pauseSharedAudioCaptions: mocks.pauseSharedAudioCaptions,
    resumeSharedAudioCaptions: mocks.resumeSharedAudioCaptions,
  }),
}));

vi.mock('../hooks/useRoomFeed', () => ({
  useRoomFeed: () => ({
    title: 'LiveCap room', status: 'live', viewerCount: 0,
    segments: [], error: null, mediaStatus: 'idle',
  }),
}));

vi.mock('../services/wakeService', () => ({
  isWakeBackendConfigured: () => mocks.wakeConfigured,
  isBackendWakeError: () => false,
  waitForBackendWakeAfterSignIn: mocks.waitForSignedInWake,
  wakeBackendIfConfigured: mocks.wakeBackend,
}));

vi.mock('../services/authService', async (importOriginal) => ({
  ...await importOriginal<typeof import('../services/authService')>(),
  isAuthConfigured: () => mocks.authConfigured,
  isAdminUser: () => false,
}));

vi.mock('../services/roomService', async (importOriginal) => ({
  ...await importOriginal<typeof import('../services/roomService')>(),
  isSharedRoomsEnabled: () => mocks.roomsEnabled,
  isRoomScreenShareEnabled: () => false,
  createSharedRoom: mocks.createRoom,
  closeSharedRoom: mocks.closeRoom,
}));

describe('DashboardPage start flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.webSocketOptions = undefined as unknown as typeof mocks.webSocketOptions;
    mocks.wakeBackend.mockResolvedValue();
    mocks.waitForSignedInWake.mockResolvedValue();
    mocks.startCapture.mockResolvedValue();
    mocks.disconnectAndWait.mockResolvedValue();
    mocks.pauseSharedAudioCaptions.mockResolvedValue();
    mocks.resumeSharedAudioCaptions.mockResolvedValue();
    mocks.stopScreenShare.mockResolvedValue();
    mocks.wakeConfigured = false;
    mocks.authConfigured = false;
    mocks.capturing = false;
    mocks.roomsEnabled = false;
    mocks.screenStatus = 'idle';
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('waits for the WebSocket before starting microphone capture', async () => {
    let resolveConnection!: () => void;
    mocks.connect.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          resolveConnection = resolve;
        })
    );

    render(<DashboardPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Start session' }));

    await waitFor(() => expect(mocks.connect).toHaveBeenCalledOnce());
    expect(mocks.startCapture).not.toHaveBeenCalled();

    await act(async () => {
      resolveConnection();
    });

    await waitFor(() => expect(mocks.startCapture).toHaveBeenCalledOnce());
  });

  it('does not start capture when the WebSocket connection fails', async () => {
    mocks.connect.mockRejectedValue(new Error('connection refused'));

    render(<DashboardPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Start session' }));

    expect(
      await screen.findByText(
        'Unable to connect to the backend stream. Please try again.'
      )
    ).toBeTruthy();
    expect(mocks.startCapture).not.toHaveBeenCalled();
    expect(mocks.disconnectAndWait).toHaveBeenCalledOnce();
  });

  it('explains the expected cold start while the backend is waking', async () => {
    mocks.wakeConfigured = true;
    mocks.wakeBackend.mockImplementation(() => new Promise<void>(() => undefined));

    render(<DashboardPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Start session' }));

    expect(
      await screen.findByText(
        'The backend is waking from idle. This usually takes 30-60 seconds; temporary 503 responses are expected.'
      )
    ).toBeTruthy();
    expect(
      (screen.getByRole('button', { name: 'Starting backend' }) as HTMLButtonElement)
        .disabled
    ).toBe(true);
    expect(mocks.connect).not.toHaveBeenCalled();
    expect(mocks.startCapture).not.toHaveBeenCalled();
  });

  it('waits for the sign-in wake instead of posting wake again in authenticated mode', async () => {
    mocks.authConfigured = true;
    mocks.wakeConfigured = true;
    mocks.connect.mockResolvedValue();

    render(<DashboardPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Start session' }));

    await waitFor(() => expect(mocks.waitForSignedInWake).toHaveBeenCalledOnce());
    expect(mocks.wakeBackend).not.toHaveBeenCalled();
    await waitFor(() => expect(mocks.connect).toHaveBeenCalledOnce());
    expect(mocks.startCapture).toHaveBeenCalledOnce();
  });

  it('requests AI meeting notes only after the user chooses to create them', async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/usage')) {
        return {
          ok: true,
          json: async () => ({
            sessions_used: 0, quota_error: null,
            limits: {
              max_sessions_per_week: 5, unlimited_session_duration: true,
            },
          }),
        };
      }
      if (url.includes('/api/transcripts')) {
        return { ok: true, json: async () => [] };
      }
      return {
        ok: true,
        json: async () => ({
          summary_en: 'Launch planning is underway.', summary_vi: 'Dang lap ke hoach ra mat.',
          key_points: [], decisions: [], action_items: [], topics: [], keywords: [],
          insights: [], glossary: [], follow_up_questions: [],
        }),
      };
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<DashboardPage />);
    await waitFor(() => expect(mocks.webSocketOptions.onSessionStart).toBeTypeOf('function'));
    act(() => {
      mocks.webSocketOptions.onSessionStart?.('session-1', false);
      for (let index = 0; index < 3; index += 1) {
        mocks.webSocketOptions.onFinalizedSegment({
          segmentId: `segment-${index}`, speakerLabel: 'Speaker 1',
          textVi: 'Xin chao', textEn: 'Hello', spokenLanguage: 'vi',
          isFinal: true, timestampStart: index, timestampEnd: index + 1,
        });
      }
      mocks.webSocketOptions.onSessionEnd();
    });

    expect(
      fetchMock.mock.calls.some(([input]) => String(input).includes('/summary'))
    ).toBe(false);
    fireEvent.click(screen.getByRole('button', { name: 'Create meeting notes' }));

    await waitFor(() => expect(
      fetchMock.mock.calls.some(([input]) => String(input).includes('/api/sessions/session-1/summary'))
    ).toBe(true));
    expect(screen.getByText('AI meeting summary')).toBeTruthy();
  });

  it('keeps a room live when microphone capture stops', async () => {
    mocks.roomsEnabled = true;
    mocks.connect.mockResolvedValue();
    mocks.startCapture.mockImplementation(async () => { mocks.capturing = true; });
    mocks.stopCapture.mockImplementation(() => { mocks.capturing = false; });
    mocks.createRoom.mockResolvedValue({
      roomCode: 'ABC234', hostToken: 'host-token',
      joinUrl: 'https://livecap.logantai.com/rooms/ABC234',
      title: 'LiveCap room', status: 'live', mediaStatus: 'idle',
      createdAt: '2026-09-27T00:00:00Z', liveExpiresAt: '2026-09-27T04:00:00Z',
      expiresAt: '2026-10-11T00:00:00Z',
    });
    mocks.closeRoom.mockResolvedValue(undefined);

    render(<DashboardPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Create audience room' }));
    expect(await screen.findByText('Room live')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Start session' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Stop session' }));

    expect(screen.getByText('Room live')).toBeTruthy();
    expect(mocks.closeRoom).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Stop live' }));
    await waitFor(() => expect(mocks.closeRoom).toHaveBeenCalledOnce());
    expect(mocks.stopScreenShare).toHaveBeenCalledOnce();
    expect(await screen.findByText('Transcript saved')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss saved room' }));
    expect(screen.getByRole('button', { name: 'Create audience room' })).toBeTruthy();
  });

  it('switches captions from shared audio to the selected input and back', async () => {
    mocks.screenStatus = 'live';
    mocks.connect.mockResolvedValue();
    mocks.roomsEnabled = true;
    mocks.startCapture.mockImplementation(async () => { mocks.capturing = true; });
    mocks.stopCapture.mockImplementation(() => { mocks.capturing = false; });
    mocks.createRoom.mockResolvedValue({
      roomCode: 'ABC234', hostToken: 'host-token', title: 'LiveCap room',
      joinUrl: 'https://livecap.logantai.com/rooms/ABC234',
      status: 'live', mediaStatus: 'idle', expiresAt: '2026-10-11T00:00:00Z',
    });

    render(<DashboardPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Create audience room' }));
    await screen.findByText('Host preview');
    fireEvent.click(screen.getByRole('button', { name: 'Start session' }));
    await waitFor(() => expect(mocks.startCapture).toHaveBeenCalledOnce());
    expect(mocks.pauseSharedAudioCaptions).toHaveBeenCalledOnce();
    expect(mocks.pauseSharedAudioCaptions.mock.invocationCallOrder[0]).toBeLessThan(mocks.connect.mock.invocationCallOrder[0]);
    fireEvent.click(screen.getByRole('button', { name: 'Stop session' }));
    await waitFor(() => expect(mocks.resumeSharedAudioCaptions).toHaveBeenCalledOnce());
    expect(mocks.disconnectAndWait.mock.invocationCallOrder[0]).toBeLessThan(mocks.resumeSharedAudioCaptions.mock.invocationCallOrder[0]);
  });
});
