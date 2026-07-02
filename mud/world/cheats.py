# Testing/cheat commands for the Godot port.
#
# These power the in-game cheat window (F8 in the Godot client): grant XP,
# set the class level, learn spells, raise skills, give money and items.
# They reuse the same primitives as the original GM "immortal" commands
# (mud/world/immortalcommand.py CmdGimme & co) but return structured results
# the proxy can ship back to the client UI.
#
# Gating: the world server only honors these when MOM_ENABLE_CHEATS=1 is set
# in its environment (run_servers.sh exports it by default for the local test
# stack; unset it to play without cheats).

import os

from mud.world.character import CharacterSpell
from mud.world.defines import RPG_SLOT_WORN_BEGIN, RPG_SLOT_WORN_END


def CheatsEnabled():
    return os.environ.get("MOM_ENABLE_CHEATS", "") not in ("", "0")


def _result(success, message, **extra):
    out = {"success": bool(success), "message": str(message)}
    out.update(extra)
    return out


def _char_and_mob(player):
    char = player.curChar
    if not char or not char.mob:
        return None, None
    return char, char.mob


def DoCheat(player, action, params):
    """Execute one cheat action for *player*. Returns a JSON-able dict."""
    if not CheatsEnabled():
        return _result(False, "Cheats are disabled on this server (set MOM_ENABLE_CHEATS=1).")
    params = params or {}
    handler = _ACTIONS.get(str(action))
    if not handler:
        return _result(False, "Unknown cheat action: %r" % action)
    try:
        return handler(player, params)
    except Exception as exc:
        from traceback import print_exc
        print_exc()
        return _result(False, "Cheat %s failed: %s" % (action, exc))


def cheat_status(player, params):
    return _result(True, "Cheats are enabled.", enabled=True)


def cheat_give_xp(player, params):
    amount = int(params.get("amount", 0))
    if amount <= 0:
        return _result(False, "XP amount must be positive.")
    char, mob = _char_and_mob(player)
    if not char:
        return _result(False, "No active character.")
    # clamp=False awards the exact amount (same path as XP certificates).
    char.gainXP(amount, False)
    player.cinfoDirty = True
    return _result(True, "Granted %d XP to %s (now level %d)." % (
        amount, char.name, char.spawn.plevel))


def cheat_set_level(player, params):
    target = int(params.get("level", 0))
    char, mob = _char_and_mob(player)
    if not char:
        return _result(False, "No active character.")
    current = int(char.spawn.plevel)
    if target <= current:
        return _result(False, "%s is already level %d; the engine can only level up. "
                       "Create a fresh character for a lower level." % (char.name, current))
    if target > 100:
        target = 100
    # gainLevel(0) bumps the primary class exactly one level per call.
    safety = 0
    while int(char.spawn.plevel) < target and safety < 200:
        before = int(char.spawn.plevel)
        char.gainLevel(0)
        safety += 1
        if int(char.spawn.plevel) == before:
            break  # cap reached (demo limit or class cap)
    player.cinfoDirty = True
    return _result(True, "%s is now level %d." % (char.name, char.spawn.plevel),
                   level=int(char.spawn.plevel))


def cheat_give_money(player, params):
    plat = int(params.get("platinum", 0))
    if plat == 0:
        return _result(False, "Platinum amount must be non-zero.")
    player.platinum += plat
    if player.platinum < 0:
        player.platinum = 0
    return _result(True, "Granted %d platinum." % plat)


def cheat_give_item(player, params):
    name = str(params.get("name", "")).strip()
    if not name:
        return _result(False, "Missing item name.")
    char, mob = _char_and_mob(player)
    if not char:
        return _result(False, "No active character.")
    count = max(1, min(int(params.get("count", 1)), 20))
    equip = bool(params.get("equip", False))
    given = []
    equipped = False
    for _ in range(count):
        item = player.giveItem(name, True, True)
        if not item:
            break
        # Mirror GIMME: auto-equip when the item landed on a worn slot.
        if RPG_SLOT_WORN_END > item.slot >= RPG_SLOT_WORN_BEGIN:
            mob.equipItem(item.slot, item)
            equipped = True
        elif equip and not equipped:
            # giveItemInstance prefers free carry slots, so explicitly move the
            # item into the first worn slot it fits when asked to equip. If that
            # slot is occupied (e.g. starting gear on the chest), vacate it via
            # Character.unequipItem, which reslots the old item into a free
            # carry slot — same as the player double-clicking to swap.
            for slot in item.itemProto.slots:
                if not (RPG_SLOT_WORN_END > slot >= RPG_SLOT_WORN_BEGIN):
                    continue
                if slot in mob.worn and not char.unequipItem(slot):
                    continue  # occupied and no carry space to vacate it
                item.slot = slot
                mob.equipItem(slot, item)
                equipped = True
                break
        given.append(item.name)
    if not given:
        return _result(False, "Could not give %r (unknown item or no inventory space)." % name)
    char.refreshItems()
    player.cinfoDirty = True
    suffix = " (equipped)" if equipped else ""
    return _result(True, "Gave %s x%d.%s" % (given[0], len(given), suffix))


