import { useState } from 'react';
import { Check, Copy, Link2, LoaderCircle, QrCode, Radio, Users, X } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import type { HostedRoom } from '../services/roomService';

interface RoomHostPanelProps {
  room: HostedRoom | null;
  isCreating: boolean;
  isCapturing: boolean;
  error: string | null;
  onCreate: (title: string) => void;
  onClose: () => void;
}

export default function RoomHostPanel({
  room,
  isCreating,
  isCapturing,
  error,
  onCreate,
  onClose,
}: RoomHostPanelProps) {
  const [title, setTitle] = useState('LiveCap room');
  const [copied, setCopied] = useState<'code' | 'link' | null>(null);
  const [showQr, setShowQr] = useState(true);
  const isArchived = room?.status === 'ended';

  const copy = async (value: string, kind: 'code' | 'link') => {
    await navigator.clipboard.writeText(value);
    setCopied(kind);
    window.setTimeout(() => setCopied(null), 1_600);
  };

  return (
    <section className="border-t border-[#dce5f2] px-6 py-5">
      <div className="flex items-start gap-3">
        <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-[#e9f2ff] text-ink">
          <Users className="h-4 w-4" />
        </span>
        <div>
          <p className="text-sm font-bold text-ink">Audience room</p>
          <p className="mt-1 text-xs leading-relaxed text-ink-muted">
            Share finalized captions with viewers on their own devices.
          </p>
        </div>
      </div>

      {!room ? (
        <div className="mt-4 space-y-3">
          <label className="block">
            <span className="sr-only">Room title</span>
            <input
              value={title}
              maxLength={80}
              onChange={(event) => setTitle(event.target.value)}
              className="h-11 w-full rounded-xl border border-[#dce5f2] bg-white px-3 text-sm text-ink outline-none transition focus:border-emerald-pro"
              placeholder="Room title"
            />
          </label>
          <button
            type="button"
            disabled={isCreating || isCapturing || title.trim() === ''}
            onClick={() => onCreate(title.trim())}
            className="flex h-11 w-full items-center justify-center gap-2 rounded-xl bg-ink text-sm font-bold text-white transition-colors hover:bg-emerald-pro disabled:cursor-not-allowed disabled:opacity-40"
          >
            {isCreating ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Radio className="h-4 w-4" />}
            {isCreating ? 'Creating room...' : 'Create audience room'}
          </button>
          {isCapturing && (
            <p className="text-[11px] leading-relaxed text-ink-muted">
              Stop the current session before creating an audience room.
            </p>
          )}
        </div>
      ) : (
        <div className="mt-4 overflow-hidden rounded-xl border border-emerald-pro/20 bg-[#effbf8]">
          <div className="flex items-center justify-between border-b border-emerald-pro/15 px-4 py-3">
            <span className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[0.14em] text-emerald-pro">
              <span className={`h-2 w-2 rounded-full bg-emerald-pro ${isArchived ? '' : 'animate-pulse'}`} />
              {isArchived ? 'Transcript saved' : 'Room live'}
            </span>
            <button
              type="button"
              onClick={onClose}
              className="rounded-md p-1 text-ink/40 transition hover:bg-white hover:text-crimson"
              aria-label={isArchived ? 'Dismiss saved room' : 'Close audience room'}
              title={isArchived ? 'Dismiss' : 'Close room'}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
          <div className="px-4 py-4">
            <button
              type="button"
              onClick={() => setShowQr((current) => !current)}
              className="flex h-10 w-full items-center justify-center gap-2 rounded-lg bg-ink text-xs font-bold text-white transition hover:bg-emerald-pro"
              aria-expanded={showQr}
            >
              <QrCode className="h-4 w-4" />
              {showQr ? 'Hide QR code' : 'Show QR code'}
            </button>
            {showQr && (
              <div className="mt-3 rounded-xl border border-ink/10 bg-white p-3 text-center">
                <div className="mx-auto w-fit rounded-lg bg-white p-2">
                  <QRCodeSVG
                    value={room.joinUrl}
                    size={176}
                    level="M"
                    bgColor="#ffffff"
                    fgColor="#0b1f44"
                    role="img"
                    aria-label="Viewer room QR code"
                  />
                </div>
                <p className="mt-2 text-[11px] font-bold text-ink">
                  {isArchived ? 'Scan to view saved captions' : 'Scan to join live captions'}
                </p>
                <p className="mt-1 break-all text-[9px] leading-relaxed text-ink/45">{room.joinUrl}</p>
              </div>
            )}
            <p className="mt-4 text-xs text-ink-muted">Room code</p>
            <div className="mt-1 flex items-center justify-between gap-2">
              <span className="font-mono text-2xl font-bold tracking-[0.22em] text-ink">
                {room.roomCode}
              </span>
              <button
                type="button"
                onClick={() => void copy(room.roomCode, 'code')}
                className="grid h-9 w-9 place-items-center rounded-lg border border-ink/10 bg-white text-ink/55 transition hover:text-emerald-pro"
                aria-label="Copy room code"
              >
                {copied === 'code' ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </button>
            </div>
            <button
              type="button"
              onClick={() => void copy(room.joinUrl, 'link')}
              className="mt-3 flex h-10 w-full items-center justify-center gap-2 rounded-lg border border-ink/10 bg-white text-xs font-bold text-ink transition hover:border-emerald-pro/40 hover:text-emerald-pro"
            >
              {copied === 'link' ? <Check className="h-3.5 w-3.5" /> : <Link2 className="h-3.5 w-3.5" />}
              {copied === 'link' ? 'Link copied' : 'Copy viewer link'}
            </button>
            <p className="mt-3 text-[10px] leading-relaxed text-ink/50">
              The QR, viewer link, and room code open the same read-only page. Anyone with one of them can view finalized captions until {formatExpiry(room.expiresAt)}.
            </p>
          </div>
        </div>
      )}

      {error && <p className="mt-2 text-[11px] leading-relaxed text-crimson">{error}</p>}
      <p className="mt-3 text-[10px] leading-relaxed text-ink/45">
        Only finalized text is shared. Raw microphone audio is never stored in the room archive.
      </p>
    </section>
  );
}

function formatExpiry(value: string): string {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'the archive expires';
  return date.toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' });
}
