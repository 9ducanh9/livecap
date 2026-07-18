import { useEffect, useState, type ReactNode } from 'react';
import { LogIn, LoaderCircle } from 'lucide-react';
import { beginSignIn, completeSignInFromRedirect, getAuthSession, isAuthConfigured } from '../services/authService';

export default function AuthGate({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<'checking' | 'anonymous' | 'signed-in'>(() => isAuthConfigured() ? 'checking' : 'signed-in');
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    if (!isAuthConfigured()) return;
    void (async () => {
      try { await completeSignInFromRedirect(); setStatus(getAuthSession() ? 'signed-in' : 'anonymous'); }
      catch (err) { setError(err instanceof Error ? err.message : 'Could not complete sign in.'); setStatus('anonymous'); }
    })();
  }, []);
  if (status === 'signed-in') return <>{children}</>;
  if (status === 'checking') return <div className="min-h-screen grid place-items-center bg-paper text-ink"><LoaderCircle className="h-5 w-5 animate-spin text-emerald-pro" /></div>;
  return <main className="min-h-screen grid place-items-center bg-paper px-6 text-ink"><section className="w-full max-w-md rounded-2xl border border-[#dce5f2] bg-white p-8 shadow-[0_16px_50px_rgba(16,34,71,0.07)]"><p className="font-instrument text-2xl font-bold">LiveCap workspace</p><p className="mt-3 text-sm leading-relaxed text-ink-muted">Sign in to protect your transcript history and return to previous exports.</p>{error && <p className="mt-4 text-sm text-crimson">{error}</p>}<button type="button" onClick={() => void beginSignIn()} className="mt-6 flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-ink text-sm font-bold text-white hover:bg-emerald-pro"><LogIn className="h-4 w-4" /> Sign in to continue</button></section></main>;
}
