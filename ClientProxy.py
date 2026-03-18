# ClientProxy.py - WebSocket <-> Twisted PB bridge for Godot client
# Run as T5: python3 ClientProxy.py gameconfig=mom.cfg
#
# This proxy sits between the Godot client (WebSocket on port 9000)
# and the MoM server stack (Twisted PB on port 2002+).
#
# Godot sends JSON messages, this proxy translates them into
# Twisted PB calls and sends JSON responses back.

import sys
import os
import json
import traceback

sys.path.append(os.getcwd())

from twisted.internet import reactor
from twisted.spread import pb
from twisted.cred.credentials import UsernamePassword

from autobahn.twisted.websocket import (
    WebSocketServerFactory,
    WebSocketServerProtocol,
)

from hashlib import md5

# Load game config to get master server IP/port
from mud.gamesettings import LoadGameConfiguration
LoadGameConfiguration()
from mud.gamesettings import MASTERIP, MASTERPORT

# We need WorldInfo to be unjelly-able (deserializable) by PB
from mud.world.shared.worlddata import WorldInfo, WorldConfig


class GodotClientSession:
    """Tracks the state of one connected Godot client."""

    def __init__(self, ws_protocol):
        self.ws = ws_protocol
        self.master_perspective = None
        self.world_perspective = None
        self.username = None
        self.logged_in = False

    def send(self, msg_dict):
        """Send a JSON message to the Godot client."""
        try:
            payload = json.dumps(msg_dict)
            self.ws.sendMessage(payload.encode("utf-8"), isBinary=False)
        except Exception:
            traceback.print_exc()

    def cleanup(self):
        """Disconnect any PB connections."""
        if self.master_perspective:
            try:
                self.master_perspective.broker.transport.loseConnection()
            except Exception:
                pass
            self.master_perspective = None
        if self.world_perspective:
            try:
                self.world_perspective.broker.transport.loseConnection()
            except Exception:
                pass
            self.world_perspective = None


