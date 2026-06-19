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
import random
import string

sys.path.append(os.getcwd())

from twisted.internet import reactor
from twisted.spread import pb
from twisted.cred.credentials import UsernamePassword

from autobahn.twisted.websocket import (
    WebSocketServerFactory,
    WebSocketServerProtocol,
)
from autobahn.exception import Disconnected

from hashlib import md5

# Stream enough nearby entities to make idle NPC wandering visible around town,
# while still bounding payload size. Override for profiling with
# MOM_ENTITY_STREAM_RADIUS=<units>.
ENTITY_STREAM_RADIUS = float(os.environ.get("MOM_ENTITY_STREAM_RADIUS", "120.0"))
ENTITY_STREAM_LIMIT = int(os.environ.get("MOM_ENTITY_STREAM_LIMIT", "50"))
# How often each client polls the world for a fresh entity snapshot. The old
# 0.03s (~33Hz) was the dominant cost with several clients: every poll the world
# server rebuilds + PB-serializes up to ENTITY_STREAM_LIMIT full entities, and
# the proxy re-serializes that to JSON and ships it. The Godot client
# interpolates between snapshots (ENTITY_INTERPOLATION_SPEED), so ~13Hz looks
# just as smooth while cutting server CPU and bandwidth ~2.5x. Tune with
# MOM_ENTITY_SYNC_INTERVAL (seconds).
ENTITY_SYNC_INTERVAL = float(os.environ.get("MOM_ENTITY_SYNC_INTERVAL", "0.075"))
# Per-entity fields that almost never change (identity, model, appearance, worn
# equipment, size). The proxy sends these only when they first appear or change
# for a given entity, and streams just the small dynamic remainder (position,
# rotation, health, combat flags) every snapshot. The Godot client merges each
# partial update onto its cached copy. This is the single biggest payload win
# for the proxy->client hop, which is the bandwidth-limited one on a VPS.
ENTITY_STATIC_FIELDS = (
    "name", "public_name", "race", "pclass", "sex", "model", "animation",
    "scale", "tex", "tex_single", "mounts", "realm", "is_player", "level",
    "max_health",
)
# Resend all static fields this often (seconds) so any client/proxy desync
# self-heals quickly. Cheap insurance — one "full" snapshot every few seconds.
ENTITY_STATIC_RESYNC = float(os.environ.get("MOM_ENTITY_STATIC_RESYNC", "4.0"))
# Toggles for the bandwidth optimizations (mostly for A/B profiling; leave on).
ENTITY_DELTA_ENABLED = os.environ.get("MOM_ENTITY_DELTA", "1") != "0"
ENTITY_ROUND_ENABLED = os.environ.get("MOM_ENTITY_ROUND", "1") != "0"

# Load game config to get master server IP/port
from mud.gamesettings import LoadGameConfiguration
LoadGameConfiguration()
from mud.gamesettings import MASTERIP, MASTERPORT

# We need PB datatypes to be unjelly-able (deserializable)
from mud.world.shared.worlddata import WorldInfo, WorldConfig, NewCharacter, CharacterInfo
import mud.world.shared.playdata  # registers RootInfo, AllianceInfo, etc. with jelly
from mud.world.shared.playdata import ItemInfo as _ServerItemInfo
from mud.world.shared.playdata import SpellInfo as _ServerSpellInfo


class ProxySpellInfoGhost(pb.RemoteCache):
    """Lightweight stand-in for the client's SpellInfoGhost.

    SpellInfo arrives on the wire as just {ID, LEVEL}; the real client ghost
    hydrates a dozen display columns from the local MoM client DB via
    mud.client.playermind (client-only imports that crash the headless proxy —
    same story as ItemInfo below). It fires for any character that has spells
    scribed, e.g. casters with auto-scribed starting spells. The proxy ships
    spellbook data through the plain-data getSpellbook getter instead, so the
    ghost only needs a name/icon for incidental JSON payloads.
    """

    def setCopyableState(self, state):
        self.__dict__.update(state)
        try:
            row = _baseline_db().execute(
                "SELECT name, spellbook_pic FROM spell_proto WHERE id = ? LIMIT 1;",
                (int(state.get("ID", 0)),)).fetchone()
            if row:
                self.BASENAME = self.NAME = str(row[0])
                self.SPELLBOOKPIC = str(row[1] or "")
        except Exception:
            pass

    def observe_updateChanged(self, state):
        self.__dict__.update(state)


pb.setUnjellyableForClass(_ServerSpellInfo, ProxySpellInfoGhost)


class ProxyItemInfoGhost(pb.RemoteCache):
    """Lightweight stand-in for the client's ItemInfoGhost.

    The real ItemInfoGhost.setCopyableState pulls static columns from the local
    MoM client DB via mud.client.playermind, which imports client-only modules
    (skillinfo, GUI) that don't exist in the headless proxy. That import blew up
    every loot/cursor ItemInfo, breaking the loot window. The wire state already
    carries the dynamic fields the Godot client needs (NAME, BITMAP, SLOT, ARMOR,
    STATS, FLAGS, LEVEL, WPNDAMAGE, QUALITY, ...), so just capture it verbatim.
    """

    def setCopyableState(self, state):
        self.__dict__.update(state)

    def observe_updateChanged(self, state):
        self.__dict__.update(state)


# Override playdata's registration so the proxy decodes ItemInfo with our ghost.
pb.setUnjellyableForClass(_ServerItemInfo, ProxyItemInfoGhost)


