import { useEffect, useState, type ReactNode, type FormEvent } from 'react';
import { LoaderCircle, LogIn, UserPlus, Mail, Lock, ArrowLeft, AlertCircle, KeyRound, CheckCircle2 } from 'lucide-react';
import {
  CognitoUserPool,
  CognitoUser,
  AuthenticationDetails,
  CognitoUserAttribute,
} from 'amazon-cognito-identity-js';
import { beginSignIn, getAuthSession, isAuthConfigured, completeSignInFromRedirect, clearAuthSession, signOut } from '../services/authService';

// --- Cognito direct config ---
const POOL_ID = String(import.meta.env.VITE_COGNITO_USER_POOL_ID ?? '').trim();
const CLIENT_ID = String(import.meta.env.VITE_COGNITO_CLIENT_ID ?? '').trim();
const SESSION_KEY = 'livecap.auth.session';

function getUserPool() {
  return new CognitoUserPool({ UserPoolId: POOL_ID, ClientId: CLIENT_ID });
}

function storeTokens(result: { getAccessToken: () => { getJwtToken: () => string }; getIdToken: () => { getJwtToken: () => string; getExpiration: () => number }; getRefreshToken: () => { getToken: () => string } }) {
  const session = {
    accessToken: result.getAccessToken().getJwtToken(),
    idToken: result.getIdToken().getJwtToken(),
    refreshToken: result.getRefreshToken().getToken(),
    expiresAt: result.getIdToken().getExpiration() * 1000,
  };
  sessionStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

type AuthView = 'login' | 'register' | 'confirm' | 'forgot' | 'reset';

function AuthError({ message }: { message: string }) {
  return (
    <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-red-100 bg-red-50 px-4 py-3 text-sm text-crimson">
      <AlertCircle className="h-4 w-4 shrink-0 mt-0.5" />
      <span>{message}</span>
    </div>
  );
}

function sixDigitCode(value: string): string {
  return value.replace(/\D/g, '').slice(0, 6);
}

function cognitoErrorCode(error: unknown): string {
  if (typeof error !== 'object' || error === null) return '';
  const value = error as { code?: unknown; name?: unknown };
  if (typeof value.code === 'string') return value.code;
  return typeof value.name === 'string' ? value.name : '';
}

export default function AuthGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<'checking' | 'anonymous' | 'signed-in'>(() =>
    isAuthConfigured() ? 'checking' : 'signed-in'
  );

  useEffect(() => {
    if (!isAuthConfigured()) return;
    void (async () => {
      try {
        await completeSignInFromRedirect();
        setStatus(getAuthSession() ? 'signed-in' : 'anonymous');
      } catch {
        setStatus('anonymous');
      }
    })();
  }, []);

  if (status === 'signed-in') return <>{children}</>;
  if (status === 'checking') {
    return (
      <div className="min-h-screen grid place-items-center bg-paper text-ink">
        <LoaderCircle className="h-6 w-6 animate-spin text-emerald-pro" />
      </div>
    );
  }
  return <LoginScreen onSuccess={() => setStatus('signed-in')} />;
}

