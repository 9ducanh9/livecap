import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import DashboardPage from './DashboardPage';

const mocks = vi.hoisted(() => ({
  connect: vi.fn<() => Promise<void>>(),
  disconnect: vi.fn(),
  sendAudioChunk: vi.fn(),
  startCapture: vi.fn<() => Promise<void>>(),
  stopCapture: vi.fn(),
  wakeBackend: vi.fn<() => Promise<void>>(),
  wakeConfigured: false,
  webSocketOptions: undefined as unknown as {
    onSessionStart: (sessionId: string, isReconnect: boolean) => void;
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
      sendAudioChunk: mocks.sendAudioChunk,
    };
  },
}));

vi.mock('../hooks/useAudioCapture', () => ({
  useAudioCapture: () => ({
    isCapturing: false,
    permissionDenied: false,
    audioInputDevices: [],
    selectedDeviceId: '',
    setSelectedDeviceId: vi.fn(),
    refreshAudioInputDevices: vi.fn(),
    startCapture: mocks.startCapture,
    stopCapture: mocks.stopCapture,
  }),
}));

vi.mock('../services/wakeService', () => ({
  isWakeBackendConfigured: () => mocks.wakeConfigured,
  isBackendWakeError: () => false,
  wakeBackendIfConfigured: mocks.wakeBackend,
}));

describe('DashboardPage start flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.wakeBackend.mockResolvedValue();
    mocks.startCapture.mockResolvedValue();
    mocks.wakeConfigured = false;
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
    expect(mocks.disconnect).toHaveBeenCalledOnce();
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

  it('requests AI meeting notes only after the user chooses to create them', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        summary_en: 'Launch planning is underway.', summary_vi: 'Dang lap ke hoach ra mat.',
        key_points: [], decisions: [], action_items: [], topics: [], keywords: [],
        insights: [], glossary: [], follow_up_questions: [],
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    render(<DashboardPage />);
    act(() => {
      mocks.webSocketOptions.onSessionStart('session-1', false);
      for (let index = 0; index < 3; index += 1) {
        mocks.webSocketOptions.onFinalizedSegment({
          segmentId: `segment-${index}`, speakerLabel: 'Speaker 1',
          textVi: 'Xin chao', textEn: 'Hello', spokenLanguage: 'vi',
          isFinal: true, timestampStart: index, timestampEnd: index + 1,
        });
      }
      mocks.webSocketOptions.onSessionEnd();
    });

    expect(fetchMock).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Create meeting notes' }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    expect(fetchMock.mock.calls[0][0]).toContain('/api/sessions/session-1/summary');
    expect(screen.getByText('AI meeting summary')).toBeTruthy();
  });
});
