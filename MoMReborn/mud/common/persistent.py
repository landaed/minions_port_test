# Embedded file name: mud\common\persistent.pyo
from twisted.spread import pb
from sqlobject import *
import weakref
from weakref import WeakValueDictionary
from dbconfig import GetDBConnection
from datetime import datetime
import traceback

class Persistent(SQLObject):
    _connection = GetDBConnection()

    def _init(self, *args, **kw):
        SQLObject._init(self, *args, **kw)

    def getStateToCacheAndObserveFor(self, perspective, observer):
        if observer in self.observers:
            traceback.print_stack()
            print 'AssertionError: observer already hooked up!'
            return
        else:
            tp = None
            for tperm in perspective.role.tablePermissions:
                if tperm.name == self.__class__.__name__:
                    tp = tperm
                    break

            if not tp:
                traceback.print_stack()
                print 'AssertionError: class permission not found!'
                return
            state = {}
            for cp in tp.columnPermissions:
                if cp.read:
                    v = getattr(self, cp.name)
                    if isinstance(v, datetime):
                        v = str(v)
                    if isinstance(v, list):
                        myjoin = []
                        for p in v:
                            myjoin.append(p.id)

                        tname = None
                        for j in self._joins:
                            if j.joinMethodName == cp.name:
                                tname = j.kw['otherClass']
                                break

                        if not tname:
                            traceback.print_stack()
                            print 'AssertionError: no class name found!'
                            return
                        v = (tname, myjoin)
                    if isinstance(v, Persistent):
                        v = (v.__class__.__name__, v.id)
                    state[cp.name] = v

            state['table'] = self.__class__.__name__
            state['id'] = self.id
            self.observers.append(observer)
            return state

    def stoppedObserving(self, perspective, observer):
        print 'goodbye'
        self.observers.remove(observer)

    def updateChanged(self, changed):
        for k, v in changed.iteritems():
            try:
                setattr(self, k, v)
            except:
                pass

        for o in self.observers:
            d = o.callRemote('updateChanged', changed)
            d.addErrback(lambda e: None)


class PersistentGhost(pb.RemoteCache):

    def __init__(self):
        pass

    def setCopyableState(self, state):
        self.__dict__.update(state)
        if not hasattr(self, 'primaryKey'):
            self.primaryKey = 'id'

    def observe_updateChanged(self, changed):
        self.__dict__.update(changed)

    def observe_destroySelf(self):
        print 'Destroyed!'


pb.setUnjellyableForClass(Persistent, PersistentGhost)