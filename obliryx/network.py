import http.client
import ipaddress
import socket
import ssl
from urllib.parse import urlsplit


def resolve_destination(host):
    records = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    addresses = [ipaddress.ip_address(record[4][0]) for record in records]
    if not addresses or any(not ip.is_global or ip.is_multicast or ip.is_reserved for ip in addresses):
        raise ValueError("Destinazione di rete non ammessa.")
    return str(addresses[0])


class DirectHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, host, ip, *, port=443, context=None):
        super().__init__(host, port=port, timeout=10, context=context or ssl.create_default_context())
        self.ip = ip

    def connect(self):
        raw = socket.create_connection((self.ip, self.port), timeout=self.timeout)
        try:
            self.sock = self._context.wrap_socket(raw, server_hostname=self.host)
        except BaseException:
            raw.close()
            raise


def post_form(url, ip, body):
    target = urlsplit(url)
    path = target.path or "/"
    if target.query:
        path += "?" + target.query
    connection = DirectHTTPSConnection(target.hostname, ip)
    try:
        connection.request("POST", path, body=body, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "Obliryx",
        })
        response = connection.getresponse()
        if 200 <= response.status < 300:
            return "accepted"
        if 300 <= response.status < 400:
            return "redirect_unfollowed"
        if 400 <= response.status < 500:
            return "rejected"
        return "delivery_unknown"
    except (OSError, http.client.HTTPException, ValueError):
        return "delivery_unknown"
    finally:
        connection.close()
