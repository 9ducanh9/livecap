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
}));

vi.mock('../hooks/useWebSocket', () => ({
  useWebSocket: () => ({
    isConnectionLost: false,
    connectionStatus: 'idle',
    connect: mocks.connect,
    disconnect: mocks.disconnect,
    sendAudioChunk: mocks.sendAudioChunk,
  }),
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
  isWakeBackendConfigured: () => false,
  isBackendWakeError: () => false,
  wakeBackendIfConfigured: mocks.wakeBackend,
}));

describe('DashboardPage start flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.wakeBackend.mockResolvedValue();
    mocks.startCapture.mockResolvedValue();
  });

  afterEach(() => {
    cleanup();
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
    fireEvent.click(screen.getByRole('button', { name: 'START STREAM' }));

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
    fireEvent.click(screen.getByRole('button', { name: 'START STREAM' }));

    expect(
      await screen.findByText(
        'Unable to connect to the backend stream. Please try again.'
      )
    ).toBeTruthy();
    expect(mocks.startCapture).not.toHaveBeenCalled();
    expect(mocks.disconnect).toHaveBeenCalledOnce();
  });
});
