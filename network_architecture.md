# Mirror's Edge Catalyst — Network Architecture
## Research & Reverse Engineering by Destiny Creates
## Reverse Engineered from MirrorsEdgeCatalyst.exe (84MB PE32+ x86-64)

---

## 1. Engine & SDK Stack

| Layer | Technology | Notes |
|-------|-----------|-------|
| Game Engine | Frostbite (EA DICE) | Copyright 2007 EA DICE |
| Multiplayer SDK | BlazeSDK 15.1.1.0.0 (build 15.7) | EA's proprietary multiplayer backend |
| Transport | DirtySDK (ProtoHTTP, ProtoSSL, ProtoTunnel, ProtoUDP) | EA's low-level socket abstraction |
| Auth | Origin SDK + Nucleus | LSX IPC to local Origin client |
| Scripting | Lua (PUC-Rio, Copyright 1994-2006) | Embedded scripting |
| Compression | zlib (Gailly/Adler, 1995-2010) | Data compression |
| TLS | OpenSSL 0.9.8k (2009-03-25) | Certificate validation |
| Physics | Havok (multiple versioned hashes) | Not network-relevant |

**Internal Project Codename:** Arson (seen in all GameReporting class names)
**Title Code:** MECATPC (Mirror's Edge Catalyst PC)
**EA Service Name:** winter15
**Dedicated Server Binary Name:** "Catalyst Server"

---

## 2. Blaze Protocol

Blaze is EA's proprietary client-server multiplayer protocol. It runs over:
- **TCP + TLS (heat2/fire2)** — reliable ordered messages
- **UDP (ProtoUDP)** — unreliable real-time data
- **SSL port 443** confirmed in binary

### Blaze Transport Names
- `heat2` — legacy Blaze transport name
- `fire2` — current Blaze transport (Fire2Metadata present)

### Connection Flow
```
Client
  │
  ├─► winter15.gosredirector.ea.com:443 (HTTPS/TLS)
  │       └── GET /redirector/getServerInstance
  │           Returns: BlazeServer IP:port for this region
  │
  ├─► <blazeserver>:10041 (TCP, insecure) or :10042 (TCP, SSL)
  │       └── PreAuth  → client name/version handshake
  │           PostAuth → session token
  │
  ├─► Nucleus (peach.online.ea.com) — OAuth token exchange
  │       └── NUCLEUS_ACCESS_TOKEN → Blaze ExpressLogin
  │
  └─► QoS Server (gosca.ea.com)
          └── Ping site latency measurement → matchmaking region selection
```

### Client Types
| Constant | Value | Description |
|---------|-------|-------------|
| CLIENT_TYPE_GAMEPLAY_USER | standard | Normal player |
| CLIENT_TYPE_DEDICATED_SERVER | ds | Dedicated server process |
| CLIENT_TYPE_HTTP_USER | http | HTTP-only client |
| CLIENT_TYPE_TOOLS | tools | Dev tools |
| CLIENT_TYPE_LIMITED_GAMEPLAY_USER | limited | Restricted client |

---

## 3. Server Endpoints

### GOS Redirector (4 environments)
| Environment | Hostname | Purpose |
|------------|----------|---------|
| Production | `winter15.gosredirector.ea.com` | Live servers |
| Cert Staging | `winter15.gosredirector.scert.ea.com` | Pre-production |
| Dev | `winter15.gosredirector.sdev.ea.com` | Internal dev |
| Test | `winter15.gosredirector.stest.ea.com` | QA testing |

### Other EA Services
| Service | Hostname | Purpose |
|---------|----------|---------|
| GOS CA | `gosca.ea.com` | Certificate authority / QoS |
| Online | `peach.online.ea.com` | Nucleus/OAuth |
| Demangler | `demangler.ea.com` | NAT traversal helper |
| Store | `www.origin.com/store` | Commerce |

### QoS URL Templates
```
https://{qos_host}:{port}/qos/qos
https://{qos_host}:{port}/qos/firewall
https://{qos_host}:{port}/qos/firetype
http://{demangler_host}:{port}/getPeerAddress?myIP={ip}&myPort={port}&version=1.0
```

---

## 4. Network Topology

The game supports all four Blaze topologies:

| Topology | Constant | Status |
|---------|---------|--------|
| Dedicated Server | `GameNetworkTopology_DedicatedServer` | PRIMARY — used for multiplayer |
| Peer Hosted | `GameNetworkTopology_PeerHosted` | Fallback |
| Full Mesh P2P | `PEER_TO_PEER_FULL_MESH` | Supported |
| Partial Mesh P2P | `PEER_TO_PEER_PARTIAL_MESH` | Supported |
| DirtyCast Failover | `PEER_TO_PEER_DIRTYCAST_FAILOVER` | Relay fallback |
| Disabled | `GameNetworkTopology_Disabled` | Offline |

**Host Migration** is supported: `TOPOLOGY_HOST_MIGRATION`, `TOPOLOGY_PLATFORM_HOST_MIGRATION`

---

## 5. Blaze Component Map

All Blaze services used by the game:

| Component | Namespace | Key RPCs |
|-----------|----------|----------|
| Authentication | `Blaze::Authentication` | LoginRequest, ExpressLoginRequest, TrustedLoginRequest, ListEntitlements, GetUserAccessToken |
| GameManager | `Blaze::GameManager` | CreateGame, JoinGame, StartMatchmaking, DestroyGame, UpdateMeshConnection |
| Redirector | `Blaze::Redirector` | getServerInstance, ServerListRequest, CACertificateRequest |
| Stats | `Blaze::Stats` | GetStats, UpdateStats, LeaderboardStats, GetEntityCount |
| Messaging | `Blaze::Messaging` | SendMessage, FetchMessage, PurgeMessage |
| Association Lists | `Blaze::Association` | Friends/blocked lists, GetListForUser |
| ByteVault | `Blaze::ByteVault` | UpsertRecord, GetRecord, DeleteRecord (cloud save) |
| Playgroups | `Blaze::Playgroups` | CreatePlaygroup, JoinPlaygroup, SetJoinControls |
| Game Reporting | `Blaze::GameReporting` | SubmitGameReport (Frostbite + Arson report types) |
| Util | `Blaze::Util` | PreAuth, PostAuth, GetTelemetryServer, GetTickerServer, FilterUserText |

---

## 6. Matchmaking & QoS

### NAT Types
- NAT_TYPE_OPEN
- NAT_TYPE_MODERATE
- NAT_TYPE_STRICT
- NAT_TYPE_STRICT_SEQUENTIAL
- NAT_TYPE_NONE
- NAT_TYPE_PENDING
- NAT_TYPE_UNKNOWN

### QoS Matchmaking Fields
- `bestPingSiteAlias` — selected region based on lowest latency
- `gamePingSiteAlias` — ping site of the game session
- `bandwidthPingSiteInfo` — bandwidth measurement per ping site
- `pingSiteLatencyByAliasMap` — latency map used for MM decisions
- `performQosValidation` — flag to trigger QoS check on join
- `validateQosForJoiningPlayer` — server-side validation
- `PLAYER_CONN_LOST_QOS_RULE` — player removed if QoS fails
- `PLAYER_JOIN_TIMEOUT_QOS_RULE` — join timeout on QoS failure

### Matchmaking Session Modes
- `MatchmakingSessionMode_FindDedicatedServer`
- `MatchmakingSessionMode_ResetDedicatedServer`
- `MATCHMAKING_CONTEXT_FIND_DEDICATED_SERVER`

### Connection Validation States
- CONNECTION_ASSURED
- CONNECTION_FEASIBLE
- CONNECTION_LIKELY
- CONNECTION_UNLIKELY
- CONNECTION_VERIFICATION

---

## 7. Auth Flow (Nucleus/Origin)

```
1. Origin.exe running locally (LSX IPC)
2. OriginRequestAuthCode → LSX challenge
3. Nucleus returns NUCLEUS_ACCESS_TOKEN
4. Client sends nucleusConnectTrusted to Blaze
5. Blaze validates token with peach.online.ea.com
6. Blaze returns UserSessionLoginInfo + BlazeId
7. Client proceeds to PreAuth → PostAuth → game
```

**Token fields observed:**
- NUCLEUS_ACCESS_TOKEN
- NUCLEUS_AUTH_TOKEN
- NUCLEUS_PERSONA
- NUCLEUS_USER
- ORIGIN_PERSONA_ID

---

## 8. Game Modes (Network-Relevant)

| Mode | Frostbite Constant | Network Type |
|------|---------------------|-------------|
| Singleplayer | `frostbite_singleplayer` | No network |
| Multiplayer | `frostbite_multiplayer` | Dedicated server |
| Cooperative | `frostbite_cooperative` | Dedicated server |
| Social Play | `PamSocialPlay` | Dedicated server + P2P hybrid |

### Social Play System ("PAM" layer)
Mirror's Edge Catalyst uses a **Social Play** system built on top of Blaze GameManager:
- Named challenges (time trials with async leaderboard)
- Shared content (ghost replays, UGC levels)
- Hackable billboards (live leaderboard events)
- Social teleport (join friend in open world)
- Map markers (async world presence)
- Friend list synchronization

All Social Play events are message-based:
`PamSocialPlay*Message` classes send/receive via `Blaze::Messaging`

---

## 9. Disconnect / Error Reasons

| Reason | Meaning |
|--------|---------|
| ExitToMenuReason_DisconnectedFromServer | Server dropped client |
| ExitToMenuReason_VirtualServerExpired | Dedicated server lease ended |
| ExitToMenuReason_VirtualServerRecreate | Server being recycled |
| ExitToMenuReason_KickedOutServerFull | Server capacity hit |
| ExitToMenuReason_InteractivityTimeout | AFK/inactivity timeout |
| ExitToMenuReason_WantToConnectToOnline | Re-auth needed |
| SecureReason_WrongProtocolVersion | Version mismatch |
| SecureReason_MismatchingContent | DLC mismatch |
| SecureReason_ServerMaintenance | Planned downtime |

---

## 10. UPnP

The game uses UPnP for NAT traversal:
- Discovery: `239.255.255.250:1900` (SSDP multicast)
- Device type: `urn:schemas-upnp-org:device:WANConnectionDevice:1`
- Can be disabled with `-noupnp` launch arg
- UPnP flags: `Blaze::BlazeUpnpFlags`
- States: UPNP_ENABLED, UPNP_FOUND, UPNP_UNKNOWN

