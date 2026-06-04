#!/usr/bin/env python3
"""
Setup script for Minions of Mirth server databases.

This script:
1. Copies game data from MoMReborn client directory
2. Creates the world database for the specified world name
3. Creates the character database
4. Creates the master database
5. Adds missing columns needed by the newer server code

Usage:
    python3 setup_databases.py [--worldname=TestDaemon]
"""

import sqlite3
import os
import sys
import shutil

# Add current dir to path
sys.path.insert(0, os.getcwd())

WORLDNAME = "TestDaemon"
for arg in sys.argv:
    if arg.startswith("--worldname="):
        WORLDNAME = arg.split("=", 1)[1]

# Determine GAMEROOT from mom.cfg
GAMEROOT = "minions.of.mirth"
if os.path.exists("./projects/mom.cfg"):
    from configparser import ConfigParser
    parser = ConfigParser()
    parser.read("./projects/mom.cfg")
    try:
        GAMEROOT = parser.get("Game Settings", "Game Root")
    except:
        pass

MOM_CLIENT_DIR = os.path.join("MoMReborn")
BASELINE_WORLD_DB = os.path.join(MOM_CLIENT_DIR, GAMEROOT, "data", "worlds", "multiplayer.baseline", "world.db")

# Schema additions: columns present in server code but missing from old database
# Tables present in server code but missing from old database
MISSING_TABLES = [
    """CREATE TABLE IF NOT EXISTS spawn_effect (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        spawn_id INT,
        effectname TEXT
    )""",
    """CREATE TABLE IF NOT EXISTS race (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        playable BOOLEAN DEFAULT 0,
        xp_mod REAL DEFAULT 1.0,
        regen_health REAL DEFAULT 1.0,
        regen_mana REAL DEFAULT 2.0,
        regen_stamina REAL DEFAULT 1.0,
        consume_water REAL DEFAULT 1.0,
        consume_food REAL DEFAULT 1.0,
        move REAL DEFAULT 1.0,
        swim REAL DEFAULT 1.0,
        realm INT DEFAULT 0,
        see_invisible REAL DEFAULT 0.0
    )""",
    """CREATE TABLE IF NOT EXISTS race_graphic (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        model_fit_male TEXT DEFAULT '',
        model_heavy_male TEXT DEFAULT '',
        model_thin_male TEXT DEFAULT '',
        model_fit_female TEXT DEFAULT '',
        model_heavy_female TEXT DEFAULT '',
        model_thin_female TEXT DEFAULT '',
        animation_male TEXT DEFAULT '',
        animation_female TEXT DEFAULT '',
        texture_head_male TEXT DEFAULT '',
        texture_body_male TEXT DEFAULT '',
        texture_arms_male TEXT DEFAULT '',
        texture_legs_male TEXT DEFAULT '',
        texture_hands_male TEXT DEFAULT '',
        texture_feet_male TEXT DEFAULT '',
        texture_special_male TEXT DEFAULT '',
        texture_head_female TEXT DEFAULT '',
        texture_body_female TEXT DEFAULT '',
        texture_arms_female TEXT DEFAULT '',
        texture_legs_female TEXT DEFAULT '',
        texture_hands_female TEXT DEFAULT '',
        texture_feet_female TEXT DEFAULT '',
        texture_special_female TEXT DEFAULT '',
        size_male REAL DEFAULT 1.0,
        size_female REAL DEFAULT 1.0,
        hmount_fit_male REAL DEFAULT 1.0,
        hmount_heavy_male REAL DEFAULT 1.0,
        hmount_thin_male REAL DEFAULT 1.0,
        hmount_fit_female REAL DEFAULT 1.0,
        hmount_heavy_female REAL DEFAULT 1.0,
        hmount_thin_female REAL DEFAULT 1.0
    )""",
]

