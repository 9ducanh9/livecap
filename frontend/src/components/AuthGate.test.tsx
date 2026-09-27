import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import AuthGate from './AuthGate';

const mocks = vi.hoisted(() => ({
  completeSignIn: vi.fn<() => Promise<boolean>>(),
  getAuthSession: vi.fn(),
  beginWake: vi.fn<() => Promise<void>>(),
}));

vi.mock('../services/authService', () => ({
  beginSignIn: vi.fn(),
  getAuthSession: mocks.getAuthSession,
  isAuthConfigured: () => true,
  completeSignInFromRedirect: mocks.completeSignIn,
  clearAuthSession: vi.fn(),
  signOut: vi.fn(),
}));

vi.mock('../services/wakeService', () => ({
  beginBackendWakeAfterSignIn: mocks.beginWake,
}));

describe('AuthGate backend warmup', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.completeSignIn.mockResolvedValue(true);
    mocks.getAuthSession.mockReturnValue({
      accessToken: 'access-token',
      idToken: 'id-token',
      expiresAt: Date.now() + 60_000,
    });
    mocks.beginWake.mockImplementation(() => new Promise<void>(() => undefined));
  });

  afterEach(() => cleanup());

  it('starts backend wake immediately after a successful authenticated entry without blocking the app', async () => {
    render(<AuthGate><div>workspace ready</div></AuthGate>);

    expect(await screen.findByText('workspace ready')).toBeTruthy();
    await waitFor(() => expect(mocks.beginWake).toHaveBeenCalledOnce());
  });
});
