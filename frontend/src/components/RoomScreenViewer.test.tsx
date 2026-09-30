import { act, cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Segment } from '../types';
import RoomScreenViewer from './RoomScreenViewer';

const first: Segment = {
  segmentId: 'first', speakerLabel: 'Speaker 1', textVi: 'Xin chào. Hôm nay tốt.',
  textEn: 'Hello. Today is good.', spokenLanguage: 'vi', isFinal: true,
  timestampStart: 0, timestampEnd: 2,
};
const second: Segment = {
  ...first, segmentId: 'second', textVi: 'Ngoài ra nó nên tiếp tục.',
  textEn: 'It should also continue.', timestampStart: 2, timestampEnd: 4,
};

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe('RoomScreenViewer subtitles', () => {
  it('replaces each one-line phrase in order without joining adjacent sentences', () => {
    vi.useFakeTimers();
    const { rerender } = render(
      <RoomScreenViewer roomCode="ABCDEF" active={false} subtitleSegments={[first]} subtitleLanguage="vi" />,
    );
    expect(screen.getByText('Xin chào.').className).toContain('whitespace-nowrap');
    expect(screen.queryByText('Hôm nay tốt.')).toBeNull();

    rerender(<RoomScreenViewer roomCode="ABCDEF" active={false} subtitleSegments={[first, second]} subtitleLanguage="vi" />);
    act(() => vi.advanceTimersByTime(1_300));
    expect(screen.getByText('Hôm nay tốt.')).toBeTruthy();
    expect(screen.queryByText('Ngoài ra nó nên tiếp tục.')).toBeNull();

    act(() => vi.advanceTimersByTime(1_300));
    expect(screen.getByText('Ngoài ra nó nên tiếp tục.')).toBeTruthy();
    expect(screen.queryByText('Hôm nay tốt.')).toBeNull();
  });

  it('advances through repeated identical phrases and then clears the overlay', () => {
    vi.useFakeTimers();
    render(
      <RoomScreenViewer roomCode="ABCDEF" active={false} subtitleSegments={[{
        ...first, textEn: 'Oh no. Oh no.',
      }]} subtitleLanguage="en" />,
    );
    expect(screen.getByText('Oh no.')).toBeTruthy();
    act(() => vi.advanceTimersByTime(1_300));
    act(() => vi.advanceTimersByTime(1_300));
    expect(screen.queryByText('Oh no.')).toBeNull();
  });

  it('does not replay an archived snapshot when a viewer joins late', () => {
    vi.useFakeTimers();
    const { rerender } = render(
      <RoomScreenViewer roomCode="ABCDEF" active={false} subtitleSegments={[]} subtitleLanguage="vi" />,
    );
    rerender(<RoomScreenViewer roomCode="ABCDEF" active={false} subtitleSegments={[first, second]} subtitleLanguage="vi" />);
    expect(screen.getByText('Ngoài ra nó nên tiếp tục.')).toBeTruthy();
    expect(screen.queryByText('Xin chào.')).toBeNull();
  });
});
