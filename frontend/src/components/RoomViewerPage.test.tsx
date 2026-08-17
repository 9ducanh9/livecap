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

afterEach(() => {
  cleanup();
  roomFeed.value.status = 'live';
});

describe('RoomViewerPage', () => {
  it('shows a late-join snapshot and lets viewers choose one language', () => {
    render(
      <MemoryRouter initialEntries={['/rooms/ABC123']}>
        <Routes>
          <Route path="/rooms/:roomCode" element={<RoomViewerPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('Architecture review')).toBeTruthy();
    expect(screen.getByText('Chúng ta bắt đầu nhé.')).toBeTruthy();
    expect(screen.getByText('Let us begin.')).toBeTruthy();

    fireEvent.click(screen.getByRole('button', { name: 'Tiếng Việt' }));
    expect(screen.getByText('Chúng ta bắt đầu nhé.')).toBeTruthy();
    expect(screen.queryByText('Let us begin.')).toBeNull();
  });

  it('labels an ended room as a saved finalized transcript', () => {
    roomFeed.value.status = 'ended';
    render(
      <MemoryRouter initialEntries={['/rooms/TABKNF']}>
        <Routes>
          <Route path="/rooms/:roomCode" element={<RoomViewerPage />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText('Saved transcript')).toBeTruthy();
    expect(screen.getByText('This meeting has ended. You are viewing its finalized bilingual transcript.')).toBeTruthy();
    expect(screen.getByText('Finalized transcript')).toBeTruthy();
  });
});