def _next_free_spell_slot(char):
    used = set(int(s.slot) for s in char.spells)
    slot = 0
    while slot in used:
        slot += 1
    return slot


def _learn_spell_proto(char, proto):
    for cspell in char.spells:
        if cspell.spellProto == proto:
            return False  # already known
    CharacterSpell(character=char, spellProto=proto, slot=_next_free_spell_slot(char), recast=0)
    char.spellsDirty = True
    return True


def cheat_learn_spell(player, params):
    from mud.world.spell import SpellProto
    name = str(params.get("name", "")).strip()
    if not name:
        return _result(False, "Missing spell name.")
    char, mob = _char_and_mob(player)
    if not char:
        return _result(False, "No active character.")
    try:
        con = SpellProto._connection.getConnection()
        row = con.execute('SELECT id FROM spell_proto WHERE lower(name)=lower(?) LIMIT 1;',
                          (name,)).fetchone()
        if not row:
            return _result(False, "Unknown spell: %r." % name)
        proto = SpellProto.get(row[0])
    except Exception:
        return _result(False, "Unknown spell: %r." % name)
    if not _learn_spell_proto(char, proto):
        return _result(False, "%s already knows %s." % (char.name, proto.name))
    return _result(True, "%s learns %s." % (char.name, proto.name))


def cheat_learn_class_spells(player, params):
    """Learn every spell castable by the character's classes up to a level."""
    from mud.world.spell import SpellClass
    char, mob = _char_and_mob(player)
    if not char:
        return _result(False, "No active character.")
    max_level = int(params.get("max_level", 0)) or int(char.spawn.plevel)
    classes = {}
    classes[str(char.spawn.pclassInternal)] = int(char.spawn.plevel)
    if char.spawn.sclassInternal:
        classes[str(char.spawn.sclassInternal)] = int(char.spawn.slevel)
    if char.spawn.tclassInternal:
        classes[str(char.spawn.tclassInternal)] = int(char.spawn.tlevel)
    learned = 0
    seen = set()
    for sc in SpellClass.select():
        cname = str(sc.classname)
        if cname not in classes:
            continue
        if int(sc.level) > max_level:
            continue
        proto = sc.spellProto
        if proto.id in seen:
            continue
        seen.add(proto.id)
        if _learn_spell_proto(char, proto):
            learned += 1
    return _result(True, "%s learned %d new spells (up to level %d)." % (
        char.name, learned, max_level))


def cheat_raise_skills(player, params):
    points = max(1, min(int(params.get("points", 1)), 100))
    only = str(params.get("name", "")).strip()
    char, mob = _char_and_mob(player)
    if not char:
        return _result(False, "No active character.")
    names = [only] if only else list(mob.skillLevels.keys())
    raised = 0
    for _ in range(points):
        for skname in names:
            # min=max=0 makes the raise deterministic (GIMME SKILL behavior).
            char.checkSkillRaise(skname, 0, 0, playSound=False, silent=True)
            raised += 1
    player.cinfoDirty = True
    if only:
        return _result(True, "Raised %s by up to %d points (now %d)." % (
            only, points, int(mob.skillLevels.get(only, 0))))
    return _result(True, "Raised all %d skills by up to %d points." % (len(names), points))


def cheat_full_heal(player, params):
    for c in player.party.members:
        m = c.mob
        if not m:
            continue
        m.health = m.maxHealth
        m.mana = m.maxMana
        m.stamina = m.maxStamina
        m.skillReuse = {}
        m.recastTimers = {}
        if m.pet:
            m.pet.health = m.pet.maxHealth
    player.cinfoDirty = True
    return _result(True, "Party fully restored (health/mana/stamina, cooldowns cleared).")


