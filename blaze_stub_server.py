#!/usr/bin/env python3
"""
Mirror's Edge Catalyst - Community Blaze Stub Server
=====================================================
Researched and reverse engineered by Destiny Creates
Implements a minimal Blaze protocol server that accepts
client connections and handles the core handshake sequence.

Blaze Protocol Summary (from binary analysis of BlazeSDK 15.1.1.0.0):
  - Transport: TCP (heat2/fire2 framing)
  - Auth:      Nucleus token → ExpressLogin
  - Topology:  CLIENT_SERVER_DEDICATED
  - Components: Authentication, GameManager, Redirector,
                Stats, Messaging, Association, Util

Blaze frame format (heat2):
  [2 bytes] Component ID
  [2 bytes] Command ID
  [4 bytes] Error code
  [1 byte]  Message type (0x00=Request, 0x20=Response, 0x40=Notify, 0x60=Error)
  [3 bytes] Message ID
  [4 bytes] Payload length
  [N bytes] TDF encoded payload

TDF (Type-Data-Format) is EA's proprietary serialization format.
"""

import asyncio
import struct
import logging
from typing import Optional

logging.basicConfig(level=logging.INFO,
                    format='[BlazeServer] %(asctime)s %(levelname)s %(message)s')
log = logging.getLogger('blaze')

# ---------------------------------------------------------------------------
# Blaze Component IDs (from Blaze::* class names in binary)
# ---------------------------------------------------------------------------
COMPONENT_AUTH       = 0x0001  # Blaze::Authentication
COMPONENT_GAMEMANAGER= 0x0004  # Blaze::GameManager
COMPONENT_REDIRECTOR = 0x0005  # Blaze::Redirector
COMPONENT_STATS      = 0x0007  # Blaze::Stats
COMPONENT_UTIL       = 0x0009  # Blaze::Util
COMPONENT_MESSAGING  = 0x000F  # Blaze::Messaging
COMPONENT_ASSOCLIST  = 0x0019  # Blaze::Association
COMPONENT_BYTEVAULT  = 0x001C  # Blaze::ByteVault
COMPONENT_PLAYGROUPS = 0x001D  # Blaze::Playgroups
COMPONENT_REPORTING  = 0x001E  # Blaze::GameReporting

# ---------------------------------------------------------------------------
# Blaze Command IDs (from RPC method names in binary)
# ---------------------------------------------------------------------------
# Util component
CMD_UTIL_PREAUTH     = 0x0001  # PreAuthRequest / PreAuthResponse
CMD_UTIL_POSTAUTH    = 0x0002  # PostAuthRequest / PostAuthResponse
CMD_UTIL_PING        = 0x0003  # PingResponse

# Auth component
CMD_AUTH_LOGIN       = 0x0001  # LoginRequest / LoginResponse
CMD_AUTH_EXPRESS_LOGIN = 0x0015 # ExpressLoginRequest
CMD_AUTH_TRUSTED_LOGIN = 0x0016 # TrustedLoginRequest
CMD_AUTH_LOGOUT      = 0x0002  # Logout
CMD_AUTH_LIST_ENTITLEMENTS = 0x0018 # ListEntitlementsRequest

# GameManager component
CMD_GM_CREATE_GAME   = 0x0001  # CreateGameRequest
CMD_GM_DESTROY_GAME  = 0x0002  # DestroyGameRequest
CMD_GM_JOIN_GAME     = 0x0014  # JoinGameRequest
CMD_GM_START_MM      = 0x000D  # StartMatchmakingRequest
CMD_GM_CANCEL_MM     = 0x000E  # CancelMatchmakingRequest

# ---------------------------------------------------------------------------
# Message Types
# ---------------------------------------------------------------------------
MSG_REQUEST  = 0x00
MSG_RESPONSE = 0x20
MSG_NOTIFY   = 0x40
MSG_ERROR    = 0x60

# ---------------------------------------------------------------------------
# Blaze Frame Parser
# ---------------------------------------------------------------------------
HEADER_SIZE = 16  # component(2) + command(2) + error(4) + type+msgid(4) + length(4)

