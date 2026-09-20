from __future__ import annotations

import ipaddress
import os
import select
import socket
import socketserver


ALLOWED_HOSTS = frozenset(
    host.strip().lower()
    for host in os.environ.get(
        "CATALOG_INTAKE_ALLOWED_HOSTS", "github.com,api.github.com"
    ).split(",")
    if host.strip()
)
MAX_HEADER_BYTES = 16_384


def _allowed_addresses(host: str, port: int) -> list[tuple]:
    if host.lower() not in ALLOWED_HOSTS or port != 443:
        return []
    addresses: list[tuple] = []
    for family, socktype, proto, _canonname, sockaddr in socket.getaddrinfo(
        host, port, type=socket.SOCK_STREAM
    ):
        address = ipaddress.ip_address(sockaddr[0])
        if not address.is_global:
            continue
        addresses.append((family, socktype, proto, sockaddr))
    return addresses


class ProxyHandler(socketserver.BaseRequestHandler):
    def handle(self) -> None:
        self.request.settimeout(10)
        header = bytearray()
        while b"\r\n\r\n" not in header and len(header) < MAX_HEADER_BYTES:
            chunk = self.request.recv(4096)
            if not chunk:
                return
            header.extend(chunk)
        try:
            request_line = header.split(b"\r\n", 1)[0].decode("ascii")
            method, authority, _version = request_line.split(" ", 2)
            host, port_text = authority.rsplit(":", 1)
            port = int(port_text)
        except (UnicodeDecodeError, ValueError):
            self.request.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            return
        if method != "CONNECT":
            self.request.sendall(b"HTTP/1.1 405 Method Not Allowed\r\n\r\n")
            return
        addresses = _allowed_addresses(host, port)
        if not addresses:
            self.request.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
            return
        upstream = None
        for family, socktype, proto, sockaddr in addresses:
            candidate = socket.socket(family, socktype, proto)
            candidate.settimeout(10)
            try:
                candidate.connect(sockaddr)
                upstream = candidate
                break
            except OSError:
                candidate.close()
        if upstream is None:
            self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            return
        try:
            self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            sockets = [self.request, upstream]
            while True:
                readable, _, _ = select.select(sockets, [], [], 30)
                if not readable:
                    return
                for source in readable:
                    data = source.recv(65_536)
                    if not data:
                        return
                    (upstream if source is self.request else self.request).sendall(data)
        finally:
            upstream.close()


class ThreadingProxy(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main() -> None:
    with ThreadingProxy(("0.0.0.0", 8080), ProxyHandler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
