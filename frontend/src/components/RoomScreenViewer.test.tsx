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

  it('shows revisable speech immediately and lets it expire', () => {
    vi.useFakeTimers();
    const partial = { ...first, segmentId: 'speaking', textVi: 'Tôi đang nói', isFinal: false };
    const { rerender } = render(
      <RoomScreenViewer roomCode="ABCDEF" active={false} subtitleSegments={[]} subtitlePartial={partial} subtitleLanguage="vi" />,
    );
    expect(screen.getByText('Tôi đang nói').getAttribute('style')).toContain('1.25px');
    rerender(
      <RoomScreenViewer roomCode="ABCDEF" active={false} subtitleSegments={[]} subtitlePartial={{ ...partial, textVi: 'Tôi đang nói tiếp' }} subtitleLanguage="vi" />,
    );
    expect(screen.getByText('Tôi đang nói tiếp')).toBeTruthy();
    act(() => vi.advanceTimersByTime(1_800));
    expect(screen.queryByText('Tôi đang nói tiếp')).toBeNull();
  });

  it('drops stale overlay phrases while keeping the latest ones', () => {
    vi.useFakeTimers();
    const { rerender } = render(
      <RoomScreenViewer roomCode="ABCDEF" active={false} subtitleSegments={[{ ...first, textVi: 'Old phrase.' }]} subtitleLanguage="vi" />,
    );
    const incoming = ['First.', 'Second.', 'Third.', 'Latest.'].map((textVi, index) => ({
      ...first, segmentId: `new-${index}`, textVi,
    }));
    rerender(
      <RoomScreenViewer roomCode="ABCDEF" active={false} subtitleSegments={[{ ...first, textVi: 'Old phrase.' }, ...incoming]} subtitleLanguage="vi" />,
    );
    expect(screen.queryByText('Old phrase.')).toBeNull();
    expect(screen.getByText('Second.')).toBeTruthy();
    act(() => vi.advanceTimersByTime(1_300));
    expect(screen.getByText('Third.')).toBeTruthy();
    act(() => vi.advanceTimersByTime(1_300));
    expect(screen.getByText('Latest.')).toBeTruthy();
  });
});