def cheat_apply_spell(player, params):
    """Apply a named spell to the current character immediately (no mana / cast
    time / spellbook). Handy for exercising buff effects — Enlarge, Shrink,
    Erar Invisibility, Urug's Sandals Fly, Transmutation of Volsh, etc."""
    from mud.world.spell import SpawnSpell, SpellProto
    name = str(params.get("name", "")).strip()
    if not name:
        return _result(False, "apply_spell needs a spell name.")
    char, mob = _char_and_mob(player)
    if not char or not mob:
        return _result(False, "No active character.")
    try:
        proto = SpellProto.byName(name)
    except Exception:
        proto = None
    if not proto:
        return _result(False, "No spell named %r." % name)
    # Optionally cast at the current target instead of self.
    dst = mob
    if params.get("at_target") and getattr(mob, "target", None):
        dst = mob.target
    # A projectile spell at a target must go through the projectile path (so the
    # stub's launchProjectile resolves it and applies damage on "impact"), not a
    # direct SpawnSpell which would skip the flight.
    if getattr(proto, "projectile", "") and dst is not mob:
        from mud.world.projectile import Projectile
        p = Projectile(mob, dst, 1)
        p.spellProto = proto
        p.launch()
        return _result(True, "Launched %s at %s." % (name, getattr(dst, "name", "target")))
    # spellLevel is the spell RANK (1..N, indexes RPG_ROMAN), not the character
    # level — rank 1 is always valid.
    SpawnSpell(proto, mob, dst, spellLevel=1)
    return _result(True, "Applied %s to %s." % (name, getattr(dst, "name", char.name)))


def cheat_suicide(player, params):
    """Kill the current character outright (testing the death/respawn flow)."""
    char, mob = _char_and_mob(player)
    if not char or not mob:
        return _result(False, "No active character.")
    if char.dead:
        return _result(False, "%s is already dead." % char.name)
    mob.health = 0
    # Mirror the tick's lethal-health path so the normal death machinery runs
    # (detach, death marker, character.dead = True, sim "die" event).
    mob.die(immortalOverride=True)
    player.cinfoDirty = True
    return _result(True, "%s has died. Release to respawn." % char.name)


def cheat_list_items(player, params):
    from mud.world.item import ItemProto
    flt = str(params.get("filter", "")).strip().lower()
    limit = max(1, min(int(params.get("limit", 50)), 200))
    con = ItemProto._connection.getConnection()
    if flt:
        rows = con.execute(
            "SELECT name FROM item_proto WHERE lower(name) LIKE ? ORDER BY name LIMIT ?;",
            ("%" + flt + "%", limit)).fetchall()
    else:
        rows = con.execute(
            "SELECT name FROM item_proto ORDER BY name LIMIT ?;", (limit,)).fetchall()
    return _result(True, "%d items." % len(rows), items=[r[0] for r in rows])


def cheat_list_spells(player, params):
    from mud.world.spell import SpellProto
    flt = str(params.get("filter", "")).strip().lower()
    limit = max(1, min(int(params.get("limit", 50)), 200))
    con = SpellProto._connection.getConnection()
    if flt:
        rows = con.execute(
            "SELECT name FROM spell_proto WHERE lower(name) LIKE ? ORDER BY name LIMIT ?;",
            ("%" + flt + "%", limit)).fetchall()
    else:
        rows = con.execute(
            "SELECT name FROM spell_proto ORDER BY name LIMIT ?;", (limit,)).fetchall()
    return _result(True, "%d spells." % len(rows), spells=[r[0] for r in rows])


def cheat_set_time(player, params):
    # Sets the world's authoritative time of day and syncs EVERY connected player,
    # so the change is shared (the client /time command routes here). Mirrors the
    # immortal CmdSetTime broadcast in mud/world/immortalcommand.py.
    try:
        hour = int(params.get("hour", 12))
    except Exception:
        hour = 12
    try:
        minute = int(params.get("minute", 0))
    except Exception:
        minute = 0
    hour = max(0, min(hour, 23))
    minute = max(0, min(minute, 59))
    world = getattr(player, "world", None)
    if world is None or getattr(world, "time", None) is None:
        return _result(False, "World clock unavailable.")
    # Propagate across zone clusters if this world runs more than one.
    try:
        if getattr(world, "daemonPerspective", None):
            world.daemonPerspective.callRemote("propagateCmd", "setTime", hour, minute)
    except Exception:
        pass
    world.time.hour = hour
    world.time.minute = minute
    sent = 0
    for p in list(getattr(world, "activePlayers", []) or []):
        try:
            p.mind.callRemote("syncTime", world.time.hour, world.time.minute)
            sent += 1
        except Exception:
            pass
    return _result(True, "Time set to %02d:%02d (synced to %d player(s))." % (hour, minute, sent),
                   hour=hour, minute=minute)


_ACTIONS = {
    "status": cheat_status,
    "give_xp": cheat_give_xp,
    "set_level": cheat_set_level,
    "give_money": cheat_give_money,
    "give_item": cheat_give_item,
    "learn_spell": cheat_learn_spell,
    "learn_class_spells": cheat_learn_class_spells,
    "raise_skills": cheat_raise_skills,
    "full_heal": cheat_full_heal,
    "suicide": cheat_suicide,
    "apply_spell": cheat_apply_spell,
    "list_items": cheat_list_items,
    "list_spells": cheat_list_spells,
    "set_time": cheat_set_time,
}