function LoginScreen({ onSuccess }: { onSuccess: () => void }) {
  const [view, setView] = useState<AuthView>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmCode, setConfirmCode] = useState('');
  const [resetCode, setResetCode] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [resetSent, setResetSent] = useState(false);
  const [resetCodeError, setResetCodeError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleLogin = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const user = new CognitoUser({ Username: email, Pool: getUserPool() });
      const authDetails = new AuthenticationDetails({ Username: email, Password: password });
      await new Promise<void>((resolve, reject) => {
        user.authenticateUser(authDetails, {
          onSuccess: (result) => { storeTokens(result); resolve(); },
          onFailure: (err) => reject(err),
          newPasswordRequired: () => reject(new Error('Password change required. Contact support.')),
        });
      });
      onSuccess();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Sign in failed.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const pool = getUserPool();
      const attrs = [new CognitoUserAttribute({ Name: 'email', Value: email })];
      await new Promise<void>((resolve, reject) => {
        pool.signUp(email, password, attrs, [], (err) => {
          if (err) reject(err); else resolve();
        });
      });
      setView('confirm');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Registration failed.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirm = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (confirmCode.length !== 6) {
      setError('Enter the 6-digit verification code from your email.');
      return;
    }
    setLoading(true);
    try {
      const user = new CognitoUser({ Username: email, Pool: getUserPool() });
      await new Promise<void>((resolve, reject) => {
        user.confirmRegistration(confirmCode, true, (err) => {
          if (err) reject(err); else resolve();
        });
      });
      // Auto-login after confirm
      const authDetails = new AuthenticationDetails({ Username: email, Password: password });
      await new Promise<void>((resolve, reject) => {
        user.authenticateUser(authDetails, {
          onSuccess: (result) => { storeTokens(result); resolve(); },
          onFailure: (err) => reject(err),
        });
      });
      onSuccess();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Confirmation failed.';
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  const handleForgotPassword = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setResetCodeError(null);
    setLoading(true);
    try {
      const normalizedEmail = email.trim().toLowerCase();
      const user = new CognitoUser({ Username: normalizedEmail, Pool: getUserPool() });
      await new Promise<void>((resolve, reject) => {
        user.forgotPassword({
          onSuccess: () => resolve(),
          onFailure: (err) => reject(err),
        });
      });
      setEmail(normalizedEmail);
      setResetCode('');
      setNewPassword('');
      setResetSent(true);
      setView('reset');
    } catch (err: unknown) {
      // Keep this response neutral so the password-reset form cannot be used
      // to discover whether an email address has a LiveCap account.
      const code = cognitoErrorCode(err);
      if (code === 'UserNotFoundException') {
        setResetCode('');
        setNewPassword('');
        setResetSent(true);
        setView('reset');
      } else {
        const msg = err instanceof Error ? err.message : 'Could not send a reset code.';
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleResetPassword = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setResetCodeError(null);
    if (resetCode.length !== 6) {
      setResetCodeError('Enter all 6 digits from the reset email.');
      return;
    }
    if (newPassword.length === 0) {
      setError('Enter a new password to continue.');
      return;
    }
    setLoading(true);
    try {
      const user = new CognitoUser({ Username: email, Pool: getUserPool() });
      await new Promise<void>((resolve, reject) => {
        user.confirmPassword(resetCode, newPassword, {
          onSuccess: () => resolve(),
          onFailure: (err) => reject(err),
        });
      });
      // Sign the user in with their new password right away.
      const authDetails = new AuthenticationDetails({ Username: email, Password: newPassword });
      await new Promise<void>((resolve, reject) => {
        user.authenticateUser(authDetails, {
          onSuccess: (result) => { storeTokens(result); resolve(); },
          onFailure: (err) => reject(err),
        });
      });
      onSuccess();
    } catch (err: unknown) {
      const code = cognitoErrorCode(err);
      if (code === 'CodeMismatchException') {
        setResetCodeError('This code is invalid. Check the latest email and try again.');
      } else if (code === 'ExpiredCodeException') {
        setResetCodeError('This code has expired. Request a new reset code and try again.');
      } else if (code === 'InvalidPasswordException') {
        setError('Use at least 12 characters with uppercase, lowercase, a number, and a symbol.');
      } else {
        const msg = err instanceof Error ? err.message : 'Could not reset the password.';
        setError(msg);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="min-h-screen flex items-center justify-center bg-paper px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <img src="/LiveCap.svg" alt="" className="h-12 w-12 rounded-xl" />
          <span className="font-instrument text-2xl font-bold tracking-[-0.08em] text-ink">LIVECAP</span>
        </div>

        {/* Card */}
        <div className="rounded-2xl border border-[#dce5f2] bg-white p-8 shadow-[0_16px_50px_rgba(16,34,71,0.07)]">
          {view === 'login' && (
            <>
              <h1 className="font-instrument text-xl font-bold text-ink">Welcome back</h1>
              <p className="mt-1 text-sm text-ink-muted">Sign in to your workspace</p>

              {error && <AuthError message={error} />}

              <form onSubmit={(e) => void handleLogin(e)} className="mt-6 space-y-4">
                <div>
                  <label className="text-xs font-semibold text-ink-muted uppercase tracking-wide">Email</label>
                  <div className="mt-1 flex items-center gap-2 rounded-xl border border-[#dce5f2] px-3 py-2.5 focus-within:border-emerald-pro focus-within:ring-1 focus-within:ring-emerald-pro/30">
                    <Mail className="h-4 w-4 text-ink-muted" />
                    <input
                      type="email" required autoComplete="email" placeholder="you@example.com"
                      value={email} onChange={(e) => setEmail(e.target.value)}
                      className="flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-muted/50"
                    />
                  </div>
                </div>
                <div>
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-ink-muted uppercase tracking-wide">Password</label>
                    <button
                      type="button"
                      onClick={() => { setError(null); setResetSent(false); setView('forgot'); }}
                      className="text-xs font-semibold text-emerald-pro hover:underline"
                    >
                      Forgot password?
                    </button>
                  </div>
                  <div className="mt-1 flex items-center gap-2 rounded-xl border border-[#dce5f2] px-3 py-2.5 focus-within:border-emerald-pro focus-within:ring-1 focus-within:ring-emerald-pro/30">
                    <Lock className="h-4 w-4 text-ink-muted" />
                    <input
                      type="password" required autoComplete="current-password" placeholder="••••••••••••"
                      value={password} onChange={(e) => setPassword(e.target.value)}
                      className="flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-muted/50"
                    />
                  </div>
                </div>
                <button
                  type="submit" disabled={loading}
                  className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-ink text-sm font-bold text-white transition-colors hover:bg-[#18376f] disabled:opacity-50"
                >
                  {loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <LogIn className="h-4 w-4" />}
                  Sign in
                </button>
              </form>

              {/* Divider */}
              <div className="my-6 flex items-center gap-3">
                <div className="flex-1 border-t border-[#dce5f2]" />
                <span className="text-xs text-ink-muted">or</span>
                <div className="flex-1 border-t border-[#dce5f2]" />
              </div>

              {/* Google */}
              <button
                type="button" onClick={() => { void beginSignIn('Google'); }}
                className="flex h-11 w-full items-center justify-center gap-3 rounded-xl border border-[#dce5f2] text-sm font-semibold text-ink transition-colors hover:bg-[#f7f8fc]"
              >
                <svg className="h-5 w-5" viewBox="0 0 24 24"><path d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" fill="#4285F4"/><path d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" fill="#34A853"/><path d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" fill="#FBBC05"/><path d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" fill="#EA4335"/></svg>
                Continue with Google
              </button>

              {/* Register link */}
              <p className="mt-6 text-center text-sm text-ink-muted">
                Don't have an account?{' '}
                <button type="button" onClick={() => { setError(null); setView('register'); }} className="font-semibold text-emerald-pro hover:underline">
                  Create one
                </button>
              </p>
            </>
          )}

          {view === 'register' && (
            <>
              <button type="button" onClick={() => { setError(null); setView('login'); }} className="flex items-center gap-1 text-sm text-ink-muted hover:text-ink mb-4">
                <ArrowLeft className="h-3.5 w-3.5" /> Back to sign in
              </button>
              <h1 className="font-instrument text-xl font-bold text-ink">Create account</h1>
              <p className="mt-1 text-sm text-ink-muted">Sign up with your email</p>

              {error && <AuthError message={error} />}

              <form onSubmit={(e) => void handleRegister(e)} className="mt-6 space-y-4">
                <div>
                  <label className="text-xs font-semibold text-ink-muted uppercase tracking-wide">Email</label>
                  <div className="mt-1 flex items-center gap-2 rounded-xl border border-[#dce5f2] px-3 py-2.5 focus-within:border-emerald-pro focus-within:ring-1 focus-within:ring-emerald-pro/30">
                    <Mail className="h-4 w-4 text-ink-muted" />
                    <input
                      type="email" required autoComplete="email" placeholder="you@example.com"
                      value={email} onChange={(e) => setEmail(e.target.value)}
                      className="flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-muted/50"
                    />
                  </div>
                </div>
                <div>
                  <label className="text-xs font-semibold text-ink-muted uppercase tracking-wide">Password</label>
                  <div className="mt-1 flex items-center gap-2 rounded-xl border border-[#dce5f2] px-3 py-2.5 focus-within:border-emerald-pro focus-within:ring-1 focus-within:ring-emerald-pro/30">
                    <Lock className="h-4 w-4 text-ink-muted" />
                    <input
                      type="password" required autoComplete="new-password" placeholder="Min 12 chars, mixed case + number + symbol"
                      value={password} onChange={(e) => setPassword(e.target.value)}
                      className="flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-muted/50"
                    />
                  </div>
                  <p className="mt-1.5 text-[11px] text-ink-muted">At least 12 characters, uppercase, lowercase, number, and symbol.</p>
                </div>
                <button
                  type="submit" disabled={loading}
                  className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-emerald-pro text-sm font-bold text-white transition-colors hover:bg-emerald-pro/90 disabled:opacity-50"
                >
                  {loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <UserPlus className="h-4 w-4" />}
                  Create account
                </button>
              </form>
            </>
          )}

          {view === 'confirm' && (
            <>
              <button type="button" onClick={() => { setError(null); setView('register'); }} className="flex items-center gap-1 text-sm text-ink-muted hover:text-ink mb-4">
                <ArrowLeft className="h-3.5 w-3.5" /> Back
              </button>
              <h1 className="font-instrument text-xl font-bold text-ink">Check your email</h1>
              <p className="mt-1 text-sm text-ink-muted">We sent a verification code to <strong className="text-ink">{email}</strong></p>

              {error && <AuthError message={error} />}

              <form onSubmit={(e) => void handleConfirm(e)} className="mt-6 space-y-4">
                <div>
                  <label className="text-xs font-semibold text-ink-muted uppercase tracking-wide">Verification code</label>
                  <div className="mt-1 flex items-center gap-2 rounded-xl border border-[#dce5f2] px-3 py-2.5 focus-within:border-emerald-pro focus-within:ring-1 focus-within:ring-emerald-pro/30">
                    <input
                      type="text" required inputMode="numeric" maxLength={6} autoComplete="one-time-code" placeholder="X X X X X X"
                      value={confirmCode} onChange={(e) => setConfirmCode(sixDigitCode(e.target.value))}
                      className="flex-1 bg-transparent text-center text-lg font-mono tracking-[0.3em] text-ink outline-none placeholder:text-ink-muted/50"
                    />
                  </div>
                </div>
                <button
                  type="submit" disabled={loading}
                  className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-ink text-sm font-bold text-white transition-colors hover:bg-[#18376f] disabled:opacity-50"
                >
                  {loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : null}
                  Verify & sign in
                </button>
              </form>
            </>
          )}

          {view === 'forgot' && (
            <>
              <button type="button" onClick={() => { setError(null); setView('login'); }} className="flex items-center gap-1 text-sm text-ink-muted hover:text-ink mb-4">
                <ArrowLeft className="h-3.5 w-3.5" /> Back to sign in
              </button>
              <h1 className="font-instrument text-xl font-bold text-ink">Reset your password</h1>
              <p className="mt-1 text-sm text-ink-muted">We'll email you a code to reset it</p>

              {error && <AuthError message={error} />}

              <form onSubmit={(e) => void handleForgotPassword(e)} className="mt-6 space-y-4">
                <div>
                  <label className="text-xs font-semibold text-ink-muted uppercase tracking-wide">Email</label>
                  <div className="mt-1 flex items-center gap-2 rounded-xl border border-[#dce5f2] px-3 py-2.5 focus-within:border-emerald-pro focus-within:ring-1 focus-within:ring-emerald-pro/30">
                    <Mail className="h-4 w-4 text-ink-muted" />
                    <input
                      type="email" required autoComplete="email" placeholder="you@example.com"
                      value={email} onChange={(e) => setEmail(e.target.value)}
                      className="flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-muted/50"
                    />
                  </div>
                </div>
                <button
                  type="submit" disabled={loading}
                  className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-ink text-sm font-bold text-white transition-colors hover:bg-[#18376f] disabled:opacity-50"
                >
                  {loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Mail className="h-4 w-4" />}
                  Send reset code
                </button>
              </form>
            </>
          )}

          {view === 'reset' && (
            <>
              <button type="button" onClick={() => { setError(null); setView('forgot'); }} className="flex items-center gap-1 text-sm text-ink-muted hover:text-ink mb-4">
                <ArrowLeft className="h-3.5 w-3.5" /> Back
              </button>
              <h1 className="font-instrument text-xl font-bold text-ink">Check your email</h1>
              <p className="mt-1 text-sm text-ink-muted">Enter the 6-digit code for <strong className="text-ink">{email}</strong></p>

              {resetSent && !error && (
                <div className="mt-4 flex items-start gap-2.5 rounded-xl border border-emerald-pro/20 bg-emerald-pro/5 px-4 py-3 text-sm text-emerald-pro">
                  <CheckCircle2 className="h-4 w-4 shrink-0 mt-0.5" />
                  <span>If an account exists for this email, we sent a reset code. Check your inbox and spam folder.</span>
                </div>
              )}
              {error && <AuthError message={error} />}

              <form onSubmit={(e) => void handleResetPassword(e)} className="mt-6 space-y-4">
                <div>
                  <label className="text-xs font-semibold text-ink-muted uppercase tracking-wide">Verification code</label>
                  <div className="mt-1 flex items-center gap-2 rounded-xl border border-[#dce5f2] px-3 py-2.5 focus-within:border-emerald-pro focus-within:ring-1 focus-within:ring-emerald-pro/30">
                    <KeyRound className="h-4 w-4 text-ink-muted" />
                    <input
                      type="text" required inputMode="numeric" maxLength={6} autoComplete="one-time-code" placeholder="X X X X X X"
                      value={resetCode}
                      onChange={(e) => {
                        setResetCode(sixDigitCode(e.target.value));
                        setResetCodeError(null);
                      }}
                      onBlur={() => {
                        if (resetCode.length > 0 && resetCode.length < 6) {
                          setResetCodeError('Enter all 6 digits from the reset email.');
                        }
                      }}
                      className="flex-1 bg-transparent text-center text-lg font-mono tracking-[0.3em] text-ink outline-none placeholder:text-ink-muted/50"
                    />
                  </div>
                  {resetCodeError && <p className="mt-1.5 text-[11px] text-crimson">{resetCodeError}</p>}
                </div>
                {resetCode.length === 6 && (
                  <div>
                    <label className="text-xs font-semibold text-ink-muted uppercase tracking-wide">New password</label>
                    <div className="mt-1 flex items-center gap-2 rounded-xl border border-[#dce5f2] px-3 py-2.5 focus-within:border-emerald-pro focus-within:ring-1 focus-within:ring-emerald-pro/30">
                      <Lock className="h-4 w-4 text-ink-muted" />
                      <input
                        type="password" required autoComplete="new-password" placeholder="Min 12 chars, mixed case + number + symbol"
                        value={newPassword} onChange={(e) => setNewPassword(e.target.value)}
                        className="flex-1 bg-transparent text-sm text-ink outline-none placeholder:text-ink-muted/50"
                      />
                    </div>
                    <p className="mt-1.5 text-[11px] text-ink-muted">At least 12 characters, uppercase, lowercase, number, and symbol.</p>
                  </div>
                )}
                <button
                  type="submit" disabled={loading || resetCode.length !== 6}
                  className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-emerald-pro text-sm font-bold text-white transition-colors hover:bg-emerald-pro/90 disabled:opacity-50"
                >
                  {loading ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <KeyRound className="h-4 w-4" />}
                  Reset password & sign in
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </main>
  );
}

export { signOut, clearAuthSession };
