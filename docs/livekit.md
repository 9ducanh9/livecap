# LiveKit room media

Set backend `ROOM_MEDIA_PROVIDER=livekit`, `LIVEKIT_URL=wss://<project>.livekit.cloud`,
`LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET`. Keep credentials in a backend secret
store; never put them in Vite variables or commit them. Enable the existing room
and screen-share feature flags. Existing Cognito and room-owner checks still apply.

The backend creates a fresh media room for each broadcast and returns a short-lived,
room-scoped participant token. Hosts publish screen video and mixed microphone/tab
audio; viewers can only subscribe. Caption transcription still uses the existing
backend WebSocket. Initial media rooms allow one host plus two viewers.

Stopping all media or closing the room deletes the LiveKit room. Stopping screen
sharing alone keeps microphone broadcasting if the host microphone is active.
An empty room is cleaned up by LiveKit. Browser permission and tab-audio selection
are still required. LiveKit Cloud usage and backend AWS usage are billed separately.

## License

The LiveKit JavaScript SDK and Python API SDK use Apache License 2.0.
Preserve their LICENSE/NOTICE files when distributing these dependencies.
LiveKit Cloud is also subject to its service terms:
https://livekit.com/legal/terms-of-service

## Verification

Unit tests verify restricted token grants, fresh broadcast names, participant limit,
and cleanup calls. A real Cloud project and host/viewer smoke are required before
claiming deployed screen/audio support. Do not infer media performance from unit tests.
