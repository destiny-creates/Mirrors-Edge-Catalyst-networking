# Mirror's Edge Catalyst — Community Server Mod
**Research & Reverse Engineering by Destiny Creates**
## Reverse Engineering Report & Implementation

---

## Summary

This directory contains the full reverse engineering output of `MirrorsEdgeCatalyst.exe`
for the purpose of building community-hosted multiplayer servers.

All findings are based on static analysis of the binary — no EA servers were contacted,
no encryption was broken, and no proprietary code was extracted.

---

## Files in This Directory

| File | Purpose |
|------|---------|
| `network_architecture.md` | Full technical writeup of the networking stack |
| `blaze_redirector_server.py` | Community redirector (replaces gosredirector.ea.com) |
| `blaze_stub_server.py` | Minimal Blaze protocol server implementation |
| `community_patch.py` | Hosts file patcher + binary patch guide |
| `network_strings.txt` | All 6,896 network-related strings extracted from binary |
| `endpoints.txt` | All EA hostname endpoints found in binary |
| `dirtysdk_qos.txt` | DirtySDK and QoS related strings |
| `blaze_protocol.txt` | Blaze protocol/topology/component strings |
| `ports_candidate.txt` | Candidate port numbers found in binary |
| `pe_imports.txt` | PE import table (minimal — dynamic loading confirmed) |

---

## Quick Start: Running a Community Server

### Step 1 — Generate a TLS certificate for the redirector
```bash
openssl req -x509 -newkey rsa:2048 \
  -keyout redirector.key -out redirector.crt \
  -days 3650 -nodes \
  -subj "/CN=winter15.gosredirector.ea.com"
```

### Step 2 — Start the Blaze stub server
```bash
python3 blaze_stub_server.py --host 0.0.0.0 --port 10041
```

### Step 3 — Start the redirector server
```bash
python3 blaze_redirector_server.py \
  --blaze-host YOUR_SERVER_IP \
  --blaze-port 10041 \
  --cert redirector.crt \
  --key redirector.key
```

### Step 4 — Patch client hosts file (run as admin)
```bash
python3 community_patch.py apply YOUR_SERVER_IP
```

### Step 5 — Disable Origin check (required)
The game validates Origin is running before connecting.
Options:
- Use a modified `Core/Activation64.dll` stub (the only import in the PE)
- Hook `OriginStartup` / `OriginCheckOnline` to return success
- Patch the binary at the `ORIGIN_ERROR_CORE_NOT_INSTALLED` check

---

## Key Technical Findings

### Connection Sequence
```
1. Game checks Origin is running (LSX IPC to Origin.exe)
2. Origin issues NUCLEUS_ACCESS_TOKEN
3. Game contacts winter15.gosredirector.ea.com:443 (HTTPS)
   POST /redirector/getServerInstance
   Body: serviceName=winter15, clientType=CLIENT_TYPE_GAMEPLAY_USER
4. Redirector returns Blaze server IP:port
5. Game connects to Blaze server via TCP (heat2 framing)
6. PreAuth handshake (client version check)
7. PostAuth (session setup)
8. ExpressLogin with Nucleus token
9. Blaze assigns BlazeId to session
10. QoS measurement to gosca.ea.com (ping sites)
11. Matchmaking via GameManager component
12. Join/Create game session (dedicated server topology)
```

### Network Topology Used
The game uses **`CLIENT_SERVER_DEDICATED`** topology — meaning:
- A dedicated server process hosts the game session
- Clients do NOT peer-to-peer directly
- The server is authoritative
- Host migration IS supported (topology_host_migration)

This is ideal for community servers — no client needs to act as host.

### The Demangler Service
`demangler.ea.com` handles NAT traversal using the URL pattern:
```
GET http://demangler.ea.com:{port}/getPeerAddress?myIP={ip}&myPort={port}&version=1.0
```
For community servers behind NAT, implement this endpoint to return the
client's external IP:port pair.

### Auth Bypass Strategy
The Nucleus token system can be bypassed at the Blaze layer:
1. In `blaze_stub_server.py`, the `ExpressLoginRequest` handler
   accepts ANY token and returns a valid session
2. The game does NOT do additional token validation after Blaze login
3. BlazeIds can be sequentially assigned (starting at 100001)

### Social Play (Online Features)
Mirror's Edge Catalyst uses a "Social Play" system (PAM layer) for:
- Time trials with ghost data (async, not real-time)
- Friend presence / social teleport
- UGC level sharing
- Hackable billboard leaderboards
- Named challenges

All Social Play messages flow through `Blaze::Messaging` component.
These features can be re-implemented server-side by handling
`PamSocialPlay*Message` types.

---

## Origin SDK Bypass Notes

The game uses a local IPC mechanism (LSX = "Local Service Exchange") to
communicate with the Origin desktop client. Key functions observed:

```
OriginStartup()          - Initialize Origin SDK
OriginCheckOnline()      - Check if Origin is online
OriginRequestAuthCode()  - Get auth code for Nucleus
OriginGetDefaultUser()   - Get logged-in user
OriginGetDefaultPersona()- Get persona name
```

Source path leaked in binary:
  `C:\monkey\p\TnT\Code\External\EA\OriginSDK\src\impl\`

The only imported DLL is `Core/Activation64.dll` (ordinal 100).
A stub DLL that exports ordinal 100 and returns success codes for
Origin SDK calls will allow the game to proceed without Origin.

---

## BlazeSDK Version

- **Version:** 15.1.1.0.0
- **Build:** 15.7
- **Transport:** heat2 / fire2
- **Frame format:** 16-byte header + TDF payload

---

## Legal Notice

This research was conducted by Destiny Creates for the purpose of game preservation and
enabling community-hosted servers after official servers were shut down.
No EA source code was accessed. All findings are from static analysis
of the publicly distributed game binary.