def _json_fallback(obj):
    """Fallback for json.dumps when encountering non-serializable objects."""
    if hasattr(obj, "__dict__"):
        return repr(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    return str(obj)


def _extract_state_mapping(obj):
    if obj is None:
        return {}
    if isinstance(obj, dict):
        return obj
    state = getattr(obj, "state", None)
    if isinstance(state, dict) and state:
        return state
    data = getattr(obj, "__dict__", None)
    if isinstance(data, dict) and data:
        return data
    return {}


def _get_first_attr(obj, *names, default=None):
    if obj is None:
        return default

    state = _extract_state_mapping(obj)
    for name in names:
        if name in state and state[name] is not None:
            return state[name]
        lname = name.lower()
        if lname in state and state[lname] is not None:
            return state[lname]
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value
        if hasattr(obj, lname):
            value = getattr(obj, lname)
            if value is not None:
                return value
    return default


def _serialize_rapid_mob_info(rapid_info):
    if not rapid_info:
        return {}
    fields = (
        "HEALTH", "MAXHEALTH", "MANA", "MAXMANA", "STAMINA", "MAXSTAMINA",
        "TGT", "TGTID", "TGTHEALTH", "PETNAME", "PETHEALTH", "AUTOATTACK", "CASTING",
    )
    data = {}
    for field in fields:
        value = _get_first_attr(rapid_info, field, field.lower())
        if value is not None:
            data[field.lower()] = value
    return data


def _serialize_character_cache(char_info):
    if not char_info:
        return {}

    fields = (
        ("name", ("NAME", "name")),
        ("race", ("RACE", "race")),
        ("sex", ("SEX", "sex")),
        ("realm", ("REALM", "realm")),
        ("pclass", ("PCLASS", "pclass")),
        ("sclass", ("SCLASS", "sclass")),
        ("tclass", ("TCLASS", "tclass")),
        ("plevel", ("PLEVEL", "plevel")),
        ("slevel", ("SLEVEL", "slevel")),
        ("tlevel", ("TLEVEL", "tlevel")),
        ("spawnid", ("SPAWNID", "spawnid")),
        ("charid", ("CHARID", "charid")),
        ("mobid", ("MOBID", "mobid")),
        ("dead", ("DEAD", "dead")),
        ("portraitpic", ("PORTRAITPIC", "portraitpic")),
        ("position", ("POSITION", "position")),
        # Core attributes + derived stats for the in-game character sheet.
        ("str", ("STR", "str")), ("dex", ("DEX", "dex")), ("ref", ("REF", "ref")),
        ("agi", ("AGI", "agi")), ("wis", ("WIS", "wis")), ("bdy", ("BDY", "bdy")),
        ("mnd", ("MND", "mnd")), ("mys", ("MYS", "mys")), ("pre", ("PRE", "pre")),
        ("str_base", ("STRBASE", "strBase")), ("dex_base", ("DEXBASE", "dexBase")),
        ("ref_base", ("REFBASE", "refBase")), ("agi_base", ("AGIBASE", "agiBase")),
        ("wis_base", ("WISBASE", "wisBase")), ("bdy_base", ("BDYBASE", "bdyBase")),
        ("mnd_base", ("MNDBASE", "mndBase")), ("mys_base", ("MYSBASE", "mysBase")),
        ("offense", ("OFFENSE", "offense")), ("defense", ("DEFENSE", "defense")),
        ("armor", ("ARMOR", "armor")),
        ("advancement_points", ("ADVANCE", "advancementPoints")),
        ("pxp_percent", ("PXPPERCENT", "pxpPercent")),
        ("sxp_percent", ("SXPPERCENT", "sxpPercent")),
        ("txp_percent", ("TXPPERCENT", "txpPercent")),
    )
    data = {}
    for output_name, attr_names in fields:
        value = _get_first_attr(char_info, *attr_names)
        if value is not None:
            data[output_name] = value

    skills = _get_first_attr(char_info, "SKILLS", "skills", default={}) or {}
    skill_reuse = _get_first_attr(char_info, "SKILLREUSE", "skillReuse", "skill_reuse", default={}) or {}

    abilities = []
    for name in sorted(skills.keys(), key=lambda value: str(value))[:8]:
        key = str(name)
        reuse_value = skill_reuse.get(key.upper(), skill_reuse.get(key))
        cooldown_seconds = 0
        if reuse_value is not None:
            try:
                cooldown_seconds = int(reuse_value)
            except (TypeError, ValueError):
                cooldown_seconds = 0
        abilities.append({
            "name": key,
            "rank": skills[name],
            "cooldown_active": key.upper() in skill_reuse or key in skill_reuse,
            "cooldown_seconds": cooldown_seconds,
            "source": "server",
        })

    rapid_info = _get_first_attr(char_info, "RAPIDMOBINFO", "rapidMobInfo")
    if rapid_info is None and hasattr(char_info, "character") and getattr(char_info.character, "mob", None):
        rapid_info = getattr(char_info, "rapidMobInfo", None) or getattr(char_info.character, "rapidMobInfo", None)

    data["abilities"] = abilities
    data["rapid_mob_info"] = _serialize_rapid_mob_info(rapid_info)
    data["name"] = data.get("name") or _get_first_attr(char_info, "NAME", "name", default="")
    data["pclass"] = data.get("pclass") or _get_first_attr(char_info, "PCLASS", "pclass", default="")
    data["level"] = data.get("plevel") or _get_first_attr(char_info, "PLEVEL", "plevel", default=1)
    return data


def _serialize_root_info(root_info, session):
    if not root_info:
        return {}

    char_info_map = _get_first_attr(root_info, "CHARINFOS", "charInfos", default={}) or {}
    if hasattr(char_info_map, "items"):
        sorted_infos = [value for _, value in sorted(char_info_map.items(), key=lambda item: item[0])]
    else:
        sorted_infos = list(char_info_map)

    char_infos = [_serialize_character_cache(value) for value in sorted_infos if value]

    # Replace the passive-skill placeholder ability list with the character's
    # real ACTIVE skills (Kick, Shield Bash, ...) fetched from the world server.
    # Passive proficiencies (1H Slash, Block) do nothing when "used", so showing
    # them on the ability bar made the hotkeys appear broken. Once the active
    # list has been fetched it always wins — even when it's legitimately empty
    # (a fresh caster has no active skills, just spells).
    active_skills = getattr(session, "active_skills", None)
    if char_infos and getattr(session, "active_skills_ready", False):
        char_infos[0]["abilities"] = [
            {
                "name": s.get("name", ""),
                "rank": s.get("rank", 1),
                "cooldown_active": bool(s.get("cooldown_active", False)),
                "cooldown_seconds": int(s.get("cooldown_seconds", 0) or 0),
                "icon": s.get("icon", ""),
                "source": "server",
            }
            for s in (active_skills or [])[:8]
        ]

    position = _get_first_attr(root_info, "POSITION", "position")
    if position is None:
        player = _get_first_attr(root_info, "player")
        if player is not None:
            sim_object = getattr(player, "simObject", None)
            position = getattr(sim_object, "position", None)
    position = list(position or (0, 0, 0))

    player_name = _get_first_attr(root_info, "PLAYERNAME", default=None)
    guild_name = _get_first_attr(root_info, "GUILDNAME", default=None)
    tin = _get_first_attr(root_info, "TIN", default=None)
    paused = _get_first_attr(root_info, "PAUSED", default=None)
    if any(value is None for value in (player_name, guild_name, tin, paused)):
        player = _get_first_attr(root_info, "player")
        if player is not None:
            if player_name is None:
                player_name = getattr(player, "name", "")
            if guild_name is None:
                guild_name = getattr(player, "guildName", "")
            if tin is None:
                tin = int(getattr(player, "tin", 0))
                tin += getattr(player, "copper", 0) * 100
                tin += getattr(player, "silver", 0) * 10000
                tin += getattr(player, "gold", 0) * 1000000
                tin += getattr(player, "platinum", 0) * 100000000
            if paused is None:
                paused = bool(getattr(getattr(player, "world", None), "paused", False))

    return {
        "player_name": player_name or "",
        "guild_name": guild_name or "",
        "tin": tin or 0,
        "paused": bool(paused),
        "position": position,
        "char_infos": char_infos,
        "world_name": session.current_world.get("name", "") if session.current_world else "",
    }

_BASELINE_DB = None


def _baseline_db():
    """Read-only connection to the shipped baseline world DB. The original MoM
    client kept a local copy of static tables (dialog_line text, journal_entry,
    item_proto, ...) and looked rows up by id; the proxy plays that role for the
    Godot client."""
    global _BASELINE_DB
    if _BASELINE_DB is None:
        import sqlite3
        path = os.path.join(os.getcwd(), "minions.of.mirth", "data", "worlds",
                            "multiplayer.baseline", "world.db")
        _BASELINE_DB = sqlite3.connect(path)
    return _BASELINE_DB


def _dialog_line_text(line_id):
    try:
        row = _baseline_db().execute(
            "SELECT text, journal_entry_id FROM dialog_line WHERE id = ? LIMIT 1;",
            (int(line_id),)).fetchone()
        if row:
            return str(row[0] or ""), int(row[1] or 0)
    except Exception:
        traceback.print_exc()
    return "", 0


def _journal_entry_row(entry_id):
    try:
        row = _baseline_db().execute(
            "SELECT topic, entry, text FROM journal_entry WHERE id = ? LIMIT 1;",
            (int(entry_id),)).fetchone()
        if row:
            return {"topic": str(row[0] or ""), "entry": str(row[1] or ""),
                    "text": str(row[2] or "")}
    except Exception:
        traceback.print_exc()
    return None


def _serialize_item_ghost(ghost):
    """Serialize a proxy ItemInfo ghost (UPPERCASE wire state in __dict__) to
    plain JSON data, filling proto name/slots from the baseline DB by PROTOID."""
    if ghost is None:
        return None
    if isinstance(ghost, dict):
        src = ghost
        get = lambda k, d=None: src.get(k, src.get(k.upper(), d))
    else:
        get = lambda k, d=None: getattr(ghost, k.upper(), d)
    stats = get("STATS") or []
    try:
        stats = [[str(s[0]), float(s[1])] for s in stats]
    except Exception:
        stats = []
    # The wire ItemInfo carries NAME etc. but not the proto's display name/slots;
    # resolve those from the baseline DB so the loot/vendor windows read fully.
    proto_id = get("PROTOID")
    name = str(get("NAME", "") or "")
    equip_slots = [int(s) for s in (get("SLOTS") or [])]
    if proto_id is not None:
        try:
            row = _baseline_db().execute(
                "SELECT name, bitmap FROM item_proto WHERE id = ? LIMIT 1;",
                (int(proto_id),)).fetchone()
            if row:
                if not name:
                    name = str(row[0] or "")
            if not equip_slots:
                equip_slots = [int(s[0]) for s in _baseline_db().execute(
                    "SELECT slot FROM item_slot WHERE item_proto_id = ?;",
                    (int(proto_id),))]
        except Exception:
            pass
    bitmap = str(get("BITMAP", "") or "")
    if not bitmap and proto_id is not None:
        try:
            row = _baseline_db().execute(
                "SELECT bitmap FROM item_proto WHERE id = ? LIMIT 1;",
                (int(proto_id),)).fetchone()
            if row:
                bitmap = str(row[0] or "")
        except Exception:
            pass
    return {
        "name": name,
        "slot": int(get("SLOT", -1) or -1),
        "stack_count": int(get("STACKCOUNT", 1) or 1),
        "stack_max": int(get("STACKMAX", 1) or 1),
        "use_charges": int(get("USECHARGES", 0) or 0),
        "use_max": int(get("USEMAX", 0) or 0),
        "quality": int(get("QUALITY", 0) or 0),
        "level": int(get("LEVEL", 1) or 1),
        "flags": int(get("FLAGS", 0) or 0),
        "armor": int(get("ARMOR", 0) or 0),
        "damage": float(get("WPNDAMAGE", 0) or 0),
        "delay": float(get("WPNRATE", 0) or 0),
        "wpn_range": float(get("WPNRANGE", 0) or 0),
        "bitmap": bitmap,
        "desc": str(get("DESC", "") or get("EFFECTDESC", "") or ""),
        "skill": str(get("SKILL", "") or ""),
        "worth_tin": int(get("WORTHTIN", 0) or 0),
        "stats": stats,
        "equip_slots": equip_slots,
        "repair": float(get("REPAIR", 0) or 0),
        "repair_max": float(get("REPAIRMAX", 0) or 0),
    }


class ProxyInteractPane(pb.Referenceable):
    """Stands in for the original client's InteractPane: the world server pushes
    follow-up dialog lines at it after each choice."""

    def __init__(self, session):
        self.session = session

    def remote_set(self, text, choices, journalEntryID=None):
        payload = {
            "type": "npc_dialog",
            "text": str(text or ""),
            "choices": [str(c) for c in (choices or [])],
        }
        if journalEntryID:
            entry = _journal_entry_row(journalEntryID)
            if entry:
                payload["journal"] = entry
        self.session.send(payload)
        return True

    def remote_close(self):
        self.session.send({"type": "npc_window_close"})
        return True


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

    def remoteMessageReceived(self, broker, message, args, kw):
        """Catch-all for unhandled remote_ methods to prevent NoSuchMethod errors."""
        method = getattr(self, "remote_%s" % message, None)
        if method is not None:
            return method(*broker.unserialize(args), **broker.unserialize(kw))
        # Silently accept unknown calls instead of raising NoSuchMethod
        return True

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
        self.session.root_info_cache = rootInfo
        payload = _serialize_root_info(rootInfo, self.session)
        payload.update(
            {
                "type": "root_info",
                "message": "Received root info from world server. Launching the local greybox test scene.",
            }
        )
        self.session.send(payload)
        self.session.start_gameplay_sync()
        self.session.start_entity_sync()
        self.session.start_skill_sync()
        return True

    def remote_receiveTextList(self, messages):
        text_messages = [str(message) for message in messages]
        self.session.send({
            "type": "text_messages",
            "messages": text_messages,
        })
        return True

    def remote_receiveGameText(self, textCode, text, stripML):
        self.session.send({
            "type": "game_text",
            "text_code": textCode,
            "text": str(text),
            "strip_ml": bool(stripML),
        })
        return True

    def remote_setTgtDesc(self, infoDict):
        payload = {str(key).lower(): value for key, value in dict(infoDict).items()}
        self.session.send({
            "type": "target_description",
            "target": payload,
        })
        return True

    def remote_setCursorItem(self, itemInfo):
        self.session.send({
            "type": "cursor_item",
            "item": _serialize_item_ghost(itemInfo),
        })
        # Cursor changes always accompany an inventory change; push a fresh
        # snapshot so the Godot inventory window stays exact.
        self.session.push_inventory()
        return True

    def remote_setZoneOptions(self, zoptions):
        self.session.send(
            {
                "type": "zone_options",
                "message": "Received zone options from world server.",
            }
        )
        return True

    def remote_connect(self, zconnect, fantasyName):
        # In stub/headless mode the world server creates the player's
        # simObject directly, so there is no zone server to connect to.
        # Just acknowledge receipt.
        self.session.send({
            "type": "zone_connect",
            "message": "Zone connection established (headless stub).",
        })
        return True

    def remote_checkEncounterSetting(self, *args):
        return True

    def remote_checkIgnore(self, *args):
        # The world asks a target's client whether it is ignoring the inviter
        # before delivering an alliance invite. We don't model an ignore list,
        # so always allow (False = not ignoring). Without this the invite path
        # errbacks and silently drops, so party invites never arrive.
        return False

    def remote_createServer(self, *args):
        return True

    def remote_setLoot(self, loot):
        items = {}
        try:
            for slot, info in dict(loot or {}).items():
                d = _serialize_item_ghost(info)
                if d is not None:
                    items[str(int(slot))] = d
        except Exception:
            traceback.print_exc()
        self.session.send({"type": "loot", "items": items})
        return True

    def remote_mouseSelect(self, charIndex, targetId):
        print(f"[Proxy] mouseSelect: char={charIndex}, mob_id={targetId}")
        self.session.send({
            "type": "mouse_select",
            "char_index": charIndex,
            "target_id": targetId,
        })
        return True

    def remote_setSelection(self, srcId, tgtId, charIndex):
        print(f"[Proxy] setSelection: src_sim={srcId}, tgt_sim={tgtId}, char={charIndex}")
        self.session.send({
            "type": "set_selection",
            "src_sim_id": srcId,
            "tgt_sim_id": tgtId,
            "char_index": charIndex,
        })
        return True

    def remote_startSelectron(self, ghostid):
        print(f"[Proxy] startSelectron: ghostid={ghostid}")
        return True

    def remote_stopSelectron(self):
        print(f"[Proxy] stopSelectron")
        return True

    def _forward_alliance_info(self, info):
        # Flatten an AllianceInfo ghost (PNAMES / NAMES / HEALTHS / MOBIDS, keyed
        # by member index) into a simple member list for the Godot client.
        members = []
        try:
            if info is not None:
                pnames = list(getattr(info, "PNAMES", []) or [])
                names = getattr(info, "NAMES", {}) or {}
                healths = getattr(info, "HEALTHS", {}) or {}
                mobids = getattr(info, "MOBIDS", {}) or {}

                def _first(d, i, default):
                    v = d.get(i)
                    if v is None:
                        v = d.get(str(i))
                    if isinstance(v, (list, tuple)) and v:
                        return v[0]
                    return default

                for x, pname in enumerate(pnames):
                    members.append({
                        "public_name": str(pname),
                        "name": str(_first(names, x, pname)),
                        "health_ratio": float(_first(healths, x, 1.0)),
                        "mob_id": int(_first(mobids, x, -1)),
                    })
        except Exception:
            traceback.print_exc()
        self.session.send({
            "type": "alliance_info",
            "members": members,
            "size": len(members),
        })

    def remote_setAllianceInfo(self, *args):
        # The world sends an AllianceInfo cacheable. Its ghost is updated in place
        # via observe_updateChanged when members/health change (e.g. someone joins
        # AFTER you), but that is not a fresh remote_ call — so hook it once to
        # re-forward, otherwise the alliance LEADER's panel never updates when a
        # new member joins.
        info = args[0] if args else None
        if info is not None and not getattr(info, "_proxy_hooked", False):
            try:
                info._proxy_hooked = True
                _orig = info.observe_updateChanged
                _fwd = self._forward_alliance_info

                def _hooked(changed, _orig=_orig, _info=info, _fwd=_fwd):
                    try:
                        _orig(changed)
                    except Exception:
                        pass
                    _fwd(_info)

                info.observe_updateChanged = _hooked
            except Exception:
                traceback.print_exc()
        self._forward_alliance_info(info)
        return True

    def remote_setAllianceInvite(self, *args):
        # arg is the leader's public name when invited, or None to clear.
        leader = args[0] if args else None
        self.session.send({
            "type": "alliance_invite",
            "from": str(leader) if leader else "",
            "pending": bool(leader),
        })
        return True

    def remote_setTracking(self, tracking):
        # Tracking data maps mob IDs to (name, position, range, type) tuples.
        # Just acknowledge receipt; the Godot client doesn't have a tracking window yet.
        return True

    def remote_setMuteTime(self, t):
        # Mute time for chat. Just acknowledge receipt.
        return True

    def remote_disturbEncounterSetting(self):
        # Called after skill/spell use. No-op for proxy client.
        return True

    def remote_playSound(self, sound, *args):
        # Sound playback request from server. Forward to Godot.
        self.session.send({"type": "play_sound", "sound": str(sound)})
        return True

    def remote_vocalize(self, sexcode, vset, vox, which):
        # Targeted vocal (e.g. your own character's death cry): decode the
        # vocalset path the same way the legacy client did, play as UI sound.
        from mud.world.stubsim import _vocal_filename
        filename = _vocal_filename(sexcode, vset, vox, which)
        if filename:
            self.session.send({"type": "play_sound", "sound": filename})
        return True

    def remote_beginCasting(self, charIndex, castTime):
        # Cast bar notification. Forward to Godot.
        self.session.send({"type": "begin_casting", "char_index": int(charIndex), "cast_time": float(castTime)})
        return True

    def remote_setCurCharIndex(self, index):
        # Switch active character in party. Just acknowledge.
        return True

    def remote_openNPCWnd(self, name, *args):
        banker = bool(args[0]) if args else False
        self.session.send({"type": "npc_window", "name": str(name), "banker": banker})
        return True

    def remote_closeNPCWnd(self):
        self.session.send({"type": "npc_window_close"})
        return True

    def remote_setVendorStock(self, isVendor, stock, markup):
        items = []
        if isVendor and stock:
            try:
                # The server sends {ItemInfo: index}; invert into an index-sorted list.
                by_index = sorted(dict(stock).items(), key=lambda kv: int(kv[1]))
                for info, index in by_index:
                    d = _serialize_item_ghost(info)
                    if d is not None:
                        d["vendor_index"] = int(index)
                        items.append(d)
            except Exception:
                traceback.print_exc()
        self.session.send({
            "type": "vendor_stock",
            "is_vendor": bool(isVendor),
            "items": items,
            "markup": float(markup or 1.0),
        })
        return True

    def remote_setInitialInteraction(self, dialogLine, choices, title=None):
        if dialogLine is None:
            self.session.send({"type": "npc_dialog_start", "has_dialog": False,
                               "npc": str(title or "")})
            return True
        text, journal_id = _dialog_line_text(dialogLine)
        payload = {
            "type": "npc_dialog_start",
            "has_dialog": True,
            "npc": str(title or ""),
            "text": text,
            "choices": [str(c) for c in (choices or [])],
        }
        if journal_id:
            entry = _journal_entry_row(journal_id)
            if entry:
                payload["journal"] = entry
        self.session.send(payload)
        return True

    def remote_addJournalEntry(self, journalEntryID):
        entry = _journal_entry_row(journalEntryID)
        if entry:
            self.session.send({"type": "journal_entry", **entry})
        return True

    def remote_openPetWindow(self):
        return True

    def remote_openAuction(self, *args):
        return True

    def remote_setItemSlot(self, *args):
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
        self.root_info_cache = None
        self.gameplay_sync_call = None
        self.entity_sync_call = None
        self.skill_sync_call = None
        self.active_skills = []
        self.active_skills_ready = False
        self.last_gameplay_payload = None
        self.last_entity_payload = None
        self.interact_pane = None
        self.world_login_retried = False
        self.player_dead = False  # last known death state (for death/alive edges)
        self.entity_static_sent = {}  # id -> signature of static block last sent
        self.entity_dyn_sent = {}     # id -> signature of dynamic block last sent
        self._static_resync_at = 0.0
        self._closed = False

    def push_inventory(self):
        """Fetch and forward a fresh plain-data inventory snapshot."""
        if self._closed or not self.player_perspective:
            return
        d = self.player_perspective.callRemote("PlayerAvatar", "getInventory", 0)
        d.addCallback(lambda inv: self.send({"type": "inventory", **(inv or {})}))
        d.addErrback(lambda f: None)

    def push_spellbook(self):
        """Fetch and forward the character's spellbook."""
        if self._closed or not self.player_perspective:
            return
        d = self.player_perspective.callRemote("PlayerAvatar", "getSpellbook", 0)
        d.addCallback(lambda sb: self.send({"type": "spellbook", **(sb or {})}))
        d.addErrback(lambda f: None)

    def push_loot(self):
        """Re-fetch the active loot table (slot indices shift after each take)."""
        if self._closed or not self.player_perspective:
            return
        d = self.player_perspective.callRemote("PlayerAvatar", "getLoot")
        d.addCallback(lambda lt: self.send({"type": "loot", **(lt or {"items": {}})}))
        d.addErrback(lambda f: None)

    def send(self, msg_dict):
        """Send a JSON message to the Godot client."""
        if self._closed:
            return
        try:
            payload = json.dumps(msg_dict, default=_json_fallback)
            self.ws.sendMessage(payload.encode("utf-8"), isBinary=False)
        except Disconnected:
            # Client went away (a sync callback can fire between close and
            # cleanup). Stop quietly instead of spewing a traceback.
            self._closed = True
            self.cleanup()
        except Exception:
            traceback.print_exc()

    def cleanup(self):
        """Disconnect any PB connections."""
        self._closed = True
        if self.gameplay_sync_call and self.gameplay_sync_call.active():
            self.gameplay_sync_call.cancel()
        if self.entity_sync_call and self.entity_sync_call.active():
            self.entity_sync_call.cancel()
        if self.skill_sync_call and self.skill_sync_call.active():
            self.skill_sync_call.cancel()
        self.gameplay_sync_call = None
        self.entity_sync_call = None
        self.skill_sync_call = None
        self.root_info_cache = None
        self.last_gameplay_payload = None
        self.last_entity_payload = None
        for attr in ("master_perspective", "new_world_perspective", "player_perspective"):
            perspective = getattr(self, attr, None)
            if perspective:
                try:
                    perspective.broker.transport.loseConnection()
                except Exception:
                    pass
                setattr(self, attr, None)
        self.player_mind = None

    def start_gameplay_sync(self):
        if self.gameplay_sync_call and self.gameplay_sync_call.active():
            return
        self.gameplay_sync_call = reactor.callLater(0.25, self._emit_gameplay_sync)

    def start_entity_sync(self):
        if self.entity_sync_call and self.entity_sync_call.active():
            return
        # Poll at ENTITY_SYNC_INTERVAL; the client interpolates between snapshots
        # so a moderate rate stays smooth while keeping server CPU + bandwidth in
        # check with multiple clients.
        self.entity_sync_call = reactor.callLater(ENTITY_SYNC_INTERVAL, self._emit_entity_sync)

    def start_skill_sync(self):
        if self.skill_sync_call and self.skill_sync_call.active():
            return
        # Active skills change rarely (level up / training) but cooldowns tick,
        # so a 1s poll keeps the ability bar's reuse timers reasonably fresh
        # without much overhead.
        self.skill_sync_call = reactor.callLater(1.0, self._emit_skill_sync)

    def _emit_skill_sync(self):
        self.skill_sync_call = None
        if not self.player_perspective or not self.root_info_cache:
            return
        d = self.player_perspective.callRemote("PlayerAvatar", "getActiveSkills", 0)
        d.addCallback(self._on_active_skills)
        d.addErrback(self._on_active_skills_failed)

    def _on_active_skills(self, skills):
        if isinstance(skills, (list, tuple)):
            self.active_skills = list(skills)
            self.active_skills_ready = True
        self.start_skill_sync()

    def _on_active_skills_failed(self, reason):
        # Keep whatever we had; just keep polling.
        self.start_skill_sync()

    def _emit_gameplay_sync(self):
        self.gameplay_sync_call = None
        if not self.root_info_cache:
            return
        payload = _serialize_root_info(self.root_info_cache, self)
        if payload != self.last_gameplay_payload:
            self.last_gameplay_payload = payload.copy()
            self.send({"type": "gameplay_state", **payload})
        self.start_gameplay_sync()

    def _push_gameplay_state_now(self):
        """Serialize + send the current root_info to the client immediately, without
        disturbing the periodic gameplay-sync timer. Used for event-driven updates
        (e.g. spending a stat point) so the character sheet reflects the change the
        instant the world server confirms it, instead of waiting for the next poll."""
        if not self.root_info_cache:
            return
        payload = _serialize_root_info(self.root_info_cache, self)
        if payload != self.last_gameplay_payload:
            self.last_gameplay_payload = payload.copy()
            self.send({"type": "gameplay_state", **payload})

    def _emit_entity_sync(self):
        self.entity_sync_call = None
        if not self.player_perspective or not self.root_info_cache:
            return
        d = self.player_perspective.callRemote("PlayerAvatar", "getVisibleEntities", 0)
        d.addCallback(self._on_entity_snapshot)
        d.addErrback(self._on_entity_snapshot_failed)

    def _on_entity_snapshot(self, entities):
        # New shape: {"entities": [...], "events": [...]} (zone visual events —
        # skill/spell animations, particles, explosions, 3D sounds). The bare
        # list shape is kept for compatibility with an older world server.
        events = []
        # Activity-driven replication: the world server sends only changed/new
        # entities plus an explicit "removed" list and a "full" flag (true on the
        # periodic resync). Legacy servers omit both, so full defaults True and the
        # client falls back to presence-based removal -> behaviour is unchanged.
        removed = []
        full_snapshot = True
        if isinstance(entities, dict):
            events = list(entities.get("events", []) or [])
            removed = list(entities.get("removed", []) or [])
            full_snapshot = bool(entities.get("full", True))
            # Death edge detection: getVisibleEntities returns {"dead": True} for a
            # dead character. Tell the client on the death->alive and alive->death
            # transitions so it can show / hide its death overlay.
            is_dead = bool(entities.get("dead", False))
            if is_dead and not self.player_dead:
                self.player_dead = True
                self.send({"type": "player_death"})
            elif not is_dead and self.player_dead:
                self.player_dead = False
                self.send({"type": "player_alive"})
            entities = entities.get("entities", [])
        if not isinstance(entities, (list, tuple)):
            print(f"[Proxy] entity_snapshot: unexpected type {type(entities).__name__}: {entities!r}")
            self.start_entity_sync()
            return
        entities = list(entities)

        # Keep self entity + up to 50 nearest non-self entities to limit payload size.
        self_entity = None
        others = []
        for e in entities:
            if isinstance(e, dict) and e.get("is_self"):
                self_entity = e
            else:
                others.append(e)
        others.sort(key=lambda e: float(e.get("distance", 999999)) if isinstance(e, dict) else 999999)
        # Only send nearby/relevant mobs. This used to be a hard 50-unit bubble,
        # which made the authored Trinst scene feel empty/static because many
        # town NPCs are visible but just outside that range. Keep the payload cap,
        # but use a wider configurable radius so idle wandering is actually seen.
        nearby = [e for e in others if isinstance(e, dict) and float(e.get("distance", 999999)) <= ENTITY_STREAM_RADIUS]
        capped = nearby[:ENTITY_STREAM_LIMIT]
        if self_entity:
            capped.insert(0, self_entity)

        debug_info = capped[0].get("_debug", "") if capped and isinstance(capped[0], dict) else ""
        if debug_info:
            print(f"[Proxy] entity_snapshot: {len(entities)} total, sending {len(capped)} | {debug_info}")
        elif len(capped) != getattr(self, '_last_entity_count', -1):
            print(f"[Proxy] entity_snapshot: {len(entities)} total, sending {len(capped)}")
            self._last_entity_count = len(capped)
        # Shorten the verbose float strings that dominate the dynamic payload
        # (a raw position component serializes as ~18 chars). 1cm / ~0.06deg
        # precision is far finer than the client's reconcile dead zone.
        if ENTITY_ROUND_ENABLED:
            for e in capped:
                if isinstance(e, dict):
                    pos = e.get("position")
                    if isinstance(pos, (list, tuple)):
                        e["position"] = [round(float(c), 2) for c in pos]
                    rot = e.get("rotation")
                    if isinstance(rot, (list, tuple)):
                        e["rotation"] = [round(float(c), 4) for c in rot]
        # Strip unchanged static fields (identity/model/appearance/equipment) so
        # only the small dynamic remainder goes over the wire to the client.
        capped = self._delta_compress_entities(capped, full=full_snapshot, removed=removed)
        # Always send — dedup was suppressing position/rotation updates. "full"
        # tells the client whether this is an authoritative set (erase absent) or
        # an activity delta (erase only the explicit "removed" ids).
        msg = {"type": "entity_snapshot", "entities": capped, "full": full_snapshot}
        if removed:
            msg["removed"] = removed
        if events:
            msg["events"] = events
        self.send(msg)
        # Lightweight send-rate meter (logs every 5s) so it's clear how fast
        # entity replication is actually running.
        import time as _t
        _now = _t.time()
        self._snap_n = getattr(self, "_snap_n", 0) + 1
        self._snap_bytes = getattr(self, "_snap_bytes", 0) + sum(len(json.dumps(e, default=_json_fallback)) for e in capped)
        if not hasattr(self, "_snap_t0"):
            self._snap_t0 = _now
        if _now - self._snap_t0 >= 5.0:
            dt = _now - self._snap_t0
            print("[Proxy] entity replication: %.1f snapshots/sec, %.1f KB/sec to client"
                  % (self._snap_n / dt, self._snap_bytes / 1024.0 / dt))
            self._snap_n = 0
            self._snap_bytes = 0
            self._snap_t0 = _now
        self.start_entity_sync()

    def _delta_compress_entities(self, entities, full=True, removed=None):
        """Drop static fields the client already has for each entity.

        Static identity/model/appearance/equipment is sent in full only when an
        entity first appears or when one of those fields changes; otherwise just
        the dynamic remainder (position/rotation/health/combat flags) is sent.
        Every ENTITY_STATIC_RESYNC seconds the whole static set is resent so any
        client/proxy drift self-heals. The Godot client merges each partial
        entity onto its cached copy (see gameplay_view.set_entities).

        Three tiers per entity:
          - static changed / first seen -> full entity,
          - only dynamic changed        -> dynamic fields only (no static),
          - nothing changed             -> just {id, sim_id} heartbeat.
        So an idle town NPC costs ~one field per snapshot instead of a full
        record every cycle. Proxy-internal fields (distance / visibility_source /
        _debug, used only for sorting + logging here) are never sent."""
        # Drop proxy-internal fields the client never reads.
        for e in entities:
            if isinstance(e, dict):
                e.pop("distance", None)
                e.pop("visibility_source", None)
                e.pop("_debug", None)
        if not ENTITY_DELTA_ENABLED:
            return entities
        import time as _t
        now = _t.time()
        full_resync = now - self._static_resync_at >= ENTITY_STATIC_RESYNC
        if full_resync:
            self.entity_static_sent.clear()
            self._static_resync_at = now
        out = []
        present = set()
        for e in entities:
            if not isinstance(e, dict):
                out.append(e)
                continue
            key = e.get("id", e.get("sim_id"))
            present.add(key)
            static = {k: e[k] for k in ENTITY_STATIC_FIELDS if k in e}
            dynamic = {k: v for k, v in e.items() if k not in ENTITY_STATIC_FIELDS}
            try:
                static_sig = json.dumps(static, sort_keys=True, default=_json_fallback)
                dyn_sig = json.dumps(dynamic, sort_keys=True, default=_json_fallback)
            except Exception:
                # Can't hash it reliably; just send the whole thing.
                out.append(e)
                continue
            if self.entity_static_sent.get(key) != static_sig:
                # New / changed identity/model/appearance -> full record.
                self.entity_static_sent[key] = static_sig
                self.entity_dyn_sent[key] = dyn_sig
                out.append(e)
            elif self.entity_dyn_sent.get(key) != dyn_sig:
                # Same identity, moved / took damage / flag flipped -> dynamic only.
                self.entity_dyn_sent[key] = dyn_sig
                out.append(dynamic)
            else:
                # Totally unchanged -> tiny heartbeat so the client keeps it.
                hb = {"id": e["id"]} if "id" in e else {}
                if "sim_id" in e:
                    hb["sim_id"] = e["sim_id"]
                out.append(hb if hb else dynamic)
        if full:
            # Authoritative set (legacy poll or periodic resync): anything we had
            # cached but isn't present has left range, so forget it -> it gets a
            # fresh full block when it returns.
            for key in [k for k in self.entity_static_sent if k not in present]:
                del self.entity_static_sent[key]
                self.entity_dyn_sent.pop(key, None)
        elif removed:
            # Activity delta: idle entities are intentionally absent and must be
            # kept; only the explicitly-removed (despawned) ones are forgotten.
            for key in removed:
                self.entity_static_sent.pop(key, None)
                self.entity_dyn_sent.pop(key, None)
        return out

    def _on_entity_snapshot_failed(self, reason):
        self.send({
            "type": "game_text",
            "text": "Entity replication snapshot failed: %s" % (str(reason.value) if hasattr(reason, "value") else str(reason)),
        })
        self.start_entity_sync()


class ProxyProtocol(WebSocketServerProtocol):
    """WebSocket protocol handler - one per Godot client connection."""

    def onConnect(self, request):
        # Disable Nagle so the (tiny) WebSocket handshake + JSON frames flush
        # immediately. Without this, small frames can sit in the TCP buffer on
        # Windows and the client appears to "hang" connecting/logging in.
        try:
            self.transport.setTcpNoDelay(True)
        except Exception:
            pass
        print(f"[Proxy] WebSocket handshake from {request.peer} (path={request.path})")
        return None

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
        # Suppress high-frequency player_input logging
        if msg_type != "gameplay_command" or msg.get("command") != "player_input":
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
            "leave_world": self.handle_leave_world,
            "direct_connect": self.handle_direct_connect,
            "gameplay_command": self.handle_gameplay_command,
            "cheat": self.handle_cheat,
        }.get(msg_type)

        if handler:
            try:
                handler(msg)
            except Exception as exc:
                traceback.print_exc()
                self.session.send({
                    "type": "error",
                    "message": f"{msg_type} failed: {exc}",
                })
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

    def _send_gameplay_command_result(self, success, command, message=""):
        if command in ("cycle_target", "attack_toggle", "use_ability", "target_entity"):
            print(f"[Proxy] gameplay_command_result: {command} success={success} msg={message}")
        self.session.send({
            "type": "gameplay_command_result",
            "success": bool(success),
            "command": command,
            "message": message,
        })

    def handle_gameplay_command(self, msg):
        if not self._ensure_player_logged_in():
            return

        command = str(msg.get("command", "")).strip().lower()
        if not command:
            self._send_gameplay_command_result(False, command, "Missing gameplay command.")
            return

        command_map = {
            "cycle_target": ("CYCLETARGET", ["0"]),
            "target_nearest": ("TARGETNEAREST", ["0"]),
            "interact": ("INTERACT", ["0"]),
            "attack_toggle": ("ATTACK", ["0", "TOGGLE"]),
            # Emotes — server broadcasts the matching playAnimation event.
            "emote_dance": ("DANCE", ["0"]),
            "emote_wave": ("WAVE", ["0"]),
            "emote_bow": ("BOW", ["0"]),
            "emote_point": ("POINT", ["0"]),
            "emote_agree": ("AGREE", ["0"]),
            # Pet commands (summoned/charmed pets): attack my target, stay,
            # follow me, stop fighting, dismiss.
            "pet_attack": ("PET", ["0", "ATTACK"]),
            "pet_stay": ("PET", ["0", "STAY"]),
            "pet_follow": ("PET", ["0", "FOLLOWME"]),
            "pet_back_off": ("PET", ["0", "STANDDOWN"]),
            "pet_dismiss": ("PET", ["0", "DISMISS"]),
            # Party/alliance: invite your CURRENT TARGET (another player) to your
            # alliance. Accept/decline/leave/disband are perspective calls below.
            "invite": ("INVITE", ["0"]),
        }

        payload = command_map.get(command)
        if payload is None and command == "use_ability":
            ability_name = str(msg.get("ability_name", "")).strip()
            if not ability_name:
                self._send_gameplay_command_result(False, command, "Missing ability name.")
                return
            payload = ("SKILL", ["0", *ability_name.split()])

        if payload is None and command == "target_entity":
            # entity_id 0 is a valid request: it clears the current target
            # (PlayerAvatar.targetEntity(0) -> setTargetById(mob, 0) -> no target).
            entity_id = int(msg.get("entity_id", 0) or 0)
            if entity_id < 0:
                self._send_gameplay_command_result(False, command, "Bad entity id.")
                return
            d = self.session.player_perspective.callRemote("PlayerAvatar", "targetEntity", entity_id, 0)
            label = ("Cleared target" if entity_id == 0 else f"Targeted entity {entity_id}") + " on legacy world server."
            d.addCallback(lambda result: self._send_gameplay_command_result(True, command, label))
            d.addErrback(self._on_gameplay_command_failed, command, "TARGET_ENTITY")
            return

        # Party/alliance accept/decline/leave/disband map to PlayerAvatar
        # perspective methods (no legacy COMMANDS entry). joinAlliance accepts a
        # pending invite; leaveDecline declines a pending invite OR leaves the
        # alliance you're in; disband breaks up an alliance you lead.
        if payload is None and command in (
                "accept_alliance", "join_alliance", "decline_alliance",
                "leave_alliance", "disband_alliance"):
            method = {
                "accept_alliance": "joinAlliance",
                "join_alliance": "joinAlliance",
                "decline_alliance": "leaveDecline",
                "leave_alliance": "leaveDecline",
                "disband_alliance": "disband",
            }[command]
            d = self.session.player_perspective.callRemote("PlayerAvatar", method)
            d.addCallback(lambda result: self._send_gameplay_command_result(
                True, command, f"{method} sent to legacy world server."))
            d.addErrback(self._on_gameplay_command_failed, command, method)
            return

        # Respawn a dead player at their bind point (PlayerAvatar.respawn). The
        # client sends this from its death overlay.
        if payload is None and command == "respawn":
            d = self.session.player_perspective.callRemote("PlayerAvatar", "respawn", 0)
            d.addCallback(lambda result: self._send_gameplay_command_result(
                bool(result), command,
                "Respawned at bind point." if result else "Nothing to respawn."))
            d.addErrback(self._on_gameplay_command_failed, command, "RESPAWN")
            return

        # Spend an advancement point to raise a core attribute (character sheet).
        if payload is None and command == "spend_stat_point":
            stat = str(msg.get("stat", "")).strip().lower()
            try:
                amount = max(1, int(msg.get("amount", 1) or 1))
            except (TypeError, ValueError):
                amount = 1
            d = self.session.player_perspective.callRemote("PlayerAvatar", "spendStatPoint", stat, amount)
            d.addCallback(self._on_stat_spent, command)
            d.addErrback(self._on_gameplay_command_failed, command, "SPEND_STAT_POINT")
            return

        if payload is None and self._handle_ui_command(command, msg):
            return

        if payload is None and command == "player_input":
            # Forward movement input state to the server for authoritative movement.
            # position_z is the client's collision-resolved vertical coordinate; the
            # headless stub has no Godot floor colliders, so this keeps replicated
            # multi-story/stair positions from flattening to the spawn Z.
            move_x = float(msg.get("move_x", 0))
            move_y = float(msg.get("move_y", 0))
            forward = msg.get("forward", [0, 0, 0])
            jump = bool(msg.get("jump", False))
            position_z = msg.get("position_z", None)
            flying = bool(msg.get("flying", False))
            d = self.session.player_perspective.callRemote(
                "PlayerAvatar", "updateInput", move_x, move_y, forward, jump, 0, position_z, flying
            )
            d.addErrback(lambda f: None)  # silently ignore errors on high-frequency input
            return

        if payload is None:
            self._send_gameplay_command_result(False, command, f"Unsupported gameplay command: {command}")
            return

        world_command, args = payload
        d = self.session.player_perspective.callRemote("PlayerAvatar", "doCommand", world_command, args)
        d.addCallback(lambda result: self._send_gameplay_command_result(True, command, f"Sent {world_command} to legacy world server."))
        d.addErrback(self._on_gameplay_command_failed, command, world_command)

    def _on_stat_spent(self, result, command):
        """Stat-point spend confirmed by the world server. Report the result, then —
        on success — flush the gameplay state to the client right away. The world
        server already refreshed the character's CharacterInfo before returning, so
        the cached ghost holds the new attribute values by the time this fires (PB
        preserves message order on the broker), making the sheet update immediate."""
        success = bool(result.get("success")) if isinstance(result, dict) else False
        message = result.get("message", "") if isinstance(result, dict) else ""
        self._send_gameplay_command_result(success, command, message)
        if success:
            self.session._push_gameplay_state_now()

    def _on_gameplay_command_failed(self, reason, command, world_command):
        msg = str(reason.value) if hasattr(reason, "value") else str(reason)
        self._send_gameplay_command_result(False, command, f"{world_command} failed: {msg}")

    def handle_cheat(self, msg):
        """Testing cheats (give XP / level / money / items / spells / skills).

        Forwarded to PlayerAvatar.perspective_cheat; the world server refuses
        unless it runs with MOM_ENABLE_CHEATS=1. After mutating actions the
        proxy re-pushes inventory + spellbook so the client UI updates."""
        if not self._ensure_player_logged_in():
            return
        action = str(msg.get("action", "")).strip()
        params = msg.get("params", {})
        if not isinstance(params, dict):
            params = {}
        session = self.session

        def on_result(result):
            if not isinstance(result, dict):
                result = {"success": False, "message": str(result)}
            session.send({"type": "cheat_result", "action": action, **result})
            if result.get("success") and action in (
                    "give_item", "give_money", "learn_spell", "learn_class_spells",
                    "give_xp", "set_level", "raise_skills", "full_heal"):
                session.push_inventory()
                session.push_spellbook()

        d = session.player_perspective.callRemote("PlayerAvatar", "cheat", action, params)
        d.addCallback(on_result)
        d.addErrback(lambda f: session.send({
            "type": "cheat_result", "action": action, "success": False,
            "message": str(f.value) if hasattr(f, "value") else str(f)}))

    def _handle_ui_command(self, command, msg):
        """Inventory / loot / dialog / vendor / spellbook bridge commands.

        Returns True when the command was recognized (whether or not it
        ultimately succeeds server-side)."""
        session = self.session
        perspective = session.player_perspective

        def call(method, *args, refresh_inventory=False, refresh_spellbook=False):
            d = perspective.callRemote("PlayerAvatar", method, *args)
            if refresh_inventory:
                d.addCallback(lambda _r: session.push_inventory())
            if refresh_spellbook:
                d.addCallback(lambda _r: session.push_spellbook())
            d.addErrback(self._on_gameplay_command_failed, command, method.upper())
            return d

        if command == "get_inventory":
            session.push_inventory()
            return True
        if command == "get_spellbook":
            session.push_spellbook()
            return True
        if command == "inv_click":
            call("onInvSlot", int(msg.get("char_id", 0)), int(msg.get("slot", -1)),
                 refresh_inventory=True)
            return True
        if command == "inv_click_alt":
            call("onInvSlotAlt", int(msg.get("char_id", 0)), int(msg.get("slot", -1)),
                 refresh_inventory=True)
            return True
        if command == "inv_use":
            call("onInvSlotCtrl", int(msg.get("char_id", 0)), int(msg.get("slot", -1)),
                 refresh_inventory=True, refresh_spellbook=True)
            return True
        if command == "destroy_cursor":
            call("expungeItem", refresh_inventory=True)
            return True
        if command == "select_entity":
            call("selectEntity", int(msg.get("entity_id", 0)), 0,
                 bool(msg.get("double_click", False)), bool(msg.get("shift", False)))
            return True
        if command == "loot_item":
            d = call("loot", 0, int(msg.get("slot", 0)), bool(msg.get("alt", True)),
                     refresh_inventory=True)
            d.addCallback(lambda _r: session.push_loot())
            return True
        if command == "end_looting":
            call("endLooting")
            return True
        if command == "destroy_corpse":
            call("destroyCorpse")
            return True
        if command == "dialog_choice":
            if session.interact_pane is None:
                session.interact_pane = ProxyInteractPane(session)
            call("onInteractionChoice", int(msg.get("index", 0)), session.interact_pane,
                 refresh_inventory=True)
            return True
        if command == "end_interaction":
            call("endInteraction")
            return True
        if command == "buy_item":
            call("buyItem", 0, int(msg.get("index", 0)), refresh_inventory=True)
            return True
        if command == "sell_item":
            call("sellItem", 0, int(msg.get("slot", 0)), refresh_inventory=True)
            return True
        if command == "spell_slot":
            # Cast (or memorize a scroll into) a spellbook slot.
            call("onSpellSlot", int(msg.get("char_id", 0)), int(msg.get("slot", 0)),
                 refresh_spellbook=True)
            return True
        if command == "spell_slot_swap":
            call("onSpellSlotSwap", int(msg.get("char_id", 0)),
                 int(msg.get("src", 0)), int(msg.get("dest", 0)),
                 refresh_spellbook=True)
            return True
        return False

    @staticmethod
    def _character_info_to_dict(cinfo):
        from mud.world import defines as world_defines

        klass = cinfo.klasses[0] if getattr(cinfo, "klasses", None) else ""
        level = cinfo.levels[0] if getattr(cinfo, "levels", None) else 0
        realm_labels = {
            int(getattr(world_defines, "RPG_REALM_LIGHT", 1)): "Light",
            int(getattr(world_defines, "RPG_REALM_DARKNESS", 2)): "Darkness",
            int(getattr(world_defines, "RPG_REALM_MONSTER", 3)): "Monster",
        }
        return {
            "name": cinfo.name,
            "race": cinfo.race,
            "sex": getattr(cinfo, "sex", "Male"),
            "realm": cinfo.realm,
            "realm_name": realm_labels.get(cinfo.realm, str(cinfo.realm)),
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
        # Optional: let the player choose their own account password. If empty,
        # the master server assigns a random one (legacy behaviour).
        desired_password = msg.get("password", "").strip()

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
        d.addCallback(self._on_reg_connected, email, username, desired_password)
        d.addErrback(self._on_reg_failed)

    def _on_reg_connected(self, perspective, email, username, desired_password=""):
        d = perspective.callRemote("RegistrationAvatar", "submitKey", "", email, username, "MOM", desired_password)
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
        self.session.world_login_retried = False
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
        # Auto-handle the world account so the player never has to deal with the
        # separate "fantasy name" + world-account password. Selecting a world
        # now goes straight to character selection.
        self.session.send({
            "type": "world_connected",
            "success": True,
            "world_name": world_name,
            "has_world_account": bool(has_account),
            "auto": True,
            "message": "Setting up your world character slot...",
        })
        # A logout extracts the player to the character server and removes the
        # world-local copy, so "no local account" usually means "returning
        # player" — restore the saved buffer (keeps log position, bank, guild)
        # and only fall back to creating a brand-new world account when there
        # is truly nothing saved.
        self._restore_world_player(world_name)

    def _restore_world_player(self, world_name):
        perspective = self.session.new_world_perspective
        if not perspective:
            self.session.send({"type": "player_login_result", "success": False,
                               "message": "Lost world connection before login."})
            return
        d = perspective.callRemote("NewPlayerAvatar", "restorePlayer", self.session.username)
        d.addCallback(self._on_restore_player, world_name)
        d.addErrback(self._on_restore_player_failed, world_name)

    def _on_restore_player(self, result, world_name):
        ok = (isinstance(result, (tuple, list)) and len(result) >= 3
              and result[0] == 0 and result[2])
        if ok:
            print(f"[Proxy] Restored saved world player for {self.session.username} on {world_name}.")
            self.session.world_account_ready = True
            self.session.world_password = result[2]
            self._do_world_login(result[2])
            return
        msg = result[1] if isinstance(result, (tuple, list)) and len(result) > 1 else result
        print(f"[Proxy] No saved world player to restore ({msg}); creating a fresh world account.")
        self._auto_create_world_account(world_name)

    def _on_restore_player_failed(self, reason, world_name):
        # Older world servers don't implement restorePlayer — keep the legacy
        # auto-create path working.
        msg = str(reason.value) if hasattr(reason, "value") else str(reason)
        print(f"[Proxy] restorePlayer unavailable/failed ({msg}); falling back to world account setup.")
        if self.session.world_account_ready and self.session.master_perspective:
            self._request_world_password(world_name)
        else:
            self._auto_create_world_account(world_name)

    def _derive_fantasy_name(self, salt=""):
        """A world 'avatar name' is required (>=4 alpha chars, unique per world)
        but the player shouldn't care about it — derive one from the username."""
        import re as _re
        base = _re.sub(r'[^A-Za-z]', '', self.session.username or "") or "Hero"
        base = (base + "hero")[:10] if len(base) < 4 else base
        name = (base + salt)[:16]
        return name.capitalize()

    def _auto_create_world_account(self, world_name, attempt=0):
        perspective = self.session.new_world_perspective
        if not perspective:
            self.session.send({"type": "player_login_result", "success": False,
                               "message": "Lost world connection before creating account."})
            return
        access_pw = (self.session.current_world.get("local_access_password", "")
                     or _local_world_access_password(world_name) or "")
        salt = "".join(random.choice(string.ascii_lowercase) for _ in range(3)) if attempt else ""
        fantasy = self._derive_fantasy_name(salt)
        print(f"[Proxy] Auto-creating world account for {self.session.username} as '{fantasy}'")
        d = perspective.callRemote("NewPlayerAvatar", "newPlayer", self.session.username, fantasy, access_pw)
        d.addCallback(self._on_auto_world_account, world_name, attempt)
        d.addErrback(self._on_world_connect_failed)

    def _on_auto_world_account(self, result, world_name, attempt):
        ok = isinstance(result, (tuple, list)) and len(result) >= 2 and result[0] == 0
        if ok:
            self.session.world_account_ready = True
            self.session.world_password = result[2] if len(result) > 2 else ""
            print(f"[Proxy] Auto world account created; logging into world.")
            self._do_world_login(self.session.world_password)
            return
        # Public name taken -> retry with a random suffix a few times.
        msg = result[1] if isinstance(result, (tuple, list)) and len(result) > 1 else str(result)
        if "taken" in str(msg).lower() and attempt < 4:
            self._auto_create_world_account(world_name, attempt + 1)
            return
        self.session.send({"type": "player_login_result", "success": False,
                           "message": f"Could not set up world character slot: {msg}"})

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
        if success and password:
            # Auto-login with the recovered world password.
            self.session.world_password = password
            self._do_world_login(password)
        else:
            # Account record exists but no saved password (inconsistent state) —
            # set one up automatically rather than dead-ending the player.
            print(f"[Proxy] No saved world password for {world_name}; auto-creating slot.")
            self._auto_create_world_account(world_name)

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
        self._do_world_login(world_password, role)

    def _do_world_login(self, world_password, role="Player"):
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
        self.session.world_login_retried = False
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
        # Reconnecting quickly can race the server-side teardown of the
        # previous session (the kick extracts the player and recreates the
        # account record).  One delayed retry through the restore path makes
        # "quit and immediately relaunch" reliable.
        if (not getattr(self.session, "world_login_retried", False)
                and self.session.current_world and self.session.new_world_perspective):
            self.session.world_login_retried = True
            world_name = self.session.current_world["name"]
            print(f"[Proxy] Retrying world login once via restore for {world_name}...")
            reactor.callLater(1.5, self._restore_world_player, world_name)
            return
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

        from mud.world import defines as world_defines

        default_realm = int(getattr(world_defines, "RPG_REALM_LIGHT", 1))
        pc_races = tuple(getattr(world_defines, "RPG_PC_RACES", ()))
        realm_races = dict(getattr(world_defines, "RPG_REALM_RACES", {}))
        realm_classes = dict(getattr(world_defines, "RPG_REALM_CLASSES", {}))
        race_classes = dict(getattr(world_defines, "RPG_RACE_CLASSES", {}))
        race_stats = dict(getattr(world_defines, "RPG_RACE_STATS", {}))
        default_stats = dict(getattr(world_defines, "RPG_DEFAULT_STATS", {}))
        stats = tuple(getattr(world_defines, "RPG_STATS", ()))

        name = str(msg.get("name", "")).strip().capitalize()
        race = str(msg.get("race", "Human")).strip() or "Human"
        klass = str(msg.get("klass", "Warrior")).strip() or "Warrior"
        sex = str(msg.get("sex", "Male")).strip() or "Male"
        try:
            look = int(msg.get("look", 0))
        except (TypeError, ValueError):
            look = 0
        try:
            realm = int(msg.get("realm", default_realm))
        except (TypeError, ValueError):
            self.session.send({
                "type": "create_character_result",
                "success": False,
                "message": f"Invalid realm: {msg.get('realm')}",
            })
            return

        if len(name) < 4 or len(name) > 11 or not name.isalpha():
            self.session.send(
                {
                    "type": "create_character_result",
                    "success": False,
                    "message": "Character name must be 4-11 alphabetic letters.",
                }
            )
            return

        if race not in pc_races:
            self.session.send({
                "type": "create_character_result",
                "success": False,
                "message": f"Unsupported race: {race}",
            })
            return

        if race not in realm_races.get(realm, []):
            self.session.send({
                "type": "create_character_result",
                "success": False,
                "message": f"Race {race} is not valid for this realm.",
            })
            return

        if klass not in race_classes.get(race, []):
            self.session.send({
                "type": "create_character_result",
                "success": False,
                "message": f"Class {klass} is not valid for race {race}.",
            })
            return

        if klass not in realm_classes.get(realm, []):
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

        rstat = race_stats[race]
        for stat in stats:
            newchar.scores[stat] = getattr(rstat, stat)
            newchar.adjs[stat] = 0

        if klass in default_stats:
            for stat, value in zip(stats, default_stats[klass]):
                newchar.adjs[stat] = value

        # Player-allocated starting bonus points (from character creation): add to
        # the class adjustments so they raise the starting base stats. Capped to
        # the pool the client offers so it can't be abused by a crafted message.
        bonus = msg.get("bonus", {})
        if isinstance(bonus, dict):
            bonus_cap = 10
            spent = 0
            for stat in stats:
                try:
                    amt = max(0, int(bonus.get(stat.lower(), 0) or 0))
                except (TypeError, ValueError):
                    amt = 0
                if amt <= 0:
                    continue
                if spent + amt > bonus_cap:
                    amt = max(0, bonus_cap - spent)
                spent += amt
                newchar.adjs[stat] = int(newchar.adjs.get(stat, 0)) + amt

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

    def handle_leave_world(self, msg):
        """Return to character select: stop streaming + clear gameplay caches but
        keep the player/world perspective so the client can re-enter a character."""
        session = self.session
        for attr in ("gameplay_sync_call", "entity_sync_call", "skill_sync_call"):
            call = getattr(session, attr, None)
            try:
                if call and call.active():
                    call.cancel()
            except Exception:
                pass
            setattr(session, attr, None)
        session.root_info_cache = None
        session.last_gameplay_payload = None
        session.last_entity_payload = None
        session.player_dead = False
        session.entity_static_sent = {}
        session.entity_dyn_sent = {}
        session.send({"type": "left_world", "success": True})

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
    # Real-time logs even when stdout is block-buffered (Windows consoles).
    try:
        sys.stdout.reconfigure(line_buffering=True)
        sys.stderr.reconfigure(line_buffering=True)
    except Exception:
        pass

    # Port and bind interface are configurable so a host can expose the proxy to
    # the internet (port-forward this port). Defaults: listen on ALL interfaces
    # (0.0.0.0) so remote clients can reach it — not just localhost.
    port = int(os.environ.get("MOM_PROXY_PORT", "9000"))
    bind = os.environ.get("MOM_PROXY_BIND", "0.0.0.0")

    print(f"[Proxy] Starting WebSocket proxy, listening on {bind}:{port} "
          f"(clients connect to ws://<this-host>:{port})")
    print(f"[Proxy] Will connect to MasterServer at {MASTERIP}:{MASTERPORT} "
          f"(the proxy reaches the master/world locally; only port {port} needs "
          f"to be reachable by remote players)")

    # The factory url is informational (autobahn accepts any Host); the real
    # bind is the listenTCP interface below.
    factory = WebSocketServerFactory(f"ws://{bind}:{port}")
    factory.protocol = ProxyProtocol

    reactor.listenTCP(port, factory, interface=bind)
    print(f"[Proxy] Proxy is up on {bind}:{port}. Waiting for client connections...")
    reactor.run()


if __name__ == "__main__":
    main()
