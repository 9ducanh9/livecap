import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { RoomFeedState } from '../hooks/useRoomFeed';
import RoomAudienceContent from './RoomAudienceContent';

vi.mock('./RoomScreenViewer', () => ({ default: () => <div>Screen preview</div> }));

afterEach(cleanup);

describe('room transcript', () => {
  it('updates the below-video transcript as partial captions arrive', () => {
    const feed: RoomFeedState = {
      title: 'Room', status: 'live', viewerCount: 1, segments: [],
      partial: {
        segmentId: 'live-1', speakerLabel: 'Speaker 1', textVi: 'Xin chào',
        textEn: 'Hello', spokenLanguage: 'vi', isFinal: false,
        timestampStart: 0, timestampEnd: 0,
      },
      error: null, mediaStatus: 'idle',
    };
    const view = render(<RoomAudienceContent roomCode="ABCDEF" feed={feed} />);
    expect(screen.getByText('Xin chào')).toBeTruthy();
    view.rerender(<RoomAudienceContent roomCode="ABCDEF" feed={{
      ...feed, partial: { ...feed.partial!, textVi: 'Xin chào mọi người' },
    }} />);
    expect(screen.getByText('Xin chào mọi người')).toBeTruthy();
    expect(screen.queryByText('Xin chào')).toBeNull();
  });
});
