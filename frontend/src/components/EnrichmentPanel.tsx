import { useCallback, useRef, useState } from 'react';
import { Volume2, Square, Activity, AlertCircle, Hash } from 'lucide-react';
import {
  analyzeText,
  isAnalysisEnabled,
  isTtsEnabled,
  synthesizeSpeech,
  type AnalyzeResult,
} from '../services/enrichmentService';

interface EnrichmentPanelProps {
  /** Concatenated English transcript text to read / analyze. */
  englishText: string;
}

/**
 * Optional English-only enrichment (A2 Polly TTS + A3 Comprehend analysis).
 * Renders only when at least one feature flag is on and there is text.
 */
export default function EnrichmentPanel({ englishText }: EnrichmentPanelProps) {
  const ttsOn = isTtsEnabled();
  const analysisOn = isAnalysisEnabled();
  const text = englishText.trim();

  if ((!ttsOn && !analysisOn) || text === '') return null;

  return (
    <div className="border-t border-[#dce5f2]">
      <div className="px-6 py-5 border-b border-[#dce5f2]">
        <p className="text-sm font-bold text-ink">Audio &amp; insights</p>
        <p className="mt-1 text-xs text-ink-muted">English translation add-ons.</p>
      </div>
      <div className="px-6 py-5 space-y-4">
        {ttsOn && <PlayControl text={text} />}
        {analysisOn && <AnalyzeControl text={text} />}
      </div>
    </div>
  );
}

function PlayControl({ text }: { text: string }) {
  const [status, setStatus] = useState<'idle' | 'loading' | 'playing' | 'error'>('idle');
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);

  const cleanup = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    cleanup();
    setStatus('idle');
  }, [cleanup]);

  const play = useCallback(async () => {
    cleanup();
    setStatus('loading');
    try {
      const blob = await synthesizeSpeech(text);
      const url = URL.createObjectURL(blob);
      urlRef.current = url;
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => stop();
      audio.onerror = () => setStatus('error');
      await audio.play();
      setStatus('playing');
    } catch {
      cleanup();
      setStatus('error');
    }
  }, [cleanup, stop, text]);

  return (
    <div className="space-y-1.5">
      <button
        type="button"
        onClick={status === 'playing' ? stop : play}
        disabled={status === 'loading'}
        className="w-full h-11 rounded-xl border border-ink/15 text-sm font-bold text-ink/70 hover:border-emerald-pro/50 hover:text-emerald-pro hover:bg-emerald-pro/3 transition-all disabled:opacity-40 flex items-center justify-center gap-2"
      >
        {status === 'playing' ? (
          <>
            <Square className="w-3.5 h-3.5" /> Stop
          </>
        ) : status === 'loading' ? (
          <>
            <span className="w-3 h-px bg-ink/30 animate-[loading_1.2s_infinite_linear]" /> Preparing audio...
          </>
        ) : (
          <>
            <Volume2 className="w-3.5 h-3.5" /> Play English
          </>
        )}
      </button>
      {status === 'error' && (
        <p className="text-[10px] text-crimson font-mono">Text-to-speech unavailable.</p>
      )}
    </div>
  );
}

function AnalyzeControl({ text }: { text: string }) {
  const [status, setStatus] = useState<'idle' | 'loading' | 'done' | 'error'>('idle');
  const [result, setResult] = useState<AnalyzeResult | null>(null);

  const run = useCallback(async () => {
    setStatus('loading');
    try {
      setResult(await analyzeText(text));
      setStatus('done');
    } catch {
      setStatus('error');
    }
  }, [text]);

  return (
    <div className="space-y-3">
      <button
        type="button"
        onClick={run}
        disabled={status === 'loading'}
        className="w-full h-11 rounded-xl border border-ink/15 text-sm font-bold text-ink/70 hover:border-emerald-pro/50 hover:text-emerald-pro hover:bg-emerald-pro/3 transition-all disabled:opacity-40 flex items-center justify-center gap-2"
      >
        <Activity className="w-3.5 h-3.5" />
        {status === 'loading' ? 'Analyzing...' : 'Analyze sentiment'}
      </button>

      {status === 'error' && (
        <div className="flex items-center gap-2 text-crimson">
          <AlertCircle className="w-3 h-3" />
          <p className="text-[10px] font-mono">Analysis unavailable.</p>
        </div>
      )}

      {status === 'done' && result && (
        <div className="rounded-xl border border-emerald-pro/20 bg-emerald-pro/5 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-ink/45">Sentiment</span>
            <span className="rounded-full border border-emerald-pro/25 bg-white px-2.5 py-0.5 text-xs font-bold text-emerald-pro">
              {result.sentiment || '—'}
            </span>
          </div>
          {result.key_phrases.length > 0 && (
            <div>
              <div className="flex items-center gap-1.5">
                <Hash className="w-3.5 h-3.5 text-emerald-pro" />
                <span className="text-[10px] font-bold uppercase tracking-[0.16em] text-ink/45">Key phrases</span>
              </div>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {result.key_phrases.slice(0, 20).map((phrase, i) => (
                  <span
                    key={`${phrase}-${i}`}
                    className="rounded-full border border-ink/10 bg-white px-2.5 py-1 text-xs font-medium text-ink/70"
                  >
                    {phrase}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
