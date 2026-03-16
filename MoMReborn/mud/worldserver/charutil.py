# Embedded file name: mud\worldserver\charutil.pyo
import time
from mud.world.defines import *
from mud.common.dbconfig import GetDBURI
from twisted.internet import reactor
import traceback
from pysqlite2 import dbapi2 as sqlite
import os, re, zlib
DB_TEMP = './data/tmp'
PLAYER_TABLES = ['player',
 'player_monster_spawn',
 'item',
 'item_container_content',
 'item_variant']
CHARACTER_TABLES = ['character',
 'character_spell',
 'character_skill',
 'character_advancement',
 'character_dialog_choice',
 'character_vault_item',
 'character_faction',
 'spawn',
 'spawn_skill',
 'spawn_resistance',
 'spawn_spell',
 'spawn_stat',
 'item',
 'item_container_content',
 'item_variant',
 'spell_store']
TABLES = PLAYER_TABLES[:]
TABLES.extend(CHARACTER_TABLES)
TVALUES = {}
TATTR = {}
CREATE_PLAYER_TABLE_SQL = ''
CREATE_CHARACTER_TABLE_SQL = ''
PLAYER_BUFFERS = []
CLUSTER = -1

def SetClusterNum(cluster):
    global CLUSTER
    CLUSTER = cluster


def GenerateInsertValues(table, valuesIn, playerID = None, characterID = None, spawnID = None, itemID = None, contentID = None):
    valuesOut = []
    for valueIn in valuesIn:
        valueOut = []
        for col, v in zip(TATTR[table], valueIn):
            if col == 'id':
                valueOut.append(None)
            elif col == 'playerID':
                valueOut.append(playerID)
            elif col == 'characterID':
                valueOut.append(characterID)
            elif col == 'itemID':
                valueOut.append(itemID)
            elif col == 'contentID':
                valueOut.append(contentID)
            elif col == 'spawnID':
                valueOut.append(spawnID)
            else:
                valueOut.append(v)

        valuesOut.append(valueOut)

    return valuesOut


def InstallItemList(cursor, dstCursor, itemList, playerID, characterID, spawnID, indirect = False, oldContainerItem = None, newContainerItem = None, vault = False):
    if indirect:
        for itemID in itemList:
            cursor.execute('SELECT * FROM item WHERE id=? LIMIT 1;', (itemID[0],))
            itemValues = cursor.fetchone()
            if not itemValues:
                try:
                    charName = cursor.execute('SELECT name FROM spawn WHERE id=? LIMIT 1;', (spawnID,)).fetchone()[0]
                    if vault:
                        cursor.execute('SELECT stack_count,name FROM character_vault_item WHERE item_id=? LIMIT 1;', (itemID[0],))
                        itemValues = cursor.fetchone()
                        print "ERROR: %i %s had to be purged from character %s's vault because they miss item backing." % (itemValues[0], itemValues[1], charName)
                    else:
                        dstCursor.execute('SELECT name FROM item WHERE id=? LIMIT 1;', (containerItem,))
                        print "ERROR: an item from character %s's container %s had to be purged because it misses item backing." % (charName, dstCursor.fetchone()[0])
                except:
                    pass

                continue
            itemID = itemValues[0]
            values = GenerateInsertValues('item', (itemValues,), None, None, spawnID)
            dstCursor.executemany('INSERT INTO item VALUES(%s)' % TVALUES['item'], values)
            dstCursor.execute('SELECT last_insert_rowid() FROM item')
            newItemID = dstCursor.fetchone()[0]
            cursor.execute('SELECT * FROM item_variant WHERE item_id=?;', (itemID,))
            values = GenerateInsertValues('item_variant', cursor.fetchall(), None, None, spawnID, newItemID)
            dstCursor.executemany('INSERT INTO item_variant VALUES(%s)' % TVALUES['item_variant'], values)
            try:
                cursor.execute('SELECT content_id FROM item_container_content WHERE item_id=?;', (itemID,))
                InstallItemList(cursor, dstCursor, cursor.fetchall(), playerID, characterID, spawnID, True, itemID, newItemID)
            except:
                pass

            if vault:
                cursor.execute('SELECT * FROM character_vault_item WHERE item_id=? LIMIT 1;', (itemID,))
                values = GenerateInsertValues('character_vault_item', cursor.fetchall(), playerID, characterID, spawnID, newItemID)
                dstCursor.executemany('INSERT INTO character_vault_item VALUES(%s)' % TVALUES['character_vault_item'], values)
            else:
                try:
                    cursor.execute('SELECT * FROM item_container_content WHERE item_id=? LIMIT 1;', (oldContainerItem,))
                    values = GenerateInsertValues('item_container_content', cursor.fetchall(), playerID, characterID, spawnID, newContainerItem, newItemID)
                    dstCursor.executemany('INSERT INTO item_container_content VALUES(%s)' % TVALUES['item_container_content'], values)
                except:
                    pass

    else:
        for itemValues in itemList:
            itemID = itemValues[0]
            values = GenerateInsertValues('item', (itemValues,), playerID, characterID, spawnID)
            dstCursor.executemany('INSERT INTO item VALUES(%s)' % TVALUES['item'], values)
            dstCursor.execute('SELECT last_insert_rowid() FROM item')
            newItemID = dstCursor.fetchone()[0]
            cursor.execute('SELECT * FROM item_variant WHERE item_id=?;', (itemID,))
            values = GenerateInsertValues('item_variant', cursor.fetchall(), playerID, characterID, spawnID, newItemID)
            dstCursor.executemany('INSERT INTO item_variant VALUES(%s)' % TVALUES['item_variant'], values)
            try:
                cursor.execute('SELECT content_id FROM item_container_content WHERE item_id=?;', (itemID,))
                InstallItemList(cursor, dstCursor, cursor.fetchall(), playerID, characterID, spawnID, True, itemID, newItemID)
            except:
                pass

    return