class ProxyProtocol(WebSocketServerProtocol):
    """WebSocket protocol handler - one per Godot client connection."""

    def onOpen(self):
        self.session = GodotClientSession(self)
        print(f"[Proxy] Godot client connected: {self.peer}")

    def onClose(self, wasClean, code, reason):
        print(f"[Proxy] Godot client disconnected: {self.peer}")
        if hasattr(self, "session"):
            self.session.cleanup()

    def onMessage(self, payload, isBinary):
        if isBinary:
            return

        try:
            msg = json.loads(payload.decode("utf-8"))
        except json.JSONDecodeError:
            self.session.send({"type": "error", "message": "Invalid JSON"})
            return

        msg_type = msg.get("type", "")
        print(f"[Proxy] Received: {msg_type}")

        handler = {
            "login": self.handle_login,
            "register": self.handle_register,
            "enum_worlds": self.handle_enum_worlds,
            "select_world": self.handle_select_world,
            "direct_connect": self.handle_direct_connect,
        }.get(msg_type)

        if handler:
            handler(msg)
        else:
            self.session.send(
                {"type": "error", "message": f"Unknown message type: {msg_type}"}
            )

    # ------------------------------------------------------------------
    # LOGIN: Connect to MasterServer with username-Player + MD5(password)
    # ------------------------------------------------------------------
    def handle_login(self, msg):
        username = msg.get("username", "").strip()
        password = msg.get("password", "").strip()

        if not username or not password:
            self.session.send(
                {"type": "login_result", "success": False, "message": "Missing username or password."}
            )
            return

        self.session.username = username

        print(f"[Proxy] Login attempt: username='{username}', password='{password}' (len={len(password)})")

        factory = pb.PBClientFactory()
        reactor.connectTCP(MASTERIP, MASTERPORT, factory)

        hashed_pw = md5(password.encode()).digest()
        cred = UsernamePassword(f"{username}-Player", hashed_pw)

        d = factory.login(cred, pb.Referenceable())
        d.addCallback(self._on_master_connected)
        d.addErrback(self._on_master_failed)

    def _on_master_connected(self, perspective):
        print(f"[Proxy] Logged into MasterServer as {self.session.username}")
        self.session.master_perspective = perspective
        self.session.logged_in = True
        self.session.send(
            {"type": "login_result", "success": True, "message": "Logged in to Master Server."}
        )
        # Automatically enumerate worlds after login
        self._do_enum_worlds()

    def _on_master_failed(self, reason):
        msg = str(reason.value) if hasattr(reason, "value") else str(reason)
        print(f"[Proxy] Master login failed: {msg}")
        self.session.send(
            {"type": "login_result", "success": False, "message": msg}
        )

    # ------------------------------------------------------------------
    # REGISTER: Create a new account on the MasterServer
    # ------------------------------------------------------------------
    def handle_register(self, msg):
        email = msg.get("email", "").strip()
        username = msg.get("username", "").strip()

        if not email or not username:
            self.session.send(
                {"type": "register_result", "success": False, "message": "Missing email or username."}
            )
            return

        # Registration connects as a special "Registration" role user
        factory = pb.PBClientFactory()
        reactor.connectTCP(MASTERIP, MASTERPORT, factory)

        # The original client connects as "Registration-Registration" with
        # md5(b"Registration") as the password (see registerDlg.py line 132-134)
        hashed_pw = md5(b"Registration").digest()
        cred = UsernamePassword("Registration-Registration", hashed_pw)

        d = factory.login(cred, pb.Referenceable())
        d.addCallback(self._on_reg_connected, email, username)
        d.addErrback(self._on_reg_failed)

    def _on_reg_connected(self, perspective, email, username):
        # submitKey(regkey, email, publicName, fromProduct)
        # regkey is unused (generated server-side), fromProduct="MOM" grants premium
        d = perspective.callRemote("RegistrationAvatar", "submitKey", "", email, username, "MOM")
        d.addCallback(self._on_reg_result, perspective)
        d.addErrback(self._on_reg_failed)

    def _on_reg_result(self, result, perspective):
        # Result format: (status_code, message, password, regkey)
        try:
            perspective.broker.transport.loseConnection()
        except Exception:
            pass

        print(f"[Proxy] Registration result: {result}")

        if not isinstance(result, (tuple, list)):
            self.session.send(
                {"type": "register_result", "success": False, "message": f"Unexpected result: {result}"}
            )
            return

        if result[0] == 0:
            password = result[2] if len(result) > 2 else ""
            print(f"[Proxy] Registration successful! Password: '{password}'")
            self.session.send(
                {
                    "type": "register_result",
                    "success": True,
                    "message": result[1],
                    "password": password,
                }
            )
        else:
            self.session.send(
                {"type": "register_result", "success": False, "message": result[1]}
            )

    def _on_reg_failed(self, reason):
        msg = str(reason.value) if hasattr(reason, "value") else str(reason)
        self.session.send(
            {"type": "register_result", "success": False, "message": msg}
        )

    # ------------------------------------------------------------------
    # ENUM WORLDS: List available game worlds
    # ------------------------------------------------------------------
    def handle_enum_worlds(self, msg):
        if not self.session.logged_in or not self.session.master_perspective:
            self.session.send(
                {"type": "error", "message": "Not logged in."}
            )
            return
        self._do_enum_worlds()

    def _do_enum_worlds(self):
        p = self.session.master_perspective
        # callRemote("AvatarName", "methodName", args...)
        # The MasterPerspective dispatches: perspective_EnumWorldsAvatar("enumLiveWorlds", ...)
        d = p.callRemote("EnumWorldsAvatar", "enumLiveWorlds", False, False, False, True)
        d.addCallback(self._on_worlds_received)
        d.addErrback(self._on_worlds_failed)

    def _on_worlds_received(self, world_infos):
        worlds = []
        for wi in world_infos:
            worlds.append(
                {
                    "name": wi.worldName,
                    "ip": wi.worldIP,
                    "port": wi.worldPort,
                    "has_password": wi.hasPlayerPassword,
                    "has_zone_password": wi.hasZonePassword,
                    "allow_guests": wi.allowGuests,
                    "num_players": getattr(wi, "numLivePlayers", 0),
                    "max_players": getattr(wi, "maxPlayers", 0),
                }
            )
        print(f"[Proxy] Received {len(worlds)} worlds")
        self.session.send({"type": "world_list", "worlds": worlds})

    def _on_worlds_failed(self, reason):
        msg = str(reason.value) if hasattr(reason, "value") else str(reason)
        print(f"[Proxy] Enum worlds failed: {msg}")
        self.session.send(
            {"type": "world_list", "worlds": [], "error": msg}
        )

    # ------------------------------------------------------------------
    # SELECT WORLD: Connect to a player-hosted world server
    # ------------------------------------------------------------------
    def handle_select_world(self, msg):
        world_name = msg.get("world_name", "")
        if not world_name:
            self.session.send(
                {"type": "error", "message": "No world_name specified."}
            )
            return

        if not self.session.logged_in:
            self.session.send({"type": "error", "message": "Not logged in."})
            return

        # For official "Premium"/"Free" worlds, we'd use submitPlayerToWorld.
        # For player-hosted worlds, the original client connects directly
        # to the WorldServer as "NewPlayer-NewPlayer".
        # We check by name - if it's not an official server, direct connect.
        if "Premium " in world_name or "Free " in world_name:
            self._submit_to_official_world(world_name)
        else:
            self._direct_connect_to_world(msg)

    def _submit_to_official_world(self, world_name):
        p = self.session.master_perspective
        d = p.callRemote("PlayerAvatar", "submitPlayerToWorld", world_name)
        d.addCallback(self._on_player_submitted, world_name)
        d.addErrback(self._on_world_connect_failed)

    def _on_player_submitted(self, result, world_name):
        if result[0]:
            # Success - result[1] is a temporary password
            self.session.send(
                {
                    "type": "world_connected",
                    "success": True,
                    "world_name": world_name,
                    "message": "Submitted to world.",
                }
            )
        else:
            self.session.send(
                {
                    "type": "world_connected",
                    "success": False,
                    "message": result[1],
                }
            )

    def _direct_connect_to_world(self, msg):
        """Connect to a player-hosted world as NewPlayer."""
        world_name = msg.get("world_name", "")

        # Find world IP/port from cached world list
        ip = msg.get("ip", "")
        port = msg.get("port", 0)

        if not ip or not port:
            self.session.send(
                {
                    "type": "world_connected",
                    "success": False,
                    "message": "Missing world IP/port. Send ip and port with select_world.",
                }
            )
            return

        factory = pb.PBClientFactory()
        reactor.connectTCP(ip, int(port), factory)

        hashed_pw = md5(b"").digest()
        cred = UsernamePassword("NewPlayer-NewPlayer", hashed_pw)
        d = factory.login(cred, pb.Referenceable())
        d.addCallback(self._on_world_connected, world_name)
        d.addErrback(self._on_world_connect_failed)

    def _on_world_connected(self, perspective, world_name):
        print(f"[Proxy] Connected to world: {world_name}")
        self.session.world_perspective = perspective
        self.session.send(
            {
                "type": "world_connected",
                "success": True,
                "world_name": world_name,
                "message": "Connected to world server.",
            }
        )
        # TODO: Next step would be character enumeration/creation
        # perspective.callRemote("NewPlayerAvatar", "queryPlayer", charname)
        # perspective.callRemote("NewPlayerAvatar", "newPlayer", newchar_data)

    def _on_world_connect_failed(self, reason):
        msg = str(reason.value) if hasattr(reason, "value") else str(reason)
        print(f"[Proxy] World connect failed: {msg}")
        self.session.send(
            {"type": "world_connected", "success": False, "message": msg}
        )

    # ------------------------------------------------------------------
    # DIRECT CONNECT: Connect to a world by IP:port (skip master server)
    # ------------------------------------------------------------------
    def handle_direct_connect(self, msg):
        ip = msg.get("ip", "127.0.0.1")
        port = int(msg.get("port", 2006))
        world_name = msg.get("world_name", "DirectConnection")

        factory = pb.PBClientFactory()
        reactor.connectTCP(ip, port, factory)

        hashed_pw = md5(b"").digest()
        cred = UsernamePassword("NewPlayer-NewPlayer", hashed_pw)
        d = factory.login(cred, pb.Referenceable())
        d.addCallback(self._on_world_connected, world_name)
        d.addErrback(self._on_world_connect_failed)


def main():
    port = 9000
    print(f"[Proxy] Starting WebSocket proxy on ws://localhost:{port}")
    print(f"[Proxy] Will connect to MasterServer at {MASTERIP}:{MASTERPORT}")

    factory = WebSocketServerFactory(f"ws://localhost:{port}")
    factory.protocol = ProxyProtocol

    reactor.listenTCP(port, factory)
    print("[Proxy] Proxy is up. Waiting for Godot client connections...")
    reactor.run()


if __name__ == "__main__":
    main()
