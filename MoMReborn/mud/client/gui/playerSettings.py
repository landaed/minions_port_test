# Embedded file name: mud\client\gui\playerSettings.pyo
from tgenative import *
from mud.tgepython.console import TGEExport
from pysqlite2 import dbapi2 as sqlite
from md5 import md5
import os, shutil
import traceback
from mud.utils import *
from mud.gamesettings import *
from mud.world.defines import *
from pointsOfInterest import POI
from mud.client.playermind import TOGGLEABLECHANNELS
from defaultCommandsWnd import GetDefaultCommand
from skillinfo import GetSkillInfo
from defaultMacros import CreateDefaultMacros
from tomeGui import TomeGui
TomeGui = TomeGui.instance
WINDOW_DAT_VERSION = 2
WINDOW_INITIAL = {'PARTYWND_WINDOW': (523,
                     73,
                     -1,
                     -1,
                     0),
 'CHARMINIWND_WINDOW': (0,
                        0,
                        -1,
                        -1,
                        1),
 'MACROWND_WINDOW': (302,
                     580,
                     -1,
                     -1,
                     1),
 'TOMEGUI_WINDOW': (340,
                    0,
                    -1,
                    -1,
                    1),
 'CHATGUI_WINDOW': (732,
                    580,
                    292,
                    188,
                    1),
 'GAMETEXTGUI_WINDOW': (0,
                        580,
                        292,
                        188,
                        1),
 'ITEMINFOWND_WINDOW': (352,
                        158,
                        -1,
                        -1,
                        -1),
 'DEFAULTCOMMANDSWND_WINDOW': (464,
                               196,
                               -1,
                               -1,
                               0),
 'NPCWND_WINDOW': (119,
                   79,
                   -1,
                   -1,
                   -1),
 'GAMEOPTIONSWND_WINDOW': (434,
                           302,
                           -1,
                           -1,
                           -1),
 'ALLIANCEWND_WINDOW': (456,
                        0,
                        -1,
                        -1,
                        0),
 'LEADERWND_WINDOW': (192,
                      232,
                      -1,
                      -1,
                      0),
 'TRACKINGWND_WINDOW': (370,
                        282,
                        364,
                        316,
                        -1),
 'MAPWND_WINDOW': (0,
                   0,
                   300,
                   325,
                   0),
 'HELPWND_WINDOW': (337,
                    180,
                    -1,
                    -1,
                    0),
 'JOURNALWND_WINDOW': (337,
                       180,
                       -1,
                       -1,
                       0),
 'PETWND_WINDOW': (337,
                   180,
                   -1,
                   -1,
                   -1),
 'BUFFWND_WINDOW': (903,
                    0,
                    -1,
                    -1,
                    0),
 'VAULTWND_WINDOW': (541,
                     170,
                     -1,
                     -1,
                     -1),
 'FRIENDSWND_WINDOW': (309,
                       77,
                       -1,
                       -1,
                       0),
 'CRAFTINGWND_WINDOW': (150,
                        100,
                        -1,
                        -1,
                        -1),
 'LOOTWND_WINDOW': (150,
                    100,
                    -1,
                    -1,
                    -1)}

def fillWindow(cursor):
    for name, data in WINDOW_INITIAL.iteritems():
        values = [None, name]
        values.extend(data)
        cursor.execute('INSERT INTO window VALUES(?,?,?,?,?,?,?);', values)

    return


PLAYERSETTINGS_CREATETABLES = '\nCREATE TABLE world\n(\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    name TEXT,\n    singleplayer INTEGER\n);\n\nCREATE TABLE character\n(\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    name TEXT,\n    realm INTEGER,\n    world_id INTEGER,\n    last_party INTEGER DEFAULT 0,\n    p_xp_gain FLOAT DEFAULT 1.0,\n    s_xp_gain FLOAT DEFAULT 0.0,\n    t_xp_gain FLOAT DEFAULT 0.0,\n    encounter_pve_zone INTEGER DEFAULT 1,\n    encounter_pve_death INTEGER DEFAULT 1,\n    link_mouse_target INTEGER DEFAULT 1,\n    link_character_target TEXT DEFAULT "",\n    default_target TEXT DEFAULT ""\n);\n\nCREATE TABLE journal_entry\n(\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    topic TEXT,\n    entry TEXT,\n    text TEXT,\n    character_id INTEGER,\n    hidden INTEGER DEFAULT 0\n);\n\nCREATE TABLE poi\n(\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    zone TEXT,\n    x_coord FLOAT,\n    y_coord FLOAT,\n    z_coord FLOAT,\n    description TEXT,\n    character_id INTEGER\n);\n\nCREATE TABLE friend\n(\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    name TEXT\n);\n\nCREATE TABLE ignore\n(\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    name TEXT\n);\n\nCREATE TABLE macro\n(\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    name TEXT DEFAULT "",\n    page INTEGER,\n    slot INTEGER,\n    hotkey TEXT DEFAULT "",\n    icon TEXT DEFAULT "",\n    description TEXT DEFAULT "",\n    wait_all INTEGER DEFAULT 1,\n    manual_delay INTEGER DEFAULT 0,\n    character_id INTEGER\n);\n\nCREATE TABLE macro_line\n(\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    line_index INTEGER,\n    command TEXT DEFAULT "",\n    mandatory INTEGER DEFAULT 1,\n    delay_after INTEGER DEFAULT 0,\n    macro_id INTEGER\n);\n\nCREATE TABLE window\n(\n    id INTEGER PRIMARY KEY AUTOINCREMENT,\n    name TEXT,\n    x_coord INTEGER,\n    y_coord INTEGER,\n    x_extent INTEGER,\n    y_extent INTEGER,\n    active INTEGER\n);\n\nCREATE TABLE misc\n(\n    channel_filters INTEGER DEFAULT %i,\n    window_version INTEGER DEFAULT %i,\n    last_realm INTEGER DEFAULT %i,\n    extended_macros INTEGER DEFAULT 1\n);\n' % (TOGGLEABLECHANNELS['COMBAT'], WINDOW_DAT_VERSION, RPG_REALM_DEFAULT)
PlayerSettingsFillScripts = {'window': fillWindow,
 'misc': 'INSERT INTO misc VALUES(%i,%i,%i,%i);' % (TOGGLEABLECHANNELS['COMBAT'],
          WINDOW_DAT_VERSION,
          RPG_REALM_DEFAULT,
          1)}