def InstallCharacterBuffer(playerID, cname, buffer):
    global DB_TEMP
    tm = time.time()
    from mud.world.player import Player
    try:
        dbuffer = zlib.decompress(buffer)
        dbname = '%s/char.%i.db' % (DB_TEMP, CLUSTER)
        f = open(dbname, 'wb')
        f.write(dbuffer)
        f.close()
        dbconn = sqlite.connect(dbname)
        cursor = dbconn.cursor()
        dstConn = Player._connection.transaction()
        dstCursor = Player._connection.getConnection().cursor()
    except:
        traceback.print_exc()
        return True

    error = False
    try:
        cursor.execute('SELECT name FROM character LIMIT 1;')
        name = cursor.fetchone()[0]
        if name != cname:
            cursor.execute("UPDATE character SET name = '%s' WHERE name = '%s';" % (cname, name))
        cursor.execute('SELECT name FROM spawn LIMIT 1;')
        name = cursor.fetchone()[0]
        if name != cname:
            cursor.execute("UPDATE spawn SET name = '%s' WHERE name = '%s';" % (cname, name))
        cursor.execute("SELECT * FROM character where name = '%s' LIMIT 1;" % cname)
        cvalues = cursor.fetchone()
        cid = cvalues[0]
        values = GenerateInsertValues('character', (cvalues,), playerID)
        sql = 'INSERT INTO character VALUES(%s)' % TVALUES['character']
        try:
            dstCursor.executemany(sql, values)
            dstCursor.execute('SELECT last_insert_rowid() FROM character')
            characterID = dstCursor.fetchone()[0]
        except:
            traceback.print_exc()
            print sql, values
            raise Exception, 'Error installing character %s' % cname

        cursor.execute('SELECT * FROM spawn WHERE character_id = %i LIMIT 1;' % cid)
        svalues = cursor.fetchone()
        sid = svalues[0]
        values = GenerateInsertValues('spawn', (svalues,), playerID, characterID)
        dstCursor.executemany('INSERT INTO spawn VALUES(%s)' % TVALUES['spawn'], values)
        dstCursor.execute('SELECT last_insert_rowid() FROM spawn')
        spawnID = dstCursor.fetchone()[0]
        dstCursor.execute('UPDATE character SET spawn_id = %i WHERE id = %i;' % (spawnID, characterID))
        ctables = ['character_spell',
         'character_skill',
         'character_advancement',
         'character_dialog_choice',
         'spell_store',
         'character_faction']
        for t in ctables:
            cursor.execute('SELECT * FROM %s WHERE character_id = %i;' % (t, cid))
            values = GenerateInsertValues(t, cursor.fetchall(), playerID, characterID, spawnID)
            dstCursor.executemany('INSERT INTO %s VALUES(%s)' % (t, TVALUES[t]), values)

        cursor.execute('SELECT * FROM item WHERE character_id = %i and (slot >= %i or slot < %i) and slot != -1;' % (cid, RPG_SLOT_BANK_END, RPG_SLOT_BANK_BEGIN))
        InstallItemList(cursor, dstCursor, cursor.fetchall(), None, characterID, spawnID)
        cursor.execute('SELECT item_id FROM character_vault_item WHERE character_id = %i;' % cid)
        InstallItemList(cursor, dstCursor, cursor.fetchall(), playerID, characterID, spawnID, True, None, None, True)
        stables = ['spawn_skill',
         'spawn_resistance',
         'spawn_spell',
         'spawn_stat']
        for t in stables:
            cursor.execute('SELECT * FROM %s WHERE spawn_id = %i;' % (t, sid))
            values = GenerateInsertValues(t, cursor.fetchall(), playerID, characterID, spawnID)
            dstCursor.executemany('INSERT INTO %s VALUES(%s)' % (t, TVALUES[t]), values)

        dstConn.commit()
    except:
        error = True
        traceback.print_exc()
        dstConn.rollback()

    dstCursor.close()
    cursor.close()
    dbconn.close()
    if not error:
        print 'character %s (%d,%d) installation took %.1f seconds' % (cname,
         characterID,
         spawnID,
         time.time() - tm)
    return error


