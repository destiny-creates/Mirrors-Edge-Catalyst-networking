#!/usr/bin/env python3
"""
Mirror's Edge Catalyst - Community Blaze Redirector Server
==========================================================
Researched and reverse engineered by Destiny Creates
Replaces EA's winter15.gosredirector.ea.com

The game contacts the redirector over HTTPS to get the IP/port
of the actual Blaze game server. This server intercepts that
request and returns a community-hosted Blaze server address.

Reverse engineered by Destiny Creates from MirrorsEdgeCatalyst.exe (BlazeSDK 15.1.1.0.0)

Usage:
    python3 blaze_redirector_server.py --blaze-host 1.2.3.4 --blaze-port 10041

Then redirect winter15.gosredirector.ea.com to your server IP
via hosts file or DNS.
"""

import argparse
import json
import ssl
import sys
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# -----------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------
DEFAULT_BLAZE_HOST = "127.0.0.1"   # Community Blaze server IP
DEFAULT_BLAZE_PORT = 10041          # Blaze TCP port (insecure)
DEFAULT_BLAZE_PORT_SSL = 10042      # Blaze SSL port
DEFAULT_REDIRECTOR_PORT = 443       # Must be 443 (game hardcodes HTTPS)

# Blaze service/component IDs (from binary analysis)
SERVICE_NAME = "winter15"           # EA internal codename for MEC
COMPONENT_GAMEMANAGER = "gamemanager"
COMPONENT_AUTHENTICATION = "authentication"
COMPONENT_REDIRECTOR = "redirector"

# Topology: dedicated server (primary topology observed in binary)
TOPOLOGY_DEDICATED_SERVER = "CLIENT_SERVER_DEDICATED"


# -----------------------------------------------------------------------
# Redirector Response Builder
# -----------------------------------------------------------------------
def build_server_instance_response(blaze_host: str, blaze_port: int,
                                    blaze_port_ssl: int,
                                    service_name: str = SERVICE_NAME) -> dict:
    """
    Build a Blaze ServerInstance response.

    The game sends:
        POST /redirector/getServerInstance
        Body (heat2/TDF or JSON):
            serviceName = "winter15"
            clientVersion = "..."
            clientType = "CLIENT_TYPE_GAMEPLAY_USER"
            skuId = ...

    And expects back a ServerInstance with:
        - IP address of Blaze server
        - Secure (SSL) and insecure port
        - Instance name
    """
    return {
        "ServerInstance": {
            "address": {
                "IpAddress": {
                    "hostname": blaze_host,
                    "ip": blaze_host,
                    "port": blaze_port
                }
            },
            "secure": 0,          # 0 = use insecure port first
            "defaultDnsAddress": blaze_host,
            "name": f"community-{service_name}",
            "serviceName": service_name,
            "version": "15.1.1.0.0",  # Must match BlazeSDK version in client
            "type": "PRODUCTION"
        },
        "serverAddressInfo": {
            "ServerAddressType": "HOST_TARGET_ADDRESS",
            "ipAddress": blaze_host,
            "port": blaze_port,
            "securePort": blaze_port_ssl
        }
    }


# -----------------------------------------------------------------------
# HTTP Request Handler
# -----------------------------------------------------------------------
class RedirectorHandler(BaseHTTPRequestHandler):

    blaze_host = DEFAULT_BLAZE_HOST
    blaze_port = DEFAULT_BLAZE_PORT
    blaze_port_ssl = DEFAULT_BLAZE_PORT_SSL

    def log_message(self, fmt, *args):
        print(f"[Redirector] {self.address_string()} - {fmt % args}")

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/redirector/getServerInstance":
            self._handle_get_server_instance()
        else:
            self._send_404()

    def do_GET(self):
        # Handle QoS probe - game also hits /qos/qos, /qos/firewall, /qos/firetype
        parsed = urlparse(self.path)
        if parsed.path.startswith("/qos/"):
            self._handle_qos(parsed.path)
        else:
            self._send_404()

    def _handle_get_server_instance(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length) if length > 0 else b''
        print(f"[Redirector] getServerInstance request: {body[:200]}")

        response = build_server_instance_response(
            self.blaze_host,
            self.blaze_port,
            self.blaze_port_ssl
        )
        payload = json.dumps(response).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        print(f"[Redirector] Sent instance: {self.blaze_host}:{self.blaze_port}")

    def _handle_qos(self, path):
        # Minimal QoS response so the game doesn't block on QoS checks
        # The game hits these URLs during NAT detection:
        #   GET https://{qos_host}:{port}/qos/qos
        #   GET https://{qos_host}:{port}/qos/firewall
        #   GET https://{qos_host}:{port}/qos/firetype
        qos_response = {
            "result": "ok",
            "natType": "NAT_TYPE_OPEN",
            "firewallType": "FIREWALL_NONE"
        }
        payload = json.dumps(qos_response).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        print(f"[Redirector] Handled QoS probe: {path}")

    def _send_404(self):
        self.send_response(404)
        self.end_headers()


# -----------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description='Mirror\'s Edge Catalyst Community Redirector Server')
    parser.add_argument('--blaze-host', default=DEFAULT_BLAZE_HOST,
                        help='IP of community Blaze server')
    parser.add_argument('--blaze-port', type=int, default=DEFAULT_BLAZE_PORT,
                        help='TCP port of community Blaze server (default 10041)')
    parser.add_argument('--blaze-port-ssl', type=int, default=DEFAULT_BLAZE_PORT_SSL,
                        help='SSL port of community Blaze server (default 10042)')
    parser.add_argument('--listen-port', type=int, default=DEFAULT_REDIRECTOR_PORT,
                        help='Port to listen on (default 443)')
    parser.add_argument('--cert', default='redirector.crt',
                        help='TLS certificate file (PEM)')
    parser.add_argument('--key', default='redirector.key',
                        help='TLS private key file (PEM)')
    parser.add_argument('--no-tls', action='store_true',
                        help='Disable TLS (for testing only, game expects HTTPS)')
    args = parser.parse_args()

    # Inject config into handler class
    RedirectorHandler.blaze_host = args.blaze_host
    RedirectorHandler.blaze_port = args.blaze_port
    RedirectorHandler.blaze_port_ssl = args.blaze_port_ssl

    server = HTTPServer(('0.0.0.0', args.listen_port), RedirectorHandler)

    if not args.no_tls:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            ctx.load_cert_chain(args.cert, args.key)
        except FileNotFoundError:
            print(f"[!] TLS cert/key not found. Generate with:")
            print(f"    openssl req -x509 -newkey rsa:2048 -keyout redirector.key ")
            print(f"      -out redirector.crt -days 3650 -nodes ")
            print(f"      -subj '/CN=winter15.gosredirector.ea.com'")
            print(f"[!] Or use --no-tls for plaintext testing")
            sys.exit(1)
        server.socket = ctx.wrap_socket(server.socket, server_side=True)

    print(f"[Redirector] Listening on 0.0.0.0:{args.listen_port} "
          f"({'TLS' if not args.no_tls else 'PLAINTEXT'})")
    print(f"[Redirector] Routing clients to Blaze server: "
          f"{args.blaze_host}:{args.blaze_port} (SSL:{args.blaze_port_ssl})")
    print(f"[Redirector] Add to hosts file:")
    print(f"    <this-server-ip>  winter15.gosredirector.ea.com")
    print(f"    <this-server-ip>  gosca.ea.com")
    print(f"    <this-server-ip>  peach.online.ea.com")
    print(f"    <this-server-ip>  demangler.ea.com")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[Redirector] Shutting down.")


if __name__ == '__main__':
    main()
