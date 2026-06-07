"""Compute a character's per-body-part texture indices for the Godot client.

The client (CharacterRig.apply_appearance) overrides each base.<part> material on a
character model with assets/character_textures/<part>/<part><N>.jpg. This module
produces the {part: N} dict the server streams, faithful to the original engine:

  * base skin per part comes from the mob's spawn.texture<Part> column, else the
    racial default table (below), keyed by race + sex (look does NOT affect skin).
  * worn armor overrides arms/legs/feet/hands/body (head is never overridden by
    worn gear — helmets are separate mounted models in the original).
  * armor/skin strings are "<PART>/<PART><N>" (e.g. "BODY/BODY53"); we lowercase
    (the DB is uppercase, the files are lowercase) and parse the trailing integer.
  * monsters with a single/ or multi/ whole-body texture return {} so the client
    keeps the model's embedded texture (their .dts has no base.<part> materials).

Tables copied verbatim from the shipped game (MoMReborn/mud/world/shared/models.py).
"""
from mud.world.defines import (RPG_SLOT_CHEST, RPG_SLOT_ARMS, RPG_SLOT_HANDS,
                               RPG_SLOT_LEGS, RPG_SLOT_FEET)

# (head, arms, legs, body, feet, hands)
_FTEX = {
    'Dark Elf': ('head/head34', 'arms/arms65', 'legs/legs65', 'body/body67', 'feet/feet65', 'hands/hands65'),
    'Elf': ('head/head4', 'arms/arms3', 'legs/legs3', 'body/body4', 'feet/feet3', 'hands/hands3'),
    'Human': ('head/head5', 'arms/arms4', 'legs/legs4', 'body/body5', 'feet/feet4', 'hands/hands4'),
    'Titan': ('head/head39', 'arms/arms71', 'legs/legs72', 'body/body73', 'feet/feet0', 'hands/hands71'),
    'Gnome': ('head/head33', 'arms/arms54', 'legs/legs55', 'body/body56', 'feet/feet55', 'hands/hands55'),
    'Dwarf': ('head/head7', 'arms/arms6', 'legs/legs6', 'body/body7', 'feet/feet6', 'hands/hands6'),
    'Halfling': ('head/head9', 'arms/arms9', 'legs/legs8', 'body/body10', 'feet/feet8', 'hands/hands9'),
    'Orc': ('head/head43', 'arms/arms80', 'legs/legs81', 'body/body82', 'feet/feet78', 'hands/hands80'),
    'Goblin': ('head/head37', 'arms/arms69', 'legs/legs69', 'body/body71', 'feet/feet69', 'hands/hands69'),
    'Ogre': ('head/head32', 'arms/arms53', 'legs/legs54', 'body/body55', 'feet/feet54', 'hands/hands54'),
    'Troll': ('head/head36', 'arms/arms67', 'legs/legs67', 'body/body69', 'feet/feet67', 'hands/hands67'),
    'Drakken': ('head/head12', 'arms/arms16', 'legs/legs17', 'body/body18', 'feet/feet17', 'hands/hands17'),
}
_MTEX = {
    'Dark Elf': ('head/head35', 'arms/arms64', 'legs/legs71', 'body/body66', 'feet/feet65', 'hands/hands65'),
    'Elf': ('head/head3', 'arms/arms2', 'legs/legs2', 'body/body2', 'feet/feet2', 'hands/hands2'),
    'Human': ('head/head1', 'arms/arms0', 'legs/legs0', 'body/body0', 'feet/feet0', 'hands/hands0'),
    'Titan': ('head/head38', 'arms/arms70', 'legs/legs70', 'body/body72', 'feet/feet0', 'hands/hands70'),
    'Gnome': ('head/head29', 'arms/arms32', 'legs/legs33', 'body/body34', 'feet/feet33', 'hands/hands33'),
    'Dwarf': ('head/head6', 'arms/arms5', 'legs/legs5', 'body/body6', 'feet/feet5', 'hands/hands5'),
    'Halfling': ('head/head8', 'arms/arms7', 'legs/legs7', 'body/body8', 'feet/feet7', 'hands/hands7'),
    'Orc': ('head/head42', 'arms/arms79', 'legs/legs80', 'body/body81', 'feet/feet77', 'hands/hands79'),
    'Goblin': ('head/head30', 'arms/arms38', 'legs/legs39', 'body/body40', 'feet/feet39', 'hands/hands39'),
    'Ogre': ('head/head11', 'arms/arms14', 'legs/legs15', 'body/body16', 'feet/feet15', 'hands/hands15'),
    'Troll': ('head/head31', 'arms/arms52', 'legs/legs53', 'body/body54', 'feet/feet53', 'hands/hands53'),
    'Drakken': ('head/head10', 'arms/arms10', 'legs/legs10', 'body/body12', 'feet/feet10', 'hands/hands11'),
}
_ORDER = ('head', 'arms', 'legs', 'body', 'feet', 'hands')
_WORN_SLOT = {'body': RPG_SLOT_CHEST, 'arms': RPG_SLOT_ARMS,
              'hands': RPG_SLOT_HANDS, 'legs': RPG_SLOT_LEGS, 'feet': RPG_SLOT_FEET}


def _parse_index(part, s):
    """'BODY/BODY53' -> 53 ; 'single/skeleton' / 'multi/x' / '' -> None."""
    if not s:
        return None
    base = s.lower().rsplit('/', 1)[-1]  # 'body53'
    if base.startswith(part):
        num = base[len(part):]
        if num.isdigit():
            return int(num)
    return None


def _worn_material(mob, slot):
    try:
        worn = getattr(mob, 'worn', None)
        if not worn:
            return ''
        item = worn[slot]
        return (getattr(item, 'material', '') or '') if item else ''
    except Exception:
        return ''


def compute_appearance(mob):
    """Return {part: texture_index} for a character, or {} if the model uses a
    single/multi embedded texture (monsters) and needs no per-part override."""
    try:
        spawn = getattr(mob, 'spawn', None)
        # Whole-body single texture (skeletons, zombies, ...) -> keep embedded.
        if spawn is not None and (getattr(spawn, 'textureSingle', '') or ''):
            return {}

        base = {}
        if spawn is not None:
            base['head'] = getattr(spawn, 'textureHead', '') or ''
            base['arms'] = getattr(spawn, 'textureArms', '') or ''
            base['legs'] = getattr(spawn, 'textureLegs', '') or ''
            base['body'] = getattr(spawn, 'textureBody', '') or ''
            base['feet'] = getattr(spawn, 'textureFeet', '') or ''
            base['hands'] = getattr(spawn, 'textureHands', '') or ''

        race = ''
        if getattr(mob, 'race', None) is not None:
            race = str(getattr(mob.race, 'name', '') or '')
        sex = str(getattr(mob, 'sex', '') or 'Male')
        table = _MTEX if sex.lower().startswith('m') else _FTEX
        racial = table.get(race)
        if racial:
            for i, part in enumerate(_ORDER):
                if not base.get(part):
                    base[part] = racial[i]

        # Worn armor overrides (head excluded — helmets are separate models).
        for part, slot in _WORN_SLOT.items():
            mat = _worn_material(mob, slot)
            if mat:
                base[part] = mat

        out = {}
        for part in _ORDER:
            n = _parse_index(part, base.get(part, ''))
            if n is not None:
                out[part] = n
        return out
    except Exception:
        return {}
