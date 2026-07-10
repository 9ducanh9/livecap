import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import type { Segment } from '../types/index';
import CaptionDisplay from './CaptionDisplay';

const partialSegment: Segment = {
  segmentId: 'partial-1',
  speakerLabel: 'Speaker 1',
  timestampStart: 0,
  timestampEnd: 1,
  spokenLanguage: 'vi',
  textVi: 'Xin chao',
  textEn: 'Hello',
  isFinal: false,
};

afterEach(() => cleanup());

describe('CaptionDisplay', () => {
  it('shows the current partial in the live caption stage', () => {
    render(
      <CaptionDisplay segments={[]} currentPartial={partialSegment} />,
    );

    expect(screen.getByLabelText('Live captions')).toBeTruthy();
    expect(screen.getByText('Xin chao')).toBeTruthy();
    expect(screen.getByText('Hello')).toBeTruthy();
    expect(screen.queryByText('CAPTURE_IN_PROGRESS')).toBeNull();
  });

  it('keeps finalized segments in the transcript history', () => {
    const finalSegment: Segment = {
      ...partialSegment,
      segmentId: 'final-1',
      isFinal: true,
      textVi: 'Day la dong da hoan tat',
      textEn: 'This is a finalized line',
    };

    render(
      <CaptionDisplay segments={[finalSegment]} currentPartial={null} />,
    );

    expect(screen.getByText('Day la dong da hoan tat')).toBeTruthy();
    expect(screen.getByText('This is a finalized line')).toBeTruthy();
  });

  it('joins finalized segments into one bilingual transcript flow', () => {
    const secondSegment: Segment = {
      ...partialSegment,
      segmentId: 'final-2',
      timestampStart: 2,
      isFinal: true,
      textVi: 'dong tiep theo',
      textEn: 'the next line',
    };

    render(
      <CaptionDisplay
        segments={[{ ...partialSegment, isFinal: true }, secondSegment]}
        currentPartial={null}
      />,
    );

    expect(screen.getByLabelText('Finalized transcript')).toBeTruthy();
    expect(screen.getByText('Xin chao dong tiep theo')).toBeTruthy();
    expect(screen.getByText('Hello the next line')).toBeTruthy();
  });

  it('shows a translation fallback while partial translation is unavailable', () => {
    render(
      <CaptionDisplay
        segments={[]}
        currentPartial={{ ...partialSegment, textEn: '' }}
        isCapturing
      />,
    );

    expect(screen.getByText('Xin chao')).toBeTruthy();
    expect(screen.getByText('Translating...')).toBeTruthy();
  });
});
