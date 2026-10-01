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
  setMicrophoneStream: vi.fn<(stream: MediaStream | null) => Promise<void>>(),
  setMicrophoneGain: vi.fn(),
  sendAudioChunk: vi.fn(),
  startCapture: vi.fn<() => Promise<MediaStream>>(),
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
    microphoneGain: 100,
    setMicrophoneGain: mocks.setMicrophoneGain,
    inputLevel: 0,
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
    microphonePublished: mocks.capturing,
    error: null,
    start: vi.fn(),
    stop: mocks.stopScreenShare,
    stopAll: mocks.stopScreenShare,
    setMicrophoneStream: mocks.setMicrophoneStream,
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
    localStorage.clear();
    localStorage.clear();
    mocks.webSocketOptions = undefined as unknown as typeof mocks.webSocketOptions;
    mocks.wakeBackend.mockResolvedValue();
    mocks.waitForSignedInWake.mockResolvedValue();
    mocks.startCapture.mockResolvedValue({} as MediaStream);
    mocks.disconnectAndWait.mockResolvedValue();
    mocks.pauseSharedAudioCaptions.mockResolvedValue();
    mocks.resumeSharedAudioCaptions.mockResolvedValue();
    mocks.stopScreenShare.mockResolvedValue();
    mocks.setMicrophoneStream.mockResolvedValue();
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

    await waitFor(() => expect(mocks.waitForSignedInWake).toHaveBeenCalledTimes(2));
    expect(mocks.wakeBackend).not.toHaveBeenCalled();
    await waitFor(() => expect(mocks.connect).toHaveBeenCalledOnce());
    expect(mocks.startCapture).toHaveBeenCalledOnce();
  });

  it('holds usage and history requests until the signed-in wake completes', async () => {
    mocks.authConfigured = true;
    mocks.wakeConfigured = true;
    let finishWake!: () => void;
    mocks.waitForSignedInWake.mockImplementation(() => new Promise<void>((resolve) => { finishWake = resolve; }));
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ items: [], sessions_used: 0, limits: { max_sessions_per_week: 5, unlimited_session_duration: true }, quota_error: null }) });
    vi.stubGlobal('fetch', fetchMock);

    render(<DashboardPage />);
    expect(screen.getByText('Starting backend for usage and history...')).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
    await waitFor(() => expect(mocks.waitForSignedInWake).toHaveBeenCalledOnce());
    finishWake();
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/usage'))).toBe(true));
    expect(fetchMock.mock.calls.some(([url]) => String(url).includes('/api/transcripts'))).toBe(true);
  });

  it('offers a retry without mounting backend panels when wake fails', async () => {
    mocks.authConfigured = true;
    mocks.wakeConfigured = true;
    mocks.waitForSignedInWake.mockRejectedValueOnce(new Error('Backend unavailable'));
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        items: [], sessions_used: 0,
        limits: { max_sessions_per_week: 5, unlimited_session_duration: true },
        quota_error: null,
      }),
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<DashboardPage />);
    expect(await screen.findByText('Could not load usage and history while the backend is unavailable.')).toBeTruthy();
    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => expect(mocks.waitForSignedInWake).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
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
    mocks.startCapture.mockImplementation(async () => { mocks.capturing = true; return {} as MediaStream; });
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

    expect(screen.queryByText('Ready to listen')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Turn microphone on' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Turn microphone off' }));

    expect(screen.getByText('Room live')).toBeTruthy();
    expect(mocks.closeRoom).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Stop live' }));
    await waitFor(() => expect(mocks.closeRoom).toHaveBeenCalledOnce());
    expect(mocks.stopScreenShare).toHaveBeenCalledOnce();
    expect(await screen.findByText('Transcript saved')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Turn microphone on' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Start session' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss saved room' }));
    expect(screen.getByRole('button', { name: 'Create audience room' })).toBeTruthy();
  });

  it('switches captions from shared audio to the selected input and back', async () => {
    mocks.screenStatus = 'live';
    mocks.connect.mockResolvedValue();
    mocks.roomsEnabled = true;
    mocks.startCapture.mockImplementation(async () => { mocks.capturing = true; return {} as MediaStream; });
    mocks.stopCapture.mockImplementation(() => { mocks.capturing = false; });
    mocks.createRoom.mockResolvedValue({
      roomCode: 'ABC234', hostToken: 'host-token', title: 'LiveCap room',
      joinUrl: 'https://livecap.logantai.com/rooms/ABC234',
      status: 'live', mediaStatus: 'idle', expiresAt: '2026-10-11T00:00:00Z',
    });

    render(<DashboardPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Create audience room' }));
    await screen.findByText('Host preview');
    fireEvent.click(screen.getByRole('button', { name: 'Turn microphone on' }));
    await waitFor(() => expect(mocks.startCapture).toHaveBeenCalledOnce());
    expect(mocks.pauseSharedAudioCaptions).toHaveBeenCalledOnce();
    expect(mocks.pauseSharedAudioCaptions.mock.invocationCallOrder[0]).toBeLessThan(mocks.connect.mock.invocationCallOrder[0]);
    expect(mocks.setMicrophoneStream).toHaveBeenCalledWith(expect.anything());
    fireEvent.click(screen.getByRole('button', { name: 'Turn microphone off' }));
    await waitFor(() => expect(mocks.resumeSharedAudioCaptions).toHaveBeenCalledOnce());
    expect(mocks.disconnectAndWait.mock.invocationCallOrder[0]).toBeLessThan(mocks.resumeSharedAudioCaptions.mock.invocationCallOrder[0]);
  });

  it('resumes shared-audio captions even if microphone socket cleanup fails', async () => {
    mocks.screenStatus = 'live';
    mocks.roomsEnabled = true;
    mocks.startCapture.mockImplementation(async () => { mocks.capturing = true; return {} as MediaStream; });
    mocks.stopCapture.mockImplementation(() => { mocks.capturing = false; });
    mocks.createRoom.mockResolvedValue({
      roomCode: 'ABC234', hostToken: 'host-token', title: 'LiveCap room',
      joinUrl: 'https://livecap.logantai.com/rooms/ABC234', status: 'live',
      mediaStatus: 'idle', liveExpiresAt: '2099-01-01T00:00:00Z', expiresAt: '2099-01-15T00:00:00Z',
    });
    render(<DashboardPage />);
    fireEvent.click(screen.getByRole('button', { name: 'Create audience room' }));
    await screen.findByText('Host preview');
    fireEvent.click(screen.getByRole('button', { name: 'Turn microphone on' }));
    await waitFor(() => expect(mocks.startCapture).toHaveBeenCalledOnce());
    mocks.disconnectAndWait.mockRejectedValueOnce(new Error('Close timed out'));
    fireEvent.click(screen.getByRole('button', { name: 'Turn microphone off' }));
    await waitFor(() => expect(mocks.resumeSharedAudioCaptions).toHaveBeenCalledOnce());
  });

  it('restores the live host room after a page reload without starting capture automatically', async () => {
    mocks.roomsEnabled = true;
    localStorage.setItem('livecap.hosted-room.v1', JSON.stringify({
      owner: null,
      room: {
        roomCode: 'ABCDEF', hostToken: 'saved-host-token', title: 'Recovered room',
        joinUrl: 'https://livecap.logantai.com/rooms/ABCDEF', status: 'live',
        mediaStatus: 'live', createdAt: '2026-09-30T00:00:00Z',
        liveExpiresAt: '2099-01-01T00:00:00Z', expiresAt: '2099-01-15T00:00:00Z',
      },
    }));
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true, status: 200, json: async () => ({ status: 'live', media_status: 'idle' }),
    }));
    render(<DashboardPage />);
    expect(await screen.findByText('Recovered room')).toBeTruthy();
    expect(screen.getByRole('button', { name: 'Turn microphone on' })).toBeTruthy();
    expect(mocks.startCapture).not.toHaveBeenCalled();
  });
});
