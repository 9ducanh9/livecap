import { LoaderCircle, MonitorUp, Square, Radio } from 'lucide-react';
import type { HostedRoom } from '../services/roomService';
import { isRoomScreenShareEnabled } from '../services/roomService';
import { useRoomFeed } from '../hooks/useRoomFeed';
import type { useRoomScreenShare } from '../hooks/useRoomScreenShare';
import RoomAudienceContent from './RoomAudienceContent';

type ScreenShare = ReturnType<typeof useRoomScreenShare>;

export default function RoomHostView({
  room, screenShare, isCapturing, isClosing, onStopLive,
}: {
  room: HostedRoom;
  screenShare: ScreenShare;
  isCapturing: boolean;
  isClosing: boolean;
  onStopLive: () => void;
}) {
  const feed = useRoomFeed(room.roomCode, room.hostToken);
  const ended = room.status === 'ended' || feed.status === 'ended';
  const audioSource = isCapturing
    ? 'Audio Source selected on the left'
    : screenShare.audioCaptionsActive
      ? 'Shared screen audio'
      : 'No audio captions active';

  return (
    <div className="flex-1 bg-[#f4f7fb] px-4 py-5 sm:px-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-bold uppercase tracking-[0.16em] text-emerald-pro">Host preview</p>
          <h2 className="mt-1 font-instrument text-2xl font-bold text-ink">{room.title}</h2>
          <p className="mt-1 font-mono text-[10px] tracking-[0.15em] text-ink/50">ROOM {room.roomCode}</p>
        </div>
        {!ended && (
          <button
            type="button"
            onClick={onStopLive}
            disabled={isClosing}
            className="inline-flex h-10 items-center gap-2 rounded-xl bg-crimson px-4 text-xs font-bold text-white transition hover:bg-crimson/85 disabled:opacity-50"
          >
            {isClosing ? <LoaderCircle className="h-4 w-4 animate-spin" /> : <Square className="h-3.5 w-3.5" />}
            {isClosing ? 'Stopping live...' : 'Stop live'}
          </button>
        )}
      </div>

      {!ended && isRoomScreenShareEnabled() && (
        <div className="mt-5 rounded-2xl border border-[#dce5f2] bg-white p-4">
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              disabled={screenShare.status === 'starting' || isClosing}
              onClick={() => void (screenShare.status === 'live' ? screenShare.stop() : screenShare.start())}
              className={`inline-flex h-11 items-center gap-2 rounded-xl px-5 text-sm font-bold text-white transition disabled:opacity-50 ${screenShare.status === 'live' ? 'bg-crimson hover:bg-crimson/85' : 'bg-ink hover:bg-emerald-pro'}`}
            >
              {screenShare.status === 'starting' ? <LoaderCircle className="h-4 w-4 animate-spin" /> : screenShare.status === 'live' ? <Square className="h-3.5 w-3.5" /> : <MonitorUp className="h-4 w-4" />}
              {screenShare.status === 'starting' ? 'Starting share...' : screenShare.status === 'live' ? 'Stop screen share' : 'Share screen'}
            </button>
            <span className="inline-flex items-center gap-2 text-xs text-ink-muted"><Radio className="h-3.5 w-3.5 text-emerald-pro" />Captions: {audioSource}</span>
          </div>
          <p className="mt-3 text-xs leading-5 text-ink-muted">Your preview is muted to prevent echo. Screen sharing works without shared audio; choose an Audio Source on the left and start a session when needed.</p>
          {screenShare.error && <p role="alert" className="mt-2 text-xs text-crimson">{screenShare.error}</p>}
        </div>
      )}

      {feed.error && <p role="alert" className="mt-4 rounded-xl border border-crimson/20 bg-crimson/5 p-3 text-xs text-crimson">{feed.error}</p>}
      {ended && <p className="mt-4 rounded-xl border border-emerald-pro/20 bg-[#effbf8] p-3 text-xs text-ink">Live ended. The finalized transcript remains available until the room expires.</p>}
      <div className="mt-5"><RoomAudienceContent roomCode={room.roomCode} feed={feed} muted /></div>
    </div>
  );
}
