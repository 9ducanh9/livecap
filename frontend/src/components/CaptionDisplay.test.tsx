import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
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

describe('CaptionDisplay', () => {
  it('shows the current partial as an in-progress capture', () => {
    render(
      <CaptionDisplay segments={[]} currentPartial={partialSegment} />,
    );

    expect(screen.getByText('Xin chao')).toBeTruthy();
    expect(screen.getByText('CAPTURE_IN_PROGRESS')).toBeTruthy();
  });
});