def parse_frame_header(data: bytes) -> Optional[dict]:
    if len(data) < HEADER_SIZE:
        return None
    component, command = struct.unpack_from('>HH', data, 0)
    error              = struct.unpack_from('>I', data, 4)[0]
    msg_type_and_id    = struct.unpack_from('>I', data, 8)[0]
    msg_type           = (msg_type_and_id >> 24) & 0xFF
    msg_id             = msg_type_and_id & 0x00FFFFFF
    payload_len        = struct.unpack_from('>I', data, 12)[0]
    return {
        'component':   component,
        'command':     command,
        'error':       error,
        'msg_type':    msg_type,
        'msg_id':      msg_id,
        'payload_len': payload_len,
    }

def build_frame(component: int, command: int, msg_id: int,
                msg_type: int = MSG_RESPONSE,
                payload: bytes = b'', error: int = 0) -> bytes:
    type_and_id = ((msg_type & 0xFF) << 24) | (msg_id & 0x00FFFFFF)
    header = struct.pack('>HHIII',
                         component, command,
                         error,
                         type_and_id,
                         len(payload))
    return header + payload

# ---------------------------------------------------------------------------
# Minimal TDF helpers
# TDF is EA proprietary; we only need to encode simple string/int responses
# for the handshake. Full TDF decode is not required for the stub.
# ---------------------------------------------------------------------------
TDF_INTEGER = 0x01
TDF_STRING  = 0x02
TDF_BLOB    = 0x03
TDF_MAP     = 0x07
TDF_UNION   = 0x08

def tdf_tag(label: str) -> bytes:
    """Encode a 4-char TDF field label into 3 bytes."""
    label = label.upper().ljust(4)[:4]
    vals = [ord(c) - 0x20 for c in label]
    return bytes([
        ((vals[0] & 0x3F) << 2) | ((vals[1] & 0x30) >> 4),
        ((vals[1] & 0x0F) << 4) | ((vals[2] & 0x3C) >> 2),
        ((vals[2] & 0x03) << 6) | (vals[3] & 0x3F),
    ])

def tdf_int(label: str, value: int) -> bytes:
    tag = tdf_tag(label)
    # variable-length encoding
    enc = []
    v = value
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            enc.append(b | 0x80)
        else:
            enc.append(b)
            break
    return tag + bytes([TDF_INTEGER]) + bytes(enc)

def tdf_str(label: str, value: str) -> bytes:
    tag = tdf_tag(label)
    encoded = value.encode('utf-8') + b'\x00'
    length = len(encoded)
    length_enc = []
    v = length
    while True:
        b = v & 0x7F
        v >>= 7
        if v:
            length_enc.append(b | 0x80)
        else:
            length_enc.append(b)
            break
    return tag + bytes([TDF_STRING]) + bytes(length_enc) + encoded

# ---------------------------------------------------------------------------
# Response Payloads
# ---------------------------------------------------------------------------
def build_preauth_response() -> bytes:
    """
    Blaze::Util::PreAuthResponse
    Fields: CINF (client info), CONF (config), VDFF (version diff)
    Minimal response to satisfy the client handshake.
    """
    return (
        tdf_str('CDAT', 'data') +
        tdf_str('IITO', 'winter15') +
        tdf_int('RPRT', 0) +
        tdf_str('SNAM', 'winter15') +
        tdf_str('SVID', 'community') +
        tdf_int('TYPE', 0)
    )

def build_postauth_response() -> bytes:
    """Blaze::Util::PostAuthResponse — returns telemetry/ticker server info."""
    return (
        tdf_str('PSS_', 'community-server') +
        tdf_int('RPRT', 0)
    )

def build_login_response(session_id: int = 1, blaze_id: int = 100001) -> bytes:
    """
    Blaze::Authentication::LoginResponse / ExpressLoginResponse
    Assigns client a BlazeId and session key.
    """
    return (
        tdf_int('BUID', blaze_id) +
        tdf_int('FRST', 0) +
        tdf_str('KEY_', 'community-session-key') +
        tdf_int('LLOG', 0) +
        tdf_str('MAIL', 'player@community.local') +
        tdf_int('SPAM', 0) +
        tdf_str('THST', 'community-server') +
        tdf_str('TOS_', '') +
        tdf_str('UNAM', f'Player{blaze_id}') +
        tdf_int('UID_', session_id)
    )

def build_ping_response() -> bytes:
    return tdf_int('STIM', 0)

