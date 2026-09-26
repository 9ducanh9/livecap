import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import RoomViewerPage from './RoomViewerPage';

const roomFeed = vi.hoisted(() => ({
  value: {
    title: 'Architecture review',
    status: 'live' as 'live' | 'ended',
    viewerCount: 3,
    error: null as string | null,
    mediaStatus: 'idle' as 'idle' | 'live',
    segments: [{
      segmentId: 'segment-1',
      speakerLabel: 'Speaker 1',
      textVi: 'Chúng ta bắt đầu nhé.',
      textEn: 'Let us begin.',
      spokenLanguage: 'vi' as const,
      isFinal: true,
      timestampStart: 2,
      timestampEnd: 4,
    }],
  },
}));

vi.mock('../hooks/useRoomFeed', () => ({
  useRoomFeed: () => roomFeed.value,
}));

vi.mock('../services/wakeService', () => ({ wakeBackendIfConfigured: vi.fn().mockResolvedValue(undefined) }));
vi.mock('../services/roomService', async (importOriginal) => ({
  ...await importOriginal<typeof import('../services/roomService')>(),
  roomExists: vi.fn().mockResolvedValue(true),
}));

afterEach(() => {
  cleanup();
  roomFeed.value.status = 'live';
});

describe('RoomViewerPage', () => {
  it('shows a late-join snapshot and lets viewers choose one language', async () => {
    render(
      <MemoryRouter initialEntries={['/rooms/ABC234']}>
        <Routes>
          <Route path="/rooms/:roomCode" element={<RoomViewerPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Architecture review')).toBeTruthy();
    const subtitle = screen.getByText('Chúng ta bắt đầu nhé.');
    expect(subtitle.style.fontSize).toBe('11px');
    expect(subtitle.style.webkitTextStroke).toBe('0.5px rgba(0, 0, 0, 0.95)');
    expect(subtitle.parentElement?.className).not.toContain('bg-black');
    fireEvent.click(screen.getByRole('button', { name: 'VI + EN' }));
    expect(screen.getByText('Let us begin.')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Tiếng Việt' }));
    expect(screen.getByText('Chúng ta bắt đầu nhé.')).toBeTruthy();
    expect(screen.queryByText('Let us begin.')).toBeNull();
  });

  it('labels an ended room as a saved finalized transcript', async () => {
    roomFeed.value.status = 'ended';
    render(
      <MemoryRouter initialEntries={['/rooms/TABKNF']}>
        <Routes>
          <Route path="/rooms/:roomCode" element={<RoomViewerPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Saved transcript')).toBeTruthy();
    expect(screen.getByText('This meeting has ended. You are viewing its finalized bilingual transcript.')).toBeTruthy();
    fireEvent.click(screen.getByRole('button', { name: 'Transcript below' }));
    expect(screen.getByText('Finalized transcript')).toBeTruthy();
  });

  it('rejects malformed room codes before opening a room connection', () => {
    render(
      <MemoryRouter initialEntries={['/rooms/120323']}>
        <Routes>
          <Route path="/rooms/:roomCode" element={<RoomViewerPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByPlaceholderText('XXXXXX')).toBeTruthy();
    expect(screen.getByRole('alert').textContent).toContain('exactly six');
    expect(screen.queryByText('Architecture review')).toBeNull();
  });
});
