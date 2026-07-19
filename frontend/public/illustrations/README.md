# Transcript history illustrations

`TranscriptHistoryPanel.tsx` looks for these two files here (served at
`/illustrations/...`). If a file is missing, the panel silently falls back to
a plain icon — nothing breaks, so this can be filled in whenever convenient.

- `history-empty.png` — "no transcripts yet" state.
- `history-session-expired.png` — "sign in again" state.

Both were generated in Canva (LiveCap emerald `#0a9c88` / ink `#102247` /
paper `#eef2f8` palette) and exported as transparent 480x480 PNGs. Open the
designs, adjust if you like, then export → PNG → transparent background, and
save with the exact filenames above:

- Empty state: https://www.canva.com/d/jq4FU8ifZGqPH8H
- Session expired: https://www.canva.com/d/Ai4FOWjEoMMx3WU
