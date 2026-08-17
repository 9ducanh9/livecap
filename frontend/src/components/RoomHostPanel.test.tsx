import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import RoomHostPanel from './RoomHostPanel';

afterEach(cleanup);

describe('RoomHostPanel', () => {
  it('shows a scannable viewer QR code and lets the host hide it', () => {
    render(
      <RoomHostPanel
        room={{
          roomCode: 'ABC123',
          hostToken: 'host-token',
          joinUrl: 'http://127.0.0.1:5173/rooms/ABC123',
          title: 'Architecture review',
          status: 'live',
          createdAt: '2026-08-17T00:00:00Z',
          liveExpiresAt: '2026-08-17T04:00:00Z',
          expiresAt: '2026-08-31T00:00:00Z',
        }}
        isCreating={false}
        isCapturing={false}
        error={null}
        onCreate={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByRole('img', { name: 'Viewer room QR code' })).toBeTruthy();
    expect(screen.getByText('Scan to join live captions')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Hide QR code' }));
    expect(screen.queryByRole('img', { name: 'Viewer room QR code' })).toBeNull();
    expect(screen.getByRole('button', { name: 'Show QR code' })).toBeTruthy();
  });

  it('keeps the viewer link available after the meeting ends', () => {
    render(
      <RoomHostPanel
        room={{
          roomCode: 'TABKNF',
          hostToken: 'host-token',
          joinUrl: 'https://livecap.logantai.com/rooms/TABKNF',
          title: 'Saved meeting',
          status: 'ended',
          createdAt: '2026-08-17T00:00:00Z',
          liveExpiresAt: '2026-08-17T04:00:00Z',
          expiresAt: '2026-08-31T00:00:00Z',
        }}
        isCreating={false}
        isCapturing={false}
        error={null}
        onCreate={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByText('Transcript saved')).toBeTruthy();
    expect(screen.getByText('Scan to view saved captions')).toBeTruthy();
    expect(screen.getByText('TABKNF')).toBeTruthy();
  });
});