# ---------------------------------------------------------------------------
# Client Session
# ---------------------------------------------------------------------------
class BlazeClientSession:

    _next_id = 100001

    def __init__(self, reader: asyncio.StreamReader,
                 writer: asyncio.StreamWriter):
        self.reader  = reader
        self.writer  = writer
        self.addr    = writer.get_extra_info('peername')
        self.blaze_id = BlazeClientSession._next_id
        BlazeClientSession._next_id += 1
        self._buf    = b''
        log.info(f'Client connected: {self.addr} → BlazeId {self.blaze_id}')

    async def run(self):
        try:
            while True:
                chunk = await self.reader.read(4096)
                if not chunk:
                    break
                self._buf += chunk
                await self._process_buffer()
        except (asyncio.IncompleteReadError, ConnectionResetError):
            pass
        finally:
            log.info(f'Client disconnected: {self.addr}')
            self.writer.close()

    async def _process_buffer(self):
        while len(self._buf) >= HEADER_SIZE:
            hdr = parse_frame_header(self._buf)
            if hdr is None:
                break
            total = HEADER_SIZE + hdr['payload_len']
            if len(self._buf) < total:
                break
            payload = self._buf[HEADER_SIZE:total]
            self._buf = self._buf[total:]
            await self._dispatch(hdr, payload)

    async def _dispatch(self, hdr: dict, payload: bytes):
        comp = hdr['component']
        cmd  = hdr['command']
        mid  = hdr['msg_id']
        log.debug(f'Frame comp=0x{comp:04X} cmd=0x{cmd:04X} mid={mid} '
                  f'len={hdr["payload_len"]}')

        # Route to handler
        if comp == COMPONENT_UTIL:
            if cmd == CMD_UTIL_PREAUTH:
                await self._send(comp, cmd, mid, build_preauth_response())
            elif cmd == CMD_UTIL_POSTAUTH:
                await self._send(comp, cmd, mid, build_postauth_response())
            elif cmd == CMD_UTIL_PING:
                await self._send(comp, cmd, mid, build_ping_response())
            else:
                await self._send(comp, cmd, mid, b'')

        elif comp == COMPONENT_AUTH:
            if cmd in (CMD_AUTH_LOGIN, CMD_AUTH_EXPRESS_LOGIN,
                       CMD_AUTH_TRUSTED_LOGIN):
                log.info(f'Auth login from {self.addr} (BlazeId {self.blaze_id})')
                await self._send(comp, cmd, mid,
                                 build_login_response(mid, self.blaze_id))
            elif cmd == CMD_AUTH_LOGOUT:
                await self._send(comp, cmd, mid, b'')
            elif cmd == CMD_AUTH_LIST_ENTITLEMENTS:
                await self._send(comp, cmd, mid, b'')
            else:
                await self._send(comp, cmd, mid, b'')

        elif comp == COMPONENT_GAMEMANAGER:
            log.info(f'GameManager cmd=0x{cmd:04X} from {self.addr}')
            await self._send(comp, cmd, mid, b'')

        else:
            # Default: empty success response for unhandled components
            await self._send(comp, cmd, mid, b'')

    async def _send(self, component: int, command: int, msg_id: int,
                    payload: bytes, error: int = 0):
        frame = build_frame(component, command, msg_id,
                            MSG_RESPONSE, payload, error)
        self.writer.write(frame)
        await self.writer.drain()


# ---------------------------------------------------------------------------
# Server Entry Point
# ---------------------------------------------------------------------------
async def start_server(host: str = '0.0.0.0', port: int = 10041):
    srv = await asyncio.start_server(
        lambda r, w: BlazeClientSession(r, w).run(),
        host, port
    )
    log.info(f'Blaze stub server listening on {host}:{port}')
    log.info(f'Service name: {SERVICE_NAME}')
    log.info(f'Protocol: heat2/fire2 (BlazeSDK 15.1.1.0.0 compatible)')
    async with srv:
        await srv.serve_forever()


SERVICE_NAME = 'winter15'

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
        description="Mirror's Edge Catalyst Community Blaze Server")
    parser.add_argument('--host', default='0.0.0.0')
    parser.add_argument('--port', type=int, default=10041)
    args = parser.parse_args()
    asyncio.run(start_server(args.host, args.port))