PLAYERSETTINGS = None

class PlayerSettings():

    def __init__(self):
        dbpath = '%s/data/settings.db' % GAMEROOT
        if os.path.exists(dbpath):
            newDB = False
        else:
            print 'local settings database is not found'
            newDB = True
            preApp = False
            try:
                found = None
                if PLATFORM == 'mac':
                    if os.path.exists('../../minions.of.mirth/data/settings.db'):
                        preApp = True
                    for test in ['../../minions.of.mirth/data/settings.db', '/Applications/MinionsOfMirth/common/minions.of.mirth/data/settings.db']:
                        if os.path.exists(test):
                            found = test
                            break

                else:
                    for test in ['C:\\Program Files\\Minions of Mirth\\common\\minions.of.mirth\\data\\settings.db', 'C:\\Program Files (x86)\\Minions of Mirth\\common\\minions.of.mirth\\data\\settings.db']:
                        if os.path.exists(test):
                            found = test
                            break
                        test = test[2:]
                        if os.path.exists(test):
                            found = test
                            break

                if found is not None:
                    print 'found old settings %s' % found
                    shutil.copy2(found, dbpath)
                    newDB = False
            except:
                pass

            pname = TGEGetGlobal('$pref::PublicName')
            password = TGEGetGlobal('$pref::MasterPassword')
            if not pname or not password:
                try:
                    found = None
                    if PLATFORM == 'mac':
                        for test in ['../../minions.of.mirth/client/prefs.cs', '/Applications/MinionsOfMirth/common/minions.of.mirth/client/prefs.cs']:
                            if os.path.exists(test):
                                found = test
                                break

                    else:
                        for test in ['C:\\Program Files\\Minions of Mirth\\common\\minions.of.mirth\\client\\prefs.cs', 'C:\\Program Files (x86)\\Minions of Mirth\\common\\minions.of.mirth\\client\\prefs.cs']:
                            if os.path.exists(test):
                                found = test
                                break
                            test = test[2:]
                            if os.path.exists(test):
                                found = test
                                break

                    if found is not None:
                        pname = ''
                        password = ''
                        print 'found old prefs at %s' % found
                        f = open(found, 'rt')
                        try:
                            for line in f:
                                if line.startswith('$pref::PublicName '):
                                    p = line.split('"')
                                    pname = p[1]
                                elif line.startswith('$pref::MasterPassword '):
                                    p = line.split('"')
                                    password = p[1]

                        except:
                            pass

                        f.close()
                        if pname and password:
                            print "found old PublicName '%s' MasterPassword '%s'" % (pname, password)
                            TGESetGlobal('$pref::PublicName', pname)
                            TGESetGlobal('$pref::MasterPassword', password)
                except:
                    pass

            if preApp:
                print 'pre-app setup, cleaning up'
                try:
                    for fname in ['./minions.of.mirth/client/prefs.cs', './minions.of.mirth/client/config.cs']:
                        test = os.path.normpath(os.path.join('../..', fname))
                        if os.path.exists(test):
                            try:
                                shutil.move(test, fname)
                            except:
                                pass

                    for path, ds, fs in os.walk('../../minions.of.mirth/data/worlds/singleplayer'):
                        for d in ds:
                            sname = os.path.join('../../minions.of.mirth/data/worlds/singleplayer', d)
                            dname = os.path.join('./minions.of.mirth/data/worlds/singleplayer', d)
                            try:
                                shutil.move(sname, dname)
                            except:
                                pass

                    for fname in ['./cache',
                     './restore',
                     './common',
                     './logs',
                     './minions.of.mirth']:
                        test = os.path.join('../..', fname)
                        try:
                            shutil.rmtree(test)
                        except:
                            pass

                    for fname in ['args.txt',
                     'main.cs.dso',
                     'patchlist.txt',
                     'patchfh.txt',
                     'patch.cpz']:
                        test = os.path.join('../..', fname)
                        try:
                            os.remove(test)
                        except:
                            pass

                    print 'done cleaning up'
                except:
                    pass

        self.connection = sqlite.connect(dbpath, isolation_level=None)
        give_perm(dbpath)
        self.connection.text_factory = str
        cursor = self.cursor = self.connection.cursor()
        if newDB:
            cursor.executescript(PLAYERSETTINGS_CREATETABLES)
            for table, filler in PlayerSettingsFillScripts.iteritems():
                try:
                    filler(cursor)
                except:
                    cursor.execute(filler)

        else:
            self.updateDatabase()
        self.channelFilters, self.windowVersion, self.lastRealm, self.useExtendedMacros = cursor.execute('SELECT channel_filters,window_version,last_realm,extended_macros FROM misc LIMIT 1;').fetchone()
        from macro import MACROMASTER
        MACROMASTER.extendedMacros = self.useExtendedMacros
        self.loadFriends()
        self.loadIgnored()
        self.windows = dict()
        self.worldname = ''
        self.worldID = 0
        self.newWorld = False
        self.zone = ''
        self.charInfos = None
        self.charIndex = 0
        self.characters = dict()
        self.characterID = 0
        self.poi = dict()
        self.journal = None
        self.macroCollection = None
        return

    def updateDatabase(self):
        cursor = self.cursor
        memconn = sqlite.connect(':memory:')
        memconn.text_factory = str
        memconn.isolation_level = None
        memcursor = memconn.cursor()
        memcursor.executescript(PLAYERSETTINGS_CREATETABLES)
        q = "SELECT name,sql FROM sqlite_master WHERE type='table' and name<>'sqlite_sequence';"
        memlist = dict(memcursor.execute(q).fetchall())
        curlist = dict(cursor.execute(q).fetchall())
        if memlist == curlist:
            print 'local settings database layout is up to date'
            memcursor.close()
            memconn.close()
            return
        else:
            print 'updating local settings database layout'
            tableAdd = []
            tableAlter = {}
            for name, sql in memlist.iteritems():
                try:
                    prevsql = curlist[name]
                    if prevsql != sql:
                        tableAlter[name] = sql
                    del curlist[name]
                except KeyError:
                    tableAdd.append(name)

            tableDrop = curlist.iterkeys()
            for newTable in tableAdd:
                cursor.execute(memlist[newTable])
                try:
                    filler = PlayerSettingsFillScripts[newTable]
                    try:
                        filler(cursor)
                    except:
                        cursor.execute(filler)

                except KeyError:
                    pass

            for dropTable in tableDrop:
                cursor.execute('DROP TABLE %s;' % dropTable)

            for alterTable, newsql in tableAlter.iteritems():
                curSchema = cursor.execute('PRAGMA TABLE_INFO(%s);' % alterTable).fetchall()
                memSchema = memcursor.execute('PRAGMA TABLE_INFO(%s);' % alterTable).fetchall()
                newColumns = dict(((column[1], column[4]) for column in memSchema))
                curColumns = tuple((column[1] for column in curSchema if column[1] in newColumns))
                curColnum = len(curColumns)
                curColumns = ','.join(curColumns)
                curTableData = cursor.execute('SELECT %s FROM %s;' % (curColumns, alterTable)).fetchall()
                cursor.execute('DROP TABLE %s;' % alterTable)
                cursor.execute(newsql)
                for data in curTableData:
                    cursor.execute('INSERT INTO %s (%s) VALUES(%s)' % (alterTable, curColumns, ','.join('?' * curColnum)), data)

            return

    def updateWorld(self):
        cursor = self.cursor
        worldname = TGEGetGlobal('$Py::WORLDNAME')
        singleplayer = int(TGEGetGlobal('$Py::ISSINGLEPLAYER'))
        if self.worldname != worldname:
            self.newWorld = True
            self.worldname = worldname
            data = cursor.execute('SELECT id,singleplayer FROM world WHERE name=? AND (singleplayer=? OR singleplayer isnull) LIMIT 1;', (worldname, singleplayer)).fetchone()
            if data == None:
                cursor.execute('INSERT INTO world (name,singleplayer) VALUES(?,?);', (worldname, singleplayer))
                self.worldID = cursor.execute('SELECT id FROM world WHERE name=? AND singleplayer=? LIMIT 1;', (worldname, singleplayer)).fetchone()[0]
            else:
                self.worldID, dbsingleplayer = data
                if dbsingleplayer == None:
                    cursor.execute('UPDATE world SET singleplayer=? WHERE id=?;', (singleplayer, self.worldID))
        try:
            realm = int(TGEGetGlobal('$Py::REALM'))
            if self.lastRealm != realm:
                self.lastRealm = realm
                cursor.execute('UPDATE misc SET last_realm=?;', (realm,))
        except:
            pass

        return

    def updateZone(self, zoneName):
        self.updateWorld()
        self.zone = zoneName
        if self.newWorld:
            self.newWorld = False
            channelFilters = self.channelFilters
            from mud.client.playermind import PLAYERMIND
            if channelFilters & TOGGLEABLECHANNELS['H']:
                TomeGui.onHelpChannelToggle(False, True)
            if channelFilters & TOGGLEABLECHANNELS['O']:
                TomeGui.onOffTopicChannelToggle(False, True)
            if channelFilters & TOGGLEABLECHANNELS['M']:
                TomeGui.onGlobalChannelToggle(False, True)
            if channelFilters & TOGGLEABLECHANNELS['W']:
                PLAYERMIND.doCommand('CHANNEL', [0, 'world', 'off'])
            if channelFilters & TOGGLEABLECHANNELS['Z']:
                PLAYERMIND.doCommand('CHANNEL', [0, 'zone', 'off'])
            if not channelFilters & TOGGLEABLECHANNELS['COMBAT']:
                PLAYERMIND.doCommand('CHANNEL', [0, 'combat', 'on'])
        self.loadPOI()

    def renameCharacter(self, oldName, newName):
        cursor = self.cursor
        self.updateWorld()
        try:
            cursor.execute('UPDATE character SET name=? WHERE world_id=? AND name=?;', (newName, self.worldID, oldName))
        except:
            traceback.print_exc()

    def setCharacterInfos(self, cinfos):
        if cinfos == self.charInfos:
            return
        else:
            cursor = self.cursor
            self.updateWorld()
            realm = self.lastRealm
            cursor.execute('UPDATE character SET last_party=? WHERE world_id=? AND last_party=?;', (0, self.worldID, realm))
            self.charInfos = cinfos
            self.charIndex = 0
            characters = {}
            for index, cinfo in cinfos.iteritems():
                characterID = cursor.execute('SELECT id FROM character WHERE world_id=? AND (realm=? OR realm isnull) AND name=? LIMIT 1;', (self.worldID, realm, cinfo.NAME)).fetchone()
                if characterID == None:
                    cursor.execute('INSERT INTO character (name,realm,world_id,last_party) VALUES(?,?,?,?);', (cinfo.NAME,
                     realm,
                     self.worldID,
                     realm))
                    characters[index] = cursor.execute('SELECT id FROM character WHERE world_id=? AND realm=? AND name=? LIMIT 1;', (self.worldID, realm, cinfo.NAME)).fetchone()[0]
                else:
                    characterID = characterID[0]
                    cursor.execute('UPDATE character SET realm=?, last_party=? WHERE id=?;', (realm, realm, characterID))
                    characters[index] = characterID

            self.characterID = characters[self.charIndex]
            for charIndex, characterID in characters.iteritems():
                charSettings = cinfos[charIndex].clientSettings = dict()
                pXPGain, sXPGain, tXPGain, encounterPVEZone, encounterPVEDeath, linkMouseTarget, linkCharacterTarget, defaultTarget = cursor.execute('SELECT p_xp_gain,s_xp_gain,t_xp_gain,encounter_pve_zone,encounter_pve_death,link_mouse_target,link_character_target,default_target FROM character WHERE id=? LIMIT 1;', (characterID,)).fetchone()
                charSettings['PXPGAIN'] = pXPGain
                charSettings['SXPGAIN'] = sXPGain
                charSettings['TXPGAIN'] = tXPGain
                charSettings['ENCOUNTERPVEZONE'] = encounterPVEZone
                charSettings['ENCOUNTERPVEDIE'] = encounterPVEDeath
                charSettings['LINKMOUSETARGET'] = linkMouseTarget
                charSettings['LINKTARGET'] = linkCharacterTarget
                charSettings['DEFAULTTARGET'] = defaultTarget

            if self.characters != characters:
                self.characters = characters
                self.loadMacros()
                self.updateJournal()
            else:
                from macro import MACROMASTER
                for charIndex in characters.iterkeys():
                    MACROMASTER.updateAttackMacros(charIndex, cinfos[charIndex].RAPIDMOBINFO.AUTOATTACK)

            if self.zone:
                self.loadPOI()
            return

    def storeCharacterSettings(self):
        cursor = self.cursor
        for charIndex, characterID in self.characters.iteritems():
            charSettings = self.charInfos[charIndex].clientSettings
            cursor.execute('UPDATE character SET p_xp_gain=?, s_xp_gain=?, t_xp_gain=?, encounter_pve_zone=?, encounter_pve_death=?, link_mouse_target=?, link_character_target=?, default_target=? WHERE id=?;', (charSettings['PXPGAIN'],
             charSettings['SXPGAIN'],
             charSettings['TXPGAIN'],
             charSettings['ENCOUNTERPVEZONE'],
             charSettings['ENCOUNTERPVEDIE'],
             charSettings['LINKMOUSETARGET'],
             charSettings['LINKTARGET'],
             charSettings['DEFAULTTARGET'],
             characterID))

    def updateMainCharIndex(self, index):
        if index >= 0 and index != self.charIndex:
            self.charIndex = index
            self.characterID = self.characters[index]
            self.updateJournal()
            self.loadPOI()

    def characterDeleted(self, charname):
        cursor = self.cursor
        charID = cursor.execute('SELECT id FROM character WHERE world_id=? AND realm=? AND name=?;', (self.worldID, self.lastRealm, charname)).fetchone()
        if charID == None:
            return
        else:
            charID = charID[0]
            cursor.execute('DELETE FROM poi WHERE character_id=?;', (charID,))
            cursor.execute('DELETE FROM journal_entry WHERE character_id=?;', (charID,))
            macroIDs = cursor.execute('SELECT id FROM macro WHERE character_id=?;', (charID,))
            for macroID in macroIDs:
                cursor.execute('DELETE FROM macro_line WHERE macro_id=?;', (macroID[0],))

            cursor.execute('DELETE FROM macro WHERE character_id=?;', (charID,))
            cursor.execute('DELETE FROM character WHERE id=?;', (charID,))
            return

    def loadWindowSettings(self):
        cursor = self.cursor
        if self.windowVersion < WINDOW_DAT_VERSION:
            print 'Stored window data is of old version, deleting and recreating window data.'
            cursor.execute('DELETE FROM window;')
            fillWindow(cursor)
            cursor.execute('UPDATE misc SET window_version=?;', (WINDOW_DAT_VERSION,))
        windowSettings = cursor.execute('SELECT * FROM window;')
        self.windows = {}
        resolution = TGECall('getRes').split(' ')
        screenWidth, screenHeight = int(resolution[0]), int(resolution[1])
        for id, name, x_coord, y_coord, x_extent, y_extent, active in windowSettings:
            try:
                window = TGEObject(name)
            except:
                continue

            resizable = x_extent != -1 and y_extent != -1
            self.windows[name] = (window, active, resizable)
            if resizable:
                if x_extent > screenWidth:
                    x_extent = screenWidth
                if y_extent > screenHeight:
                    y_extent = screenHeight
            else:
                width, height = window.extent.split(' ')
                x_extent = int(width)
                y_extent = int(height)

            def correct(x_coord, x_extent, screenWidth, resizable):
                if x_coord + x_extent > screenWidth:
                    x_coord = screenWidth - x_extent
                    if x_coord < 0:
                        x_coord = 0
                        if resizable:
                            x_extent = screenWidth
                return (x_coord, x_extent)

            x_coord, x_extent = correct(x_coord, x_extent, screenWidth, resizable)
            y_coord, y_extent = correct(y_coord, y_extent, screenHeight, resizable)
            window.resize(x_coord, y_coord, x_extent, y_extent)
            if active == 1:
                TGEEval('canvas.pushDialog(%s);' % name[:-7])

    def storeWindowSettings(self):
        for name, windowInfo in self.windows.iteritems():
            window, active, resizable = windowInfo
            posX, posY = window.position.split(' ')
            x_coord = int(posX)
            y_coord = int(posY)
            if resizable:
                width, height = window.extent.split(' ')
                x_extent = int(width)
                y_extent = int(height)
            else:
                x_extent = y_extent = -1
            if active > -1:
                if int(window.isAwake()):
                    active = 1
                else:
                    active = 0
            self.cursor.execute('UPDATE window SET x_coord=?, y_coord=?, x_extent=?, y_extent=?, active=? WHERE name=?;', (x_coord,
             y_coord,
             x_extent,
             y_extent,
             active,
             name))

    def checkWindowPositions(self):
        resolution = TGECall('getRes').split(' ')
        screenWidth, screenHeight = int(resolution[0]), int(resolution[1])
        for name, windowInfo in self.windows.iteritems():
            window, active, resizable = windowInfo
            posX, posY = window.position.split(' ')
            x_coord = int(posX)
            y_coord = int(posY)
            width, height = window.extent.split(' ')
            x_extent = int(width)
            y_extent = int(height)
            if x_coord + x_extent > screenWidth + 5 or y_coord + y_extent > screenHeight + 5:
                initial = WINDOW_INITIAL[name]
                window.position = '%d %d' % (initial[0], initial[1])

    def loadLastParty(self, getRealm = None):
        cursor = self.cursor
        self.updateWorld()
        wdirname = md5(self.worldname).hexdigest()
        single = int(TGEGetGlobal('$Py::ISSINGLEPLAYER'))
        if single:
            gdirname = 'single'
        else:
            gdirname = 'multiplayer'
        filename = '%s/data/settings/%s/%s/lastparty.dat' % (GAMEROOT, gdirname, wdirname)
        if os.path.exists(filename):
            try:
                from cPickle import load as pickleLoad
                f = file(filename, 'rb')
                data = pickleLoad(f)
                f.close()
                lastParty = data['PARTY']
                realm = RPG_REALM_LIGHT
                if data['DARKNESS']:
                    realm = RPG_REALM_DARKNESS
                elif data['MONSTER']:
                    realm = RPG_REALM_MONSTER
                cursor.execute('UPDATE misc SET last_realm=?;', (realm,))
                self.lastRealm = realm
                for name in lastParty:
                    charID = cursor.execute('SELECT id FROM character WHERE world_id=? AND (realm=? OR realm isnull) AND name=? LIMIT 1;', (self.worldID, realm, name)).fetchone()
                    if charID == None:
                        cursor.execute('INSERT INTO character (name,world_id,realm,last_party) VALUES(?,?,?,?);', (name,
                         self.worldID,
                         realm,
                         realm))
                    else:
                        cursor.execute('UPDATE character SET realm=?, last_party=? WHERE id=?;', (realm, realm, charID[0]))

            except:
                traceback.print_exc()

            os.remove(filename)
        if getRealm == None:
            getRealm = self.lastRealm
        lastParty = cursor.execute('SELECT name FROM character WHERE world_id=? AND (realm=? OR realm isnull) AND last_party=?;', (self.worldID, getRealm, getRealm))
        lastParty = (member[0] for member in lastParty)
        return (getRealm, lastParty)

    def loadFriends(self):
        cursor = self.cursor
        filename = '%s/data/settings/friends.dat' % GAMEROOT
        if os.path.exists(filename):
            from cPickle import load as pickleLoad
            try:
                f = file(filename, 'rb')
                friends = pickleLoad(f)
                f.close()
                for friend in friends:
                    cursor.execute('INSERT INTO friend (name) VALUES(?);', (friend,))

            except:
                traceback.print_exc()

            os.remove(filename)
        friends = cursor.execute('SELECT name FROM friend;')
        self.friends = list((friend[0] for friend in friends))

    def addFriend(self, friend):
        friend = friend.upper()
        if friend not in self.friends:
            self.cursor.execute('INSERT INTO friend (name) VALUES(?);', (friend,))
            self.friends.append(friend)
            self.friends.sort()
            return True
        else:
            return False

    def removeFriend(self, friend):
        friend = friend.upper()
        if friend in self.friends:
            self.cursor.execute('DELETE FROM friend WHERE name=?;', (friend,))
            self.friends.remove(friend)
            return True
        else:
            return False

    def loadIgnored(self):
        cursor = self.cursor
        filename = '%s/data/settings/ignore.dat' % GAMEROOT
        if os.path.exists(filename):
            from cPickle import load as pickleLoad
            try:
                f = file(filename, 'rb')
                ignored = pickleLoad(f)
                f.close()
                for ignore in ignored:
                    cursor.execute('INSERT INTO ignore (name) VALUES(?);', (ignore,))

            except:
                traceback.print_exc()

            os.remove(filename)
        ignored = cursor.execute('SELECT name FROM ignore;')
        self.ignored = list((ignore[0] for ignore in ignored))

    def ignore(self, nick):
        nick = nick.replace('_', ' ').upper()
        if nick not in self.ignored:
            self.cursor.execute('INSERT INTO ignore (name) VALUES(?);', (nick,))
            self.ignored.append(nick)
            self.ignored.sort()
            return True
        else:
            return False

    def unignore(self, nick):
        nick = nick.replace('_', ' ').upper()
        if nick in self.ignored:
            self.cursor.execute('DELETE FROM ignore WHERE name=?;', (nick,))
            self.ignored.remove(nick)
            return True
        else:
            return False

    def loadPOI(self):
        poi = self.cursor.execute('SELECT description,x_coord,y_coord,z_coord FROM poi WHERE zone=? AND character_id=?;', (self.zone, self.characterID))
        if poi:
            self.poi = dict(((description, (x_coord, y_coord, z_coord)) for description, x_coord, y_coord, z_coord in poi))
        else:
            self.poi = dict()
        if POI.has_key(self.zone):
            self.poi.update(POI[self.zone])

    def addPOI(self, desc, loc, zoneName = None):
        if zoneName == None:
            zoneName = self.zone
        if len(desc) > 35:
            TomeGui.receiveGameText(RPG_MSG_GAME_DENIED, "For your own good, don't describe points of interest with more than 35 characters.\\n")
        else:
            self.poi[desc] = loc
            self.cursor.execute('INSERT INTO poi (zone,description,x_coord,y_coord,z_coord,character_id) VALUES(?,?,?,?,?,?);', (zoneName,
             desc,
             loc[0],
             loc[1],
             loc[2],
             self.characterID))
        return

    def removePOI(self, desc, zoneName = None):
        if zoneName == None:
            zoneName = self.zone
        if not self.poi.has_key(desc):
            TomeGui.receiveGameText(RPG_MSG_GAME_DENIED, 'Point of interest of name %s could not be found.\\n' % desc)
        else:
            del self.poi[desc]
            self.cursor.execute('DELETE FROM poi WHERE zone=? AND description=? AND character_id=?;', (zoneName, desc, self.characterID))
        return

    def setChannel(self, channel, on):
        if on:
            newFilters = self.channelFilters & ~channel
        else:
            newFilters = self.channelFilters | channel
        if newFilters != self.channelFilters:
            self.channelFilters = newFilters
            self.cursor.execute('UPDATE misc SET channel_filters=?;', (newFilters,))

    def updateJournal(self):
        cursor = self.cursor
        self.updateWorld()
        loadOld = False
        wdirname = md5(self.worldname).hexdigest()
        single = int(TGEGetGlobal('$Py::ISSINGLEPLAYER'))
        if single:
            gdirname = 'single'
        else:
            gdirname = 'multiplayer'
        dirname = '%s/data/settings/%s/%s' % (GAMEROOT, gdirname, wdirname)
        filename = '%s/%s_journal.dat' % (dirname, self.charInfos[self.charIndex].NAME)
        if os.path.exists(filename):
            loadOld = True
        else:
            if self.lastRealm == RPG_REALM_LIGHT:
                filename = '%s/journal.dat' % dirname
            elif self.lastRealm == RPG_REALM_DARKNESS:
                filename = '%s/journal_dark.dat' % dirname
            else:
                filename = '%s/journal_monster.dat' % dirname
            if os.path.exists(filename):
                print 'Could not find character specific journal, copying from old file ...'
                loadOld = True
        if loadOld == True:
            from cPickle import load as pickleLoad
            try:
                f = file(filename, 'rb')
                journal = pickleLoad(f)
                f.close()
                for topic, entryDict in journal.iteritems():
                    for entry, text in entryDict.iteritems():
                        cursor.execute('INSERT INTO journal_entry (topic,entry,text,character_id) VALUES(?,?,?,?);', (topic,
                         entry,
                         text,
                         self.characterID))

                del journal
            except:
                traceback.print_exc()

            os.remove(filename)
        journal = dict()
        journalData = cursor.execute('SELECT topic,entry,text,hidden FROM journal_entry WHERE character_id=?;', (self.characterID,))
        for topic, entry, text, hidden in journalData:
            journal.setdefault(topic, [{}, True])[0][entry] = [text, hidden]
            if not hidden:
                journal[topic][1] = False

        if len(journal) == 0:
            from journalWnd import CreateDefaultJournal
            journal = CreateDefaultJournal(self.lastRealm)
            for topic, topicData in journal.iteritems():
                for entry, entryData in topicData[0].iteritems():
                    cursor.execute('INSERT INTO journal_entry (topic,entry,text,character_id,hidden) VALUES(?,?,?,?,?);', (topic,
                     entry,
                     entryData[0],
                     self.characterID,
                     entryData[1]))

        self.journal = journal
        from journalWnd import JOURNALWND
        JOURNALWND.setJournal(journal)

    def addJournalEntry(self, topic, entry, text):
        cursor = self.cursor
        existingTopic = self.journal.get(topic)
        if existingTopic:
            existingEntry = existingTopic[0].get(entry)
            if existingEntry:
                if existingEntry[0] == text:
                    if not existingEntry[1]:
                        return (False, self.journal)
                else:
                    existingEntry[0] = text
                existingEntry[1] = False
                existingTopic[1] = False
                cursor.execute('UPDATE journal_entry SET text=?, hidden=? WHERE topic=? AND entry=? AND character_id=?;', (text,
                 False,
                 topic,
                 entry,
                 self.characterID))
            else:
                existingTopic[0][entry] = [text, False]
                existingTopic[1] = False
                cursor.execute('INSERT INTO journal_entry (topic,entry,text,character_id) VALUES(?,?,?,?);', (topic,
                 entry,
                 text,
                 self.characterID))
        else:
            self.journal[topic] = [{entry: [text, False]}, False]
            cursor.execute('INSERT INTO journal_entry (topic,entry,text,character_id) VALUES(?,?,?,?);', (topic,
             entry,
             text,
             self.characterID))
        return (True, self.journal)

    def hideJournalTopic(self, topic, hide = True):
        cursor = self.cursor
        existingTopic = self.journal.get(topic)
        if not existingTopic or existingTopic[1] == hide:
            return (False, self.journal)
        existingTopic[1] = hide
        cursor.execute('UPDATE journal_entry SET hidden=? WHERE topic=? AND character_id=?;', (hide, topic, self.characterID))
        for entry, entryData in existingTopic[0].iteritems():
            entryData[1] = hide

        return (True, self.journal)

    def hideJournalEntry(self, topic, entry, hide = True):
        cursor = self.cursor
        existingTopic = self.journal.get(topic)
        if not existingTopic or hide == True and existingTopic[1] == True:
            return (False, self.journal)
        existingEntry = existingTopic[0].get(entry)
        if not existingEntry or existingEntry[1] == hide:
            return (False, self.journal)
        existingEntry[1] = hide
        cursor.execute('UPDATE journal_entry SET hidden=? WHERE topic=? AND entry=? AND character_id=?;', (hide,
         topic,
         entry,
         self.characterID))
        existingTopic[1] = True
        for entry, entryData in existingTopic[0].iteritems():
            if entryData[1] == False:
                existingTopic[1] = False
                break

        return (True, self.journal)

    def clearJournalTopic(self, topic):
        cursor = self.cursor
        existingTopic = self.journal.get(topic)
        if not existingTopic:
            return (False, self.journal)
        cursor.execute('DELETE FROM journal_entry WHERE topic=? AND character_id=?;', (topic, self.characterID))
        del self.journal[topic]
        return (True, self.journal)

    def clearJournalEntry(self, topic, entry):
        cursor = self.cursor
        existingTopic = self.journal.get(topic)
        if not existingTopic:
            return (False, self.journal)
        existingEntry = existingTopic[0].get(entry)
        if not existingEntry:
            return (False, self.journal)
        cursor.execute('DELETE FROM journal_entry WHERE topic=? AND entry=? AND character_id=?;', (topic, entry, self.characterID))
        del existingTopic[0][entry]
        if len(existingTopic[0]) == 0:
            del self.journal[topic]
        return (True, self.journal)

    def loadMacros(self):
        from macro import Macro, MacroLine, MACROMASTER
        cursor = self.cursor
        self.macroCollection = dict()
        wdirname = md5(self.worldname).hexdigest()
        single = int(TGEGetGlobal('$Py::ISSINGLEPLAYER'))
        if single:
            gdirname = 'single'
        else:
            gdirname = 'multiplayer'
        dirname = '%s/data/settings/%s/%s' % (GAMEROOT, gdirname, wdirname)
        storeCharacterSettings = False
        for charIndex, characterID in self.characters.iteritems():
            charInfo = self.charInfos[charIndex]
            filename = '%s/%s_macros.dat' % (dirname, charInfo.NAME)
            if os.path.exists(filename):
                from cPickle import load as pickleLoad
                try:
                    f = file(filename, 'rb')
                    macroStore = pickleLoad(f)
                    f.close()
                    self.charInfos[charIndex].clientSettings.update(macroStore['CLIENTSETTINGS'])
                    storeCharacterSettings = True
                    del macroStore['CLIENTSETTINGS']
                    for macroIndex, macroData in macroStore.iteritems():
                        page = macroIndex / 10
                        slot = macroIndex % 10
                        name = ''
                        hotkey = str((slot + 1) % 10)
                        icon = ''
                        description = ''
                        macroLines = list()
                        for attr, value in macroData.iteritems():
                            if attr == 'hotKey':
                                hotkey = value
                            elif attr == 'defaultCommand':
                                if value:
                                    defaultCommand = GetDefaultCommand(value.name)
                                    name = defaultCommand.name
                                    icon = defaultCommand.icon
                                    if icon and not icon.startswith('SPELLICON_'):
                                        icon = 'icons/%s' % icon
                                    description = defaultCommand.tooltip
                                    macroLines.append((defaultCommand.command, 0))
                            elif attr == 'skill':
                                if value:
                                    skillInfo = GetSkillInfo(value)
                                    name = skillInfo.name
                                    icon = skillInfo.icon
                                    if icon and not icon.startswith('SPELLICON_'):
                                        icon = 'icons/%s' % icon
                                    description = name
                                    macroLines.append(('/skill %s' % skillInfo.name, 0))
                            elif attr == 'spellSlot':
                                if value != None:
                                    spell = charInfo.SPELLS.get(value)
                                    if spell:
                                        spellInfo = spell.SPELLINFO
                                        name = spellInfo.NAME
                                        icon = spellInfo.SPELLBOOKPIC
                                        if icon and not icon.startswith('SPELLICON_'):
                                            icon = 'spellicons/%s' % icon
                                        description = name
                                        macroLines.append(('/cast %s' % spellInfo.BASENAME, 0))
                            elif attr == 'customMacro':
                                if value:
                                    name = value['name']
                                    icon = value['icon']
                                    if icon and not icon.startswith('SPELLICON_'):
                                        icon = 'icons/%s' % icon
                                    description = name
                                    for command, delay in zip(value['lines'].itervalues(), value['delays'].itervalues()):
                                        macroLines.append((command, delay))

                        cursor.execute('INSERT INTO macro (name,page,slot,hotkey,icon,description,character_id) VALUES(?,?,?,?,?,?,?);', (name,
                         page,
                         slot,
                         hotkey,
                         icon,
                         description,
                         characterID))
                        macroID = cursor.execute('SELECT id FROM macro WHERE character_id=? AND page=? AND slot=? LIMIT 1;', (characterID, page, slot)).fetchone()[0]
                        for lineIndex, macroLine in enumerate(macroLines):
                            cursor.execute('INSERT INTO macro_line (line_index,command,delay_after,macro_id) VALUES(?,?,?,?);', (lineIndex,
                             macroLine[0].lstrip().rstrip(),
                             macroLine[1],
                             macroID))

                    del macroStore
                except:
                    traceback.print_exc()

                os.remove(filename)
            characterMacros = dict()
            characterMacroData = cursor.execute('SELECT * FROM macro WHERE character_id=?;', (characterID,)).fetchall()
            for macroData in characterMacroData:
                newMacro = Macro(charIndex, macroData[2], macroData[3])
                newMacro.name = macroData[1]
                newMacro.hotkey = macroData[4]
                newMacro.icon = macroData[5]
                newMacro.description = macroData[6]
                newMacro.waitAll = macroData[7]
                newMacro.manualDelay = macroData[8]
                macroLines = cursor.execute('SELECT line_index,command,mandatory,delay_after FROM macro_line WHERE macro_id=?;', (macroData[0],)).fetchall()
                for lineIndex, command, mandatory, delayAfter in macroLines:
                    newLine = MacroLine(command, mandatory, delayAfter)
                    newMacro.insertMacroLine(lineIndex, newLine)

                if characterMacros.has_key((macroData[2], macroData[3])):
                    oldMacroID = cursor.execute('SELECT id FROM macro WHERE character_id=? AND page=? AND slot=? LIMIT 1;', (characterID, macroData[2], macroData[3])).fetchone()[0]
                    cursor.execute('DELETE FROM macro_line WHERE macro_id=?;', (oldMacroID,))
                    cursor.execute('DELETE FROM macro WHERE id=?;', (oldMacroID,))
                    if oldMacroID == macroData[0]:
                        continue
                characterMacros[macroData[2], macroData[3]] = newMacro

            if len(characterMacros) == 0:
                characterMacros = CreateDefaultMacros(charIndex, charInfo.PCLASS)
                for macro in characterMacros.itervalues():
                    cursor.execute('INSERT INTO macro (name,page,slot,hotkey,icon,description,character_id) VALUES(?,?,?,?,?,?,?);', (macro.name,
                     macro.page,
                     macro.slot,
                     macro.hotkey,
                     macro.icon,
                     macro.description,
                     characterID))
                    macroID = cursor.execute('SELECT id FROM macro WHERE character_id=? AND page=? AND slot=? LIMIT 1;', (characterID, macro.page, macro.slot)).fetchone()[0]
                    for lineIndex, macroLine in macro.macroLines.iteritems():
                        cursor.execute('INSERT INTO macro_line (line_index,command,delay_after,macro_id) VALUES(?,?,?,?);', (lineIndex,
                         macroLine.command,
                         macroLine.delayAfter,
                         macroID))

            self.macroCollection[charIndex] = characterMacros

        if storeCharacterSettings:
            self.storeCharacterSettings()
        MACROMASTER.installMacroCollection(self.macroCollection)
        return

    def saveMacro(self, macro, prevMacro = False):
        cursor = self.cursor
        characterID = self.characters[macro.charIndex]
        if prevMacro:
            oldMacroID = cursor.execute('SELECT id FROM macro WHERE character_id=? AND page=? AND slot=? LIMIT 1;', (characterID, macro.page, macro.slot)).fetchone()[0]
            cursor.execute('DELETE FROM macro_line WHERE macro_id=?;', (oldMacroID,))
            cursor.execute('DELETE FROM macro WHERE id=?;', (oldMacroID,))
        cursor.execute('INSERT INTO macro VALUES(?,?,?,?,?,?,?,?,?,?);', (None,
         macro.name,
         macro.page,
         macro.slot,
         macro.hotkey,
         macro.icon,
         macro.description,
         macro.waitAll,
         macro.manualDelay,
         characterID))
        macroID = cursor.execute('SELECT id FROM macro WHERE character_id=? AND page=? AND slot=? LIMIT 1;', (characterID, macro.page, macro.slot)).fetchone()[0]
        for lineIndex, macroLine in macro.macroLines.iteritems():
            cursor.execute('INSERT INTO macro_line VALUES(?,?,?,?,?,?);', (None,
             lineIndex,
             macroLine.command,
             macroLine.mandatory,
             macroLine.delayAfter,
             macroID))

        return

    def deleteMacro(self, charIndex, page, slot):
        cursor = self.cursor
        characterID = self.characters[charIndex]
        oldMacroID = cursor.execute('SELECT id FROM macro WHERE character_id=? AND page=? AND slot=? LIMIT 1;', (characterID, page, slot)).fetchone()
        if oldMacroID:
            oldMacroID = oldMacroID[0]
            cursor.execute('DELETE FROM macro_line WHERE macro_id=?;', (oldMacroID,))
            cursor.execute('DELETE FROM macro WHERE id=?;', (oldMacroID,))

    def toggleExtendedMacros(self, args):
        enabled = int(args[1])
        if self.useExtendedMacros != enabled:
            self.useExtendedMacros = enabled
            from macro import MACROMASTER
            MACROMASTER.extendedMacros = enabled
            self.cursor.execute('UPDATE misc SET extended_macros=?;', (enabled,))


if not IN_PATCHING:
    PLAYERSETTINGS = PlayerSettings()
    TGEExport(PLAYERSETTINGS.checkWindowPositions, 'Py', 'CheckWindowPositions', 'desc', 1, 1)
    TGEExport(PLAYERSETTINGS.toggleExtendedMacros, 'Py', 'ToggleExtendedMacros', 'desc', 2, 2)