def InstallPlayerBuffer(publicName, buffer):
    global CREATE_PLAYER_TABLE_SQL
    if not CREATE_PLAYER_TABLE_SQL:
        Initialize()
    tm = time.time()
    from mud.world.player import Player
    try:
        dbuffer = zlib.decompress(buffer)
        dbname = '%s/player.%i.db' % (DB_TEMP, CLUSTER)
        f = open(dbname, 'wb')
        f.write(dbuffer)
        f.close()
        dbconn = sqlite.connect(dbname)
        cursor = dbconn.cursor()
        dstConn = Player._connection.transaction()
        dstCursor = Player._connection.getConnection().cursor()
    except:
        traceback.print_exc()
        return True

    error = False
    try:
        cursor.execute('SELECT public_name FROM player LIMIT 1;')
        pname = cursor.fetchone()[0]
        cursor.execute('SELECT * FROM player')
        values = GenerateInsertValues('player', cursor.fetchall())
        dstCursor.executemany('INSERT INTO player VALUES(%s)' % TVALUES['player'], values)
        dstCursor.execute("SELECT id FROM player where public_name = '%s' LIMIT 1;" % pname)
        playerID = dstCursor.fetchone()[0]
        ptables = ['player_monster_spawn']
        for t in ptables:
            cursor.execute('SELECT * FROM %s;' % t)
            values = GenerateInsertValues(t, cursor.fetchall(), playerID)
            dstCursor.executemany('INSERT INTO %s VALUES(%s)' % (t, TVALUES[t]), values)

        cursor.execute('SELECT * FROM item WHERE slot >= %i and slot < %i;' % (RPG_SLOT_BANK_BEGIN, RPG_SLOT_BANK_END))
        InstallItemList(cursor, dstCursor, cursor.fetchall(), playerID, None, None)
        dstConn.commit()
    except:
        error = True
        traceback.print_exc()
        dstConn.rollback()

    dstCursor.close()
    cursor.close()
    dbconn.close()
    if not error:
        print 'player %s %d installation took %.1f seconds' % (publicName, playerID, time.time() - tm)
    return error


def Initialize():
    global CREATE_CHARACTER_TABLE_SQL
    global DB_TEMP
    global CREATE_PLAYER_TABLE_SQL
    dbconn = sqlite.connect(GetDBURI())
    cursor = dbconn.cursor()
    CREATE_PLAYER_TABLE_SQL = ''
    for t in PLAYER_TABLES:
        try:
            cursor.execute('PRAGMA table_info(%s);' % t)
            TATTR[t] = []
            sql = []
            c = 0
            for col in cursor.fetchall():
                TATTR[t].append(UnderToMixed(col[1]))
                sql.append('%s %s' % (col[1], col[2]))
                c += 1

            TVALUES[t] = ','.join('?' * c)
            CREATE_PLAYER_TABLE_SQL += 'CREATE TABLE %s (%s);' % (t, ', '.join(sql))
        except:
            traceback.print_exc()

    CREATE_CHARACTER_TABLE_SQL = ''
    for t in CHARACTER_TABLES:
        try:
            cursor.execute('PRAGMA table_info(%s);' % t)
            TATTR[t] = []
            sql = []
            c = 0
            for col in cursor.fetchall():
                TATTR[t].append(UnderToMixed(col[1]))
                sql.append('%s %s' % (col[1], col[2]))
                c += 1

            TVALUES[t] = ','.join('?' * c)
            CREATE_CHARACTER_TABLE_SQL += 'CREATE TABLE %s (%s);' % (t, ', '.join(sql))
        except:
            traceback.print_exc()

    cursor.close()
    dbconn.close()
    if os.path.exists('R:/'):
        DB_TEMP = 'R:/tmp'
    if not os.path.exists(DB_TEMP):
        os.makedirs(DB_TEMP)


def ExtractItemList(cursor, excursor, itemList, indirect = False):
    if indirect:
        for item in itemList:
            itemID = item[0]
            cursor.execute('SELECT * FROM item WHERE id=? LIMIT 1;', (itemID,))
            excursor.executemany('INSERT INTO item VALUES(%s)' % TVALUES['item'], cursor.fetchall())
            cursor.execute('SELECT * FROM item_variant WHERE item_id=?;', (itemID,))
            excursor.executemany('INSERT INTO item_variant VALUES(%s)' % TVALUES['item_variant'], cursor.fetchall())
            try:
                cursor.execute('SELECT content_id FROM item_container_content WHERE item_id=?;', (itemID,))
                ExtractItemList(cursor, excursor, cursor.fetchall(), True)
                cursor.execute('SELECT * FROM item_container_content WHERE item_id=?;', (itemID,))
                excursor.executemany('INSERT INTO item_container_content VALUES(%s)' % TVALUES['item_container_content'], cursor.fetchall())
            except:
                traceback.print_exc()
                print "Probably a database that didn't yet hear of the introduction of item containers."

    else:
        for item in itemList:
            itemID = item[0]
            cursor.execute('SELECT * FROM item_variant WHERE item_id=?;', (itemID,))
            excursor.executemany('INSERT INTO item_variant VALUES(%s)' % TVALUES['item_variant'], cursor.fetchall())
            try:
                cursor.execute('SELECT content_id FROM item_container_content WHERE item_id=?;', (itemID,))
                ExtractItemList(cursor, excursor, cursor.fetchall(), True)
                cursor.execute('SELECT * FROM item_container_content WHERE item_id=?;', (itemID,))
                excursor.executemany('INSERT INTO item_container_content VALUES(%s)' % TVALUES['item_container_content'], cursor.fetchall())
            except:
                traceback.print_exc()
                print "Probably a database that didn't yet hear of the introduction of item containers."

        excursor.executemany('INSERT INTO item VALUES(%s)' % TVALUES['item'], itemList)


