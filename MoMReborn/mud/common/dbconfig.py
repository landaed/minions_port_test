# Embedded file name: mud\common\dbconfig.pyo
from sqlobject import *
from sqlobject.sqlite.sqliteconnection import SQLiteConnection
DBCONNECTION = None
HUB = dbconnection.ConnectionHub()
HUB.processConnection = None

def GetDBURI():
    global DBCONNECTION
    uri = DBCONNECTION
    print 'GetDBURI %s' % uri
    return uri


def GetDBConnection():
    global HUB
    return HUB


def SetDBConnection(uri, finalize = False, autoCommit = 1, debugOutput = 0):
    global DBCONNECTION
    from persistent import Persistent
    DBCONNECTION = uri
    if not finalize:
        Persistent._connection = HUB
        if not uri:
            dbconnection.TheURIOpener.cachedURIs = {}
            if HUB.processConnection:
                try:
                    HUB.processConnection.close()
                    HUB.processConnection._conn.close()
                    HUB.processConnection._conn = None
                except:
                    pass

            HUB.processConnection = None
            return
    print 'SetDBConnection %s' % uri
    HUB.processConnection = SQLiteConnection(uri, driver='pysqlite2', check_same_thread=1, autoCommit=autoCommit, debugOutput=debugOutput)
    return