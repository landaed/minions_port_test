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
import runpy

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

# We need PB datatypes to be unjelly-able (deserializable)
from mud.world.shared.worlddata import WorldInfo, WorldConfig, NewCharacter, CharacterInfo
import mud.world.shared.playdata  # registers RootInfo, AllianceInfo, etc. with jelly
from mud.world.defines import (
    RPG_REALM_LIGHT, RPG_REALM_DARKNESS, RPG_REALM_MONSTER,
    RPG_PC_RACES, RPG_REALM_RACES, RPG_REALM_CLASSES, RPG_RACE_CLASSES,
    RPG_RACE_STATS, RPG_DEFAULT_STATS, RPG_STATS,
)


def _local_world_access_password(world_name):
    """Best-effort lookup for locally hosted player-world access passwords."""
    candidates = []
    if world_name:
        candidates.append(world_name)
        candidates.append(world_name.replace(" ", "_"))

    for candidate in candidates:
        path = os.path.join(os.getcwd(), "serverconfig", f"{candidate}.py")
        if not os.path.exists(path):
            continue
        try:
            data = runpy.run_path(path)
        except Exception:
            traceback.print_exc()
            continue
        password = data.get("PLAYERPASSWORD", "")
        if password:
            return password
    return ""


class ProxyPlayerMind(pb.Referenceable):
    """Minimal PB mind used when logging into a world as a player."""

    def __init__(self, session):
        self.session = session

    def remote_syncTime(self, hour, minute):
        self.session.send({"type": "world_time", "hour": hour, "minute": minute})
        return True

    def remote_messageBox(self, title, message):
        self.session.send(
            {
                "type": "error",
                "title": title,
                "message": message,
            }
        )
        return True

    def remote_setRootInfo(self, rootInfo, *args):
        self.session.send(
            {
                "type": "root_info",
                "message": "Received root info from world server.",
            }
        )
        return True

    def remote_setCursorItem(self, itemInfo):
        self.session.send(
            {
                "type": "cursor_item",
                "message": "Received cursor item from world server.",
            }
        )
        return True

    def remote_setZoneOptions(self, zoptions):
        self.session.send(
            {
                "type": "zone_options",
                "message": "Received zone options from world server.",
            }
        )
        return True

    def remote_setAllianceInfo(self, *args):
        self.session.send(
            {
                "type": "alliance_info",
                "message": "Received alliance info from world server.",
            }
        )
        return True

    def remote_setAllianceInvite(self, *args):
        self.session.send(
            {
                "type": "alliance_invite",
                "message": "Received alliance invite from world server.",
            }
        )
        return True

    def remote_jumpServer(self, wip, wport, wpassword, zport, zpassword, party):
        self.session.send(
            {
                "type": "zone_transfer",
                "world_ip": wip,
                "world_port": wport,
                "world_password": wpassword,
                "zone_port": zport,
                "zone_password": zpassword,
                "party": list(party) if party else [],
                "message": "Received enter-world handoff. Zone protocol work is the next milestone.",
            }
        )
        return True


class GodotClientSession:
    """Tracks the state of one connected Godot client."""

    def __init__(self, ws_protocol):
        self.ws = ws_protocol
        self.master_perspective = None
        self.new_world_perspective = None
        self.player_perspective = None
        self.player_mind = None
        self.username = None
        self.logged_in = False
        self.world_account_ready = False
        self.current_world = None
        self.cached_characters = []
        self.world_password = ""

    def send(self, msg_dict):
        """Send a JSON message to the Godot client."""
        try:
            payload = json.dumps(msg_dict)
            self.ws.sendMessage(payload.encode("utf-8"), isBinary=False)
        except Exception:
            traceback.print_exc()

    def cleanup(self):
        """Disconnect any PB connections."""
        for attr in ("master_perspective", "new_world_perspective", "player_perspective"):
            perspective = getattr(self, attr, None)
            if perspective:
                try:
                    perspective.broker.transport.loseConnection()
                except Exception:
                    pass
                setattr(self, attr, None)
        self.player_mind = None


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
            "create_world_account": self.handle_create_world_account,
            "world_login": self.handle_world_login,
            "query_characters": self.handle_query_characters,
            "create_character": self.handle_create_character,
            "enter_world": self.handle_enter_world,
            "direct_connect": self.handle_direct_connect,
        }.get(msg_type)

        if handler:
            handler(msg)
        else:
            self.session.send(
                {"type": "error", "message": f"Unknown message type: {msg_type}"}
            )

    def _close_perspective(self, attr_name):
        perspective = getattr(self.session, attr_name, None)
        if perspective:
            try:
                perspective.broker.transport.loseConnection()
            except Exception:
                pass
            setattr(self.session, attr_name, None)

    def _ensure_player_logged_in(self):
        if not self.session.player_perspective:
            self.session.send({
                "type": "error",
                "message": "Not logged into the selected world yet.",
            })
            return False
        return True

    @staticmethod
    def _character_info_to_dict(cinfo):
        klass = cinfo.klasses[0] if getattr(cinfo, "klasses", None) else ""
        level = cinfo.levels[0] if getattr(cinfo, "levels", None) else 0
        return {
            "name": cinfo.name,
            "race": cinfo.race,
            "realm": cinfo.realm,
            "realm_name": {
                RPG_REALM_LIGHT: "Light",
                RPG_REALM_DARKNESS: "Darkness",
                RPG_REALM_MONSTER: "Monster",
            }.get(cinfo.realm, str(cinfo.realm)),
            "klass": klass,
            "level": level,
            "status": cinfo.status,
            "rename": bool(getattr(cinfo, "rename", 0)),
            "klasses": list(getattr(cinfo, "klasses", [])),
            "levels": list(getattr(cinfo, "levels", [])),
        }

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

        factory = pb.PBClientFactory()
        reactor.connectTCP(MASTERIP, MASTERPORT, factory)

        hashed_pw = md5(b"Registration").digest()
        cred = UsernamePassword("Registration-Registration", hashed_pw)

        d = factory.login(cred, pb.Referenceable())
        d.addCallback(self._on_reg_connected, email, username)
        d.addErrback(self._on_reg_failed)

    def _on_reg_connected(self, perspective, email, username):
        d = perspective.callRemote("RegistrationAvatar", "submitKey", "", email, username, "MOM")
        d.addCallback(self._on_reg_result, perspective)
        d.addErrback(self._on_reg_failed)

    def _on_reg_result(self, result, perspective):
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

    def _do_enum_worlds(self, retries_left=3):
        p = self.session.master_perspective
        if not p:
            print("[Proxy] Skipping enumLiveWorlds retry because master perspective is gone.")
            return
        d = p.callRemote("EnumWorldsAvatar", "enumLiveWorlds", False, False, False, True)
        d.addCallback(self._on_worlds_received, retries_left)
        d.addErrback(self._on_worlds_failed)

    def _on_worlds_received(self, world_infos, retries_left=0):
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
        if len(worlds) == 0 and retries_left > 0:
            print(f"[Proxy] No worlds yet, retrying in 10s ({retries_left} retries left)")
            reactor.callLater(10, self._do_enum_worlds, retries_left - 1)
            return
        self.session.send({"type": "world_list", "worlds": worlds})

    def _on_worlds_failed(self, reason):
        msg = str(reason.value) if hasattr(reason, "value") else str(reason)
        print(f"[Proxy] Enum worlds failed: {msg}")
        self.session.send(
            {"type": "world_list", "worlds": [], "error": msg}
        )

    # ------------------------------------------------------------------
    # SELECT WORLD: connect to world as NewPlayer, query/create account
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
            self.session.send(
                {
                    "type": "world_connected",
                    "success": True,
                    "world_name": world_name,
                    "message": "Submitted to official world. Official-world login flow is not implemented in this proxy yet.",
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
        world_name = msg.get("world_name", "")
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

        self._close_perspective("new_world_perspective")
        self._close_perspective("player_perspective")
        self.session.player_mind = None
        self.session.world_account_ready = False
        self.session.cached_characters = []
        local_access_password = _local_world_access_password(world_name)
        self.session.current_world = {
            "name": world_name,
            "ip": ip,
            "port": int(port),
            "has_password": bool(msg.get("has_password", False)) or bool(local_access_password),
            "local_access_password": local_access_password,
        }

        if local_access_password:
            print(f"[Proxy] Local world access password discovered for {world_name} before NewPlayer connect.")

        factory = pb.PBClientFactory()
        reactor.connectTCP(ip, int(port), factory)

        hashed_pw = md5(b"").digest()
        cred = UsernamePassword("NewPlayer-NewPlayer", hashed_pw)
        d = factory.login(cred, pb.Referenceable())
        d.addCallback(self._on_new_world_connected, world_name)
        d.addErrback(self._on_world_connect_failed)

    def _on_new_world_connected(self, perspective, world_name):
        print(f"[Proxy] Connected to world as NewPlayer: {world_name}")
        self.session.new_world_perspective = perspective
        d = perspective.callRemote("NewPlayerAvatar", "queryPlayer", self.session.username)
        d.addCallback(self._on_query_player_result, world_name)
        d.addErrback(self._on_world_connect_failed)

    def _on_query_player_result(self, has_account, world_name):
        self.session.world_account_ready = bool(has_account)
        print(f"[Proxy] World account exists for {self.session.username} on {world_name}: {bool(has_account)}")
        message = "Existing world account found. Retrieving saved world password from Master Server..." if has_account else "No world account yet. Create one to continue."
        self.session.send(
            {
                "type": "world_connected",
                "success": True,
                "world_name": world_name,
                "has_world_account": bool(has_account),
                "requires_world_access_password": bool(self.session.current_world and self.session.current_world.get("has_password")),
                "message": message,
            }
        )
        if has_account and self.session.master_perspective:
            self._request_world_password(world_name)

        if self.session.current_world and self.session.current_world.get("has_password"):
            access_password = self.session.current_world.get("local_access_password", "") or _local_world_access_password(world_name)
            if access_password:
                self.session.current_world["local_access_password"] = access_password
                print(f"[Proxy] Local world access password discovered for {world_name}.")
                self.session.send({
                    "type": "world_access_password_result",
                    "success": True,
                    "world_name": world_name,
                    "world_access_password": access_password,
                    "message": "Recovered local world access password from serverconfig.",
                })

    def handle_create_world_account(self, msg):
        perspective = self.session.new_world_perspective
        if not perspective or not self.session.current_world:
            self.session.send({"type": "error", "message": "Select a world first."})
            return

        fantasy_name = msg.get("fantasy_name", "").strip().capitalize()
        player_password = msg.get("player_password", "").strip()

        if not player_password:
            player_password = self.session.current_world.get("local_access_password", "")

        if self.session.current_world.get("has_password") and not player_password:
            self.session.send(
                {
                    "type": "world_account_result",
                    "success": False,
                    "message": "This world requires its shared access password before a world account can be created.",
                }
            )
            return

        if len(fantasy_name) < 4 or not fantasy_name.isalpha():
            self.session.send(
                {
                    "type": "world_account_result",
                    "success": False,
                    "message": "Fantasy/avatar name must be at least 4 letters and alphabetic only.",
                }
            )
            return

        d = perspective.callRemote("NewPlayerAvatar", "newPlayer", self.session.username, fantasy_name, player_password)
        d.addCallback(self._on_create_world_account_result, fantasy_name)
        d.addErrback(self._on_world_connect_failed)

    def _request_world_password(self, world_name):
        d = self.session.master_perspective.callRemote("EnumWorldsAvatar", "requestWorldPassword", world_name)
        d.addCallback(self._on_world_password_result, world_name)
        d.addErrback(self._on_world_password_failed, world_name)

    def _on_world_password_result(self, result, world_name):
        print(f"[Proxy] World password lookup for {world_name}: {result}")
        if not isinstance(result, (tuple, list)) or len(result) < 2:
            self.session.send({
                "type": "world_password_result",
                "success": False,
                "message": f"Unexpected result: {result}",
            })
            return

        success = result[0] == 0
        password = result[2] if success and len(result) > 2 else ""
        if success:
            self.session.world_password = password
        self.session.send({
            "type": "world_password_result",
            "success": success,
            "world_name": world_name,
            "world_password": password,
            "message": result[1],
        })

    def _on_world_password_failed(self, reason, world_name):
        msg = str(reason.value) if hasattr(reason, "value") else str(reason)
        print(f"[Proxy] World password lookup failed for {world_name}: {msg}")
        self.session.send({
            "type": "world_password_result",
            "success": False,
            "world_name": world_name,
            "message": msg,
        })

    def _on_create_world_account_result(self, result, fantasy_name):
        if not isinstance(result, (tuple, list)) or len(result) < 2:
            self.session.send(
                {"type": "world_account_result", "success": False, "message": f"Unexpected result: {result}"}
            )
            return

        success = result[0] == 0
        world_password = result[2] if len(result) > 2 else ""
        print(f"[Proxy] World account result for {self.session.username}: {result}")
        if success:
            self.session.world_account_ready = True
            self.session.world_password = world_password
        self.session.send(
            {
                "type": "world_account_result",
                "success": success,
                "message": result[1],
                "fantasy_name": fantasy_name,
                "world_password": world_password,
            }
        )

    def handle_world_login(self, msg):
        if not self.session.current_world:
            self.session.send({"type": "error", "message": "Select a world first."})
            return

        world_password = msg.get("world_password", "").strip() or self.session.world_password
        role = msg.get("role", "Player").strip() or "Player"
        if role not in ("Player", "Guardian", "Immortal"):
            role = "Player"

        if not world_password:
            self.session.send(
                {"type": "player_login_result", "success": False, "message": "Missing world password."}
            )
            return

        self._close_perspective("player_perspective")
        self.session.player_mind = ProxyPlayerMind(self.session)

        factory = pb.PBClientFactory()
        reactor.connectTCP(self.session.current_world["ip"], self.session.current_world["port"], factory)
        hashed_pw = md5(world_password.encode()).digest()
        cred = UsernamePassword(f"{self.session.username}-{role}", hashed_pw)
        d = factory.login(cred, self.session.player_mind)
        d.addCallback(self._on_player_world_login, role)
        d.addErrback(self._on_player_world_login_failed)

    def _on_player_world_login(self, perspective, role):
        self.session.player_perspective = perspective
        self.session.send(
            {
                "type": "player_login_result",
                "success": True,
                "role": role,
                "message": "Logged into world as player.",
            }
        )
        self._do_query_characters()

    def _on_player_world_login_failed(self, reason):
        msg = str(reason.value) if hasattr(reason, "value") else str(reason)
        print(f"[Proxy] Player world login failed: {msg}")
        self.session.send(
            {"type": "player_login_result", "success": False, "message": msg}
        )

    def handle_query_characters(self, msg):
        if not self._ensure_player_logged_in():
            return
        self._do_query_characters()

    def _do_query_characters(self):
        d = self.session.player_perspective.callRemote("PlayerAvatar", "queryCharacters")
        d.addCallback(self._on_query_characters_result)
        d.addErrback(self._on_character_op_failed, "query_characters")

    def _on_query_characters_result(self, results):
        if len(results) == 2:
            cinfos, mspawns = results
            maxparty = 6
        else:
            cinfos, mspawns, maxparty = results

        characters = [self._character_info_to_dict(cinfo) for cinfo in cinfos]
        self.session.cached_characters = characters
        self.session.send(
            {
                "type": "character_list",
                "characters": characters,
                "monster_choices": list(mspawns),
                "max_party": maxparty,
            }
        )

    def handle_create_character(self, msg):
        if not self._ensure_player_logged_in():
            return

        name = msg.get("name", "").strip().capitalize()
        race = msg.get("race", "Human").strip() or "Human"
        klass = msg.get("klass", "Warrior").strip() or "Warrior"
        sex = msg.get("sex", "Male").strip() or "Male"
        look = int(msg.get("look", 0))
        realm = int(msg.get("realm", RPG_REALM_LIGHT))

        if len(name) < 4 or len(name) > 11 or not name.isalpha():
            self.session.send(
                {
                    "type": "create_character_result",
                    "success": False,
                    "message": "Character name must be 4-11 alphabetic letters.",
                }
            )
            return

        if race not in RPG_PC_RACES:
            self.session.send({
                "type": "create_character_result",
                "success": False,
                "message": f"Unsupported race: {race}",
            })
            return

        if race not in RPG_REALM_RACES.get(realm, []):
            self.session.send({
                "type": "create_character_result",
                "success": False,
                "message": f"Race {race} is not valid for this realm.",
            })
            return

        if klass not in RPG_RACE_CLASSES.get(race, []):
            self.session.send({
                "type": "create_character_result",
                "success": False,
                "message": f"Class {klass} is not valid for race {race}.",
            })
            return

        if klass not in RPG_REALM_CLASSES.get(realm, []):
            self.session.send({
                "type": "create_character_result",
                "success": False,
                "message": f"Class {klass} is not valid for this realm.",
            })
            return

        newchar = NewCharacter()
        newchar.name = name
        newchar.race = race
        newchar.klass = klass
        newchar.sex = sex
        newchar.look = max(0, min(2, look))
        newchar.realm = realm
        newchar.ptsRemaining = 0

        rstat = RPG_RACE_STATS[race]
        for stat in RPG_STATS:
            newchar.scores[stat] = getattr(rstat, stat)
            newchar.adjs[stat] = 0

        if klass in RPG_DEFAULT_STATS:
            for stat, value in zip(RPG_STATS, RPG_DEFAULT_STATS[klass]):
                newchar.adjs[stat] = value

        d = self.session.player_perspective.callRemote("PlayerAvatar", "newCharacter", newchar)
        d.addCallback(self._on_create_character_result, name)
        d.addErrback(self._on_character_op_failed, "create_character")

    def _on_create_character_result(self, result, name):
        if not isinstance(result, (tuple, list)) or len(result) < 2:
            self.session.send(
                {"type": "create_character_result", "success": False, "message": f"Unexpected result: {result}"}
            )
            return

        success = result[0] == 0
        self.session.send(
            {
                "type": "create_character_result",
                "success": success,
                "name": name,
                "message": result[1],
            }
        )
        if success:
            self._do_query_characters()

    def handle_enter_world(self, msg):
        if not self._ensure_player_logged_in():
            return

        character_name = msg.get("character_name", "").strip()
        if not character_name:
            self.session.send({"type": "error", "message": "Missing character_name."})
            return

        p = self.session.player_perspective
        print(f"[Proxy] enter_world: perspective={p}, character={character_name}")
        print(f"[Proxy] enter_world: perspective broker={p.broker if hasattr(p, 'broker') else 'N/A'}")
        if hasattr(p, 'broker') and hasattr(p.broker, 'transport'):
            peer = p.broker.transport.getPeer()
            print(f"[Proxy] enter_world: connected to {peer}")

        d = p.callRemote("PlayerAvatar", "enterWorld", [character_name], 0, "")
        d.addCallback(self._on_enter_world_result, character_name)
        d.addErrback(self._on_character_op_failed, "enter_world")

    def _on_enter_world_result(self, result, character_name):
        print(f"[Proxy] enter_world result: {result}")
        self.session.send(
            {
                "type": "enter_world_result",
                "success": True,
                "character_name": character_name,
                "message": "Enter-world request sent. Waiting for zone transfer / gameplay protocol bridge.",
                "result": str(result) if result is not None else None,
            }
        )

    def _on_character_op_failed(self, reason, op_name):
        msg = str(reason.value) if hasattr(reason, "value") else str(reason)
        print(f"[Proxy] {op_name} failed: {msg}")
        self.session.send(
            {"type": f"{op_name}_result", "success": False, "message": msg}
        )

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
        self._direct_connect_to_world({"ip": ip, "port": port, "world_name": world_name, "has_password": bool(msg.get("has_password", False))})


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