SCHEMA_ADDITIONS = [
    ('character', 'auction_id_n', 'INTEGER', '0'),
    ('character', 'zone_id', 'INTEGER', 'NULL'),
    ('dialog', 'dialog_line_id', 'INTEGER', 'NULL'),
    ('dialog_action', 'give_xp', 'INTEGER', '0'),
    ('dialog_action', 'open_mail', 'BOOLEAN', '0'),
    ('dialog_action', 'resurrect_xp', 'REAL', '0'),
    ('dialog_action', 'spawn_id', 'INTEGER', 'NULL'),
    ('dialog_action', 'spell_proto_id', 'INTEGER', 'NULL'),
    ('dialog_action', 'take_xp', 'INTEGER', '0'),
    ('dialog_choice', 'dialog_line_id', 'INTEGER', 'NULL'),
    ('effect_illusion', 'illusion_texture_extra', 'TEXT', "''"),
    ('effect_illusion', 'spawn_sound_profile_id', 'INTEGER', 'NULL'),
    ('effect_proto', 'effect_drain_id', 'INTEGER', 'NULL'),
    ('effect_proto', 'effect_illusion_id', 'INTEGER', 'NULL'),
    ('effect_proto', 'effect_leech_id', 'INTEGER', 'NULL'),
    ('effect_proto', 'effect_regen_id', 'INTEGER', 'NULL'),
    ('effect_proto', 'item_proto_id', 'INTEGER', 'NULL'),
    ('effect_proto', 'resurrection_xp', 'REAL', '0'),
    ('effect_proto', 'spawn_id', 'INTEGER', 'NULL'),
    ('item_proto', 'end_day_rl', 'TEXT', "''"),
    ('item_proto', 'item_sound_profile_id', 'INTEGER', 'NULL'),
    ('item_proto', 'start_day_rl', 'TEXT', "''"),
    ('player', 'auction_last', 'TIMESTAMP', "'2000-01-01'"),
    ('player', 'zone_id', 'INTEGER', 'NULL'),
    ('recipe', 'cost_tp', 'INTEGER', '0'),
    ('recipe', 'item_proto_id', 'INTEGER', 'NULL'),
    ('spawn', 'auctioneer', 'INTEGER', '0'),
    ('spawn', 'requires_weapon', 'TEXT', "''"),
    ('spawn', 'spawn_sound_profile_id', 'INTEGER', 'NULL'),
    ('spawn', 'texture_extra', 'TEXT', "''"),
    ('spawn_group', 'spawn_group_controller_info_id', 'INTEGER', 'NULL'),
    ('spawn_info', 'end_day_rl', 'TEXT', "''"),
    ('spawn_info', 'start_day_rl', 'TEXT', "''"),
    ('battle_proto', 'battle_result_id', 'INTEGER', 'NULL'),
    ('battle_proto', 'battle_sequence_id', 'INTEGER', 'NULL'),
    ('battle_sequence', 'battle_sequence_id', 'INTEGER', 'NULL'),
    ('table_permission', 'can_delete', 'BOOLEAN', '0'),
    ('table_permission', 'can_insert', 'BOOLEAN', '0'),
    ('table_permission', 'can_update', 'BOOLEAN', '0'),
    ('zone', 'cluster_id', 'INTEGER', '0'),
    ('world', 'start_zone', 'TEXT', "''"),
    ('world', 'dstart_zone', 'TEXT', "''"),
    ('world', 'mstart_zone', 'TEXT', "''"),
]