def ExtractPlayer(publicName, pid, cid, append = True):
    if not CREATE_PLAYER_TABLE_SQL:
        Initialize()
    tm = time.time()
    from mud.world.player import Player
    try:
        dbname = '%s/player_ex.%i.db' % (DB_TEMP, CLUSTER)
        try:
            os.remove(dbname)
        except:
            pass

        dbconn = Player._connection.getConnection()
        cursor = dbconn.cursor()
        exconn = sqlite.connect(dbname)
        excursor = exconn.cursor()
        excursor.executescript(CREATE_PLAYER_TABLE_SQL)
        cursor.execute('SELECT * FROM player WHERE id = %i LIMIT 1;' % pid)
        excursor.executemany('INSERT INTO player VALUES(%s)' % TVALUES['player'], cursor.fetchall())
        ptables = ['player_monster_spawn']
        for t in ptables:
            cursor.execute('SELECT * FROM %s WHERE player_id = %i;' % (t, pid))
            excursor.executemany('INSERT INTO %s VALUES(%s)' % (t, TVALUES[t]), cursor.fetchall())

        cursor.execute('SELECT * FROM item WHERE player_id = %i and slot >= %i and slot < %i;' % (pid, RPG_SLOT_BANK_BEGIN, RPG_SLOT_BANK_END))
        ExtractItemList(cursor, excursor, cursor.fetchall())
        excursor.close()
        exconn.commit()
        exconn.close()
        f = open(dbname, 'rb')
        buff = f.read()
        f.close()
        pbuffer = zlib.compress(buff)
        dbname = '%s/char_ex.%i.db' % (DB_TEMP, CLUSTER)
        try:
            os.remove(dbname)
        except:
            pass

        exconn = sqlite.connect(dbname)
        excursor = exconn.cursor()
        tm = time.time()
        excursor.executescript(CREATE_CHARACTER_TABLE_SQL)
        cursor.execute('SELECT * FROM character WHERE id = %i;' % cid)
        excursor.executemany('INSERT INTO character VALUES(%s)' % TVALUES['character'], cursor.fetchall())
        ctables = ['character_spell',
         'character_skill',
         'character_advancement',
         'character_dialog_choice',
         'spell_store',
         'character_faction']
        for t in ctables:
            cursor.execute('SELECT * FROM %s WHERE character_id = %i;' % (t, cid))
            excursor.executemany('INSERT INTO %s VALUES(%s)' % (t, TVALUES[t]), cursor.fetchall())

        cursor.execute('SELECT * FROM item WHERE character_id = %i and (slot >= %i or slot < %i) and slot != -1;' % (cid, RPG_SLOT_BANK_END, RPG_SLOT_BANK_BEGIN))
        ExtractItemList(cursor, excursor, cursor.fetchall())
        cursor.execute('SELECT * FROM character_vault_item WHERE character_id = %i;' % cid)
        excursor.executemany('INSERT INTO character_vault_item VALUES(%s)' % TVALUES['character_vault_item'], cursor.fetchall())
        cursor.execute('SELECT item_id FROM character_vault_item WHERE character_id = %i;' % cid)
        ExtractItemList(cursor, excursor, cursor.fetchall(), True)
        cursor.execute("SELECT name,race,pclass_internal,sclass_internal,tclass_internal,plevel,slevel,tlevel,realm FROM spawn WHERE character_id = '%i' LIMIT 1;" % cid)
        cvalues = cursor.fetchone()
        cursor.execute('SELECT * FROM spawn WHERE character_id = %i LIMIT 1;' % cid)
        v = cursor.fetchone()
        sid = v[0]
        excursor.executemany('INSERT INTO spawn VALUES(%s)' % TVALUES['spawn'], (v,))
        stables = ['spawn_skill',
         'spawn_resistance',
         'spawn_spell',
         'spawn_stat']
        for t in stables:
            cursor.execute('SELECT * FROM %s WHERE spawn_id = %i;' % (t, sid))
            excursor.executemany('INSERT INTO %s VALUES(%s)' % (t, TVALUES[t]), cursor.fetchall())

        excursor.close()
        exconn.commit()
        exconn.close()
        f = open(dbname, 'rb')
        buff = f.read()
        f.close()
        cbuffer = zlib.compress(buff)
        cursor.close()
        v = (publicName,
         pbuffer,
         cbuffer,
         cvalues)
        if append:
            PLAYER_BUFFERS.append(v)
        print 'player and character export took %.1f seconds' % (time.time() - tm)
        return v
    except:
        traceback.print_exc()
        return None

    return None


_underToMixedRE = re.compile('_(.)')

def UnderToMixed(name):
    if name.endswith('_id'):
        return UnderToMixed(name[:-3] + 'ID')
    return _underToMixedRE.sub(lambda m: m.group(1).upper(), name)