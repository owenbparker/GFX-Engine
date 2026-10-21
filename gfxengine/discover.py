"""Finding GFX Engines on the network.

Each engine that allows the network says so every few seconds with a UDP
broadcast on DISCOVERY_PORT ({"app": "scc-gfx-engine", "name", "port"}),
and listens for the others'. Where broadcasts don't get through (some
switches and Wi-Fi), find() also tries every address on this PC's own
networks on the engine's port.
"""

import concurrent.futures
import ipaddress
import json
import socket
import threading
import time
import urllib.request

from .config import DISCOVERY_PORT

APP = "scc-gfx-engine"


def own_addresses():
    """This PC's IPv4 addresses on private networks."""
    found = set()
    try:
        found.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))   # (no traffic is sent)
            found.add(s.getsockname()[0])
    except OSError:
        pass
    out = []
    for a in found:
        try:
            ip = ipaddress.IPv4Address(a)
        except ValueError:
            continue
        if ip.is_private and not ip.is_loopback and not ip.is_link_local:
            out.append(str(ip))
    return sorted(out)


class Beacon:
    def __init__(self, info):
        """info() -> {"name", "port", "network"}: what to announce (nothing if network is off)."""
        self.info = info
        self.seen = {}   # "ip:port" -> {"ip", "port", "name", "version", "seen"}
        self.lock = threading.Lock()
        self._stop = threading.Event()
        threading.Thread(target=self._listen, daemon=True).start()
        threading.Thread(target=self._announce, daemon=True).start()

    def stop(self):
        self._stop.set()

    def engines(self):
        now = time.time()
        with self.lock:
            return sorted((dict(e) for e in self.seen.values() if now - e["seen"] < 15), key=lambda e: e["name"])

    def add(self, ip, port, name, version=""):
        with self.lock:
            self.seen[f"{ip}:{port}"] = {"ip": ip, "port": port, "name": name, "version": version,
                                         "url": f"http://{ip}:{port}", "seen": time.time()}

    def _announce(self):
        while not self._stop.wait(3):
            info = self.info()
            if not info.get("network"):
                continue
            msg = json.dumps({"app": APP, "name": info["name"], "port": info["port"],
                              "version": info.get("version", "")}).encode()
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                    if info.get("address"):   # (only on the network chosen)
                        s.bind((info["address"], 0))
                    s.sendto(msg, ("255.255.255.255", DISCOVERY_PORT))
            except OSError:
                pass

    def _listen(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", DISCOVERY_PORT))
            s.settimeout(1)
        except OSError:
            return   # another engine on this PC is listening; the scan still works
        mine = set(own_addresses()) | {"127.0.0.1"}
        while not self._stop.is_set():
            try:
                data, (ip, _) = s.recvfrom(2048)
                msg = json.loads(data)
            except (socket.timeout, ValueError, OSError):
                continue
            if msg.get("app") != APP:
                continue
            port = int(msg.get("port") or 0)
            if ip in mine and port == self.info().get("port"):
                continue   # ourselves
            self.add(ip, port, str(msg.get("name", ip))[:60], str(msg.get("version", "")))
        s.close()


def _open(ip, port, timeout):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except OSError:
        return False


def scan(port, timeout=0.35, only=""):
    """Engines answering on port on this PC's networks (each /24), or on the
    one network only (this PC's address on it)."""
    mine = set(own_addresses())
    candidates = []
    for a in sorted({only} if only else mine):
        net = ipaddress.IPv4Network(a + "/24", strict=False)
        candidates += [str(h) for h in net.hosts() if str(h) not in mine]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    found = []

    def check(ip):
        try:
            with opener.open(f"http://{ip}:{port}/api/hello", timeout=2) as r:
                hello = json.loads(r.read())
            return {"ip": ip, "port": port, **hello} if hello.get("app") == APP else None
        except Exception:
            return None
    with concurrent.futures.ThreadPoolExecutor(max_workers=128) as pool:
        open_ips = [ip for ip, ok in zip(candidates, pool.map(lambda ip: _open(ip, port, timeout), candidates)) if ok]
        found = [hit for hit in pool.map(check, open_ips) if hit]
    return found