def add_missing_columns(db_path):
    """Add tables and columns that exist in server code but not in the database."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create missing tables
    for sql in MISSING_TABLES:
        cursor.execute(sql)

    # Get existing tables and columns
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]

    db_columns = {}
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        db_columns[table] = {r[1] for r in cursor.fetchall()}

    added = 0
    for table, col, sql_type, default in SCHEMA_ADDITIONS:
        if table not in db_columns:
            continue
        if col in db_columns[table]:
            continue
        sql = f'ALTER TABLE {table} ADD COLUMN {col} {sql_type} DEFAULT {default}'
        try:
            cursor.execute(sql)
            added += 1
        except Exception as e:
            if 'duplicate' not in str(e).lower():
                print(f"  Warning: {table}.{col}: {e}")

    conn.commit()
    conn.close()
    return added


def _master_db_is_valid(db_path):
    """A master DB is only usable if it exists, is non-empty, and actually has
    the `user` table the MasterServer needs at startup."""
    if not os.path.exists(db_path) or os.path.getsize(db_path) == 0:
        return False
    try:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='user';"
            ).fetchone()
            return row is not None
        finally:
            conn.close()
    except Exception:
        return False


def reset_runtime():
    """Delete all generated runtime data so the next setup rebuilds from the
    pristine MoMReborn baseline. Use when accounts/characters/world DBs have
    drifted out of sync across code changes (symptom: 'won't load into world')."""
    import glob
    targets = [GAMEROOT, "common", "data/master", "data/character", "data/tmp",
               "mom.cfg", "main.cs.dso"]
    targets += glob.glob("*export*.db")
    for t in targets:
        if os.path.isdir(t):
            print(f"  removing dir  {t}/")
            shutil.rmtree(t, ignore_errors=True)
        elif os.path.exists(t):
            print(f"  removing file {t}")
            try:
                os.remove(t)
            except OSError:
                pass
    print("Runtime data reset. Rebuilding from baseline...\n")


def setup():
    if "--reset" in sys.argv:
        print("Resetting runtime databases (--reset)...")
        reset_runtime()
    if not os.path.exists(BASELINE_WORLD_DB):
        print(f"Error: Could not find baseline world.db at {BASELINE_WORLD_DB}")
        print("Make sure the MoMReborn client directory exists in the repo root.")
        sys.exit(1)

    # Step 1: Copy game data directory
    game_data_dir = os.path.join(".", GAMEROOT)
    if not os.path.exists(game_data_dir):
        print(f"Copying game data from MoMReborn client to ./{GAMEROOT}/...")
        shutil.copytree(os.path.join(MOM_CLIENT_DIR, GAMEROOT), game_data_dir)
    else:
        print(f"./{GAMEROOT}/ already exists, skipping copy.")

    # Copy common directory
    if not os.path.exists("./common"):
        common_src = os.path.join(MOM_CLIENT_DIR, "common")
        if os.path.exists(common_src):
            print("Copying common directory...")
            shutil.copytree(common_src, "./common")

    # Copy main.cs.dso
    if not os.path.exists("./main.cs.dso"):
        mcs_src = os.path.join(MOM_CLIENT_DIR, "main.cs.dso")
        if os.path.exists(mcs_src):
            shutil.copyfile(mcs_src, "./main.cs.dso")

    # Step 2: Create world database directory and copy baseline
    world_dir = os.path.join(GAMEROOT, "data", "worlds", "multiplayer", WORLDNAME)
    world_db = os.path.join(world_dir, "world.db")
    if not os.path.exists(world_db):
        print(f"Creating world database for '{WORLDNAME}'...")
        os.makedirs(world_dir, exist_ok=True)
        shutil.copyfile(BASELINE_WORLD_DB, world_db)
    else:
        print(f"World database already exists at {world_db}")

    # Step 3: Add missing schema columns to world.db
    print("Updating world.db schema...")
    n = add_missing_columns(world_db)
    print(f"  Added {n} missing columns to world.db")

    # Step 4: Create character database
    char_db = "./data/character/character.db"
    if not os.path.exists(char_db):
        print("Creating character database...")
        os.makedirs("./data/character", exist_ok=True)
        shutil.copyfile(BASELINE_WORLD_DB, char_db)
        # Add player_buffer and character_buffer tables
        from mud_ext.characterserver.serverdb import CREATE_PLAYER_BUFFER_SQL
        conn = sqlite3.connect(char_db)
        cursor = conn.cursor()
        cursor.executescript("BEGIN TRANSACTION;\n%s\nEND TRANSACTION;" % CREATE_PLAYER_BUFFER_SQL)
        cursor.close()
        conn.commit()
        conn.close()
    else:
        print("Character database already exists.")

    # Add missing columns to character.db
    print("Updating character.db schema...")
    n = add_missing_columns(char_db)
    print(f"  Added {n} missing columns to character.db")

    # Step 5: Create master database
    master_db = "./data/master/master.db"
    if not _master_db_is_valid(master_db):
        # Remove a leftover empty/corrupt file (a 0-byte master.db from a failed
        # run still "exists", which previously caused this step to be skipped and
        # the MasterServer to crash with "no such table: user").
        if os.path.exists(master_db):
            print("Existing master.db is empty/invalid; recreating...")
            os.remove(master_db)
        print("Creating master database...")
        sys.argv.append('database=data/master')
        sys.argv.append('gameconfig=mom.cfg')
        from mud_ext.masterserver.createdb import main as CreateMasterDB
        CreateMasterDB()
    else:
        print("Master database already exists.")

    # Step 6: Copy mom.cfg to root if needed
    if not os.path.exists("./mom.cfg"):
        if os.path.exists("./projects/mom.cfg"):
            shutil.copyfile("./projects/mom.cfg", "./mom.cfg")

    print("\nSetup complete! You can now start the server with:")
    print(f"  python3 WorldDaemon.py gameconfig=mom.cfg -worldname={WORLDNAME} -publicname=TestWorld -password=mmo")


if __name__ == '__main__':
    setup()
