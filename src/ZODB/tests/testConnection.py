##############################################################################
#
# Copyright (c) 2001, 2002 Zope Corporation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.0 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Unit tests for the Connection class.
"""

import unittest
from persistent import Persistent

__metaclass__ = type

class ConnectionDotAdd(unittest.TestCase):

    def setUp(self):
        from ZODB.Connection import Connection
        self.datamgr = Connection()
        self.db = StubDatabase()
        self.datamgr._setDB(self.db)
        self.transaction = StubTransaction()

    def check_add(self):
        from ZODB.POSException import InvalidObjectReference
        obj = StubObject()
        self.assert_(obj._p_oid is None)
        self.assert_(obj._p_jar is None)
        self.datamgr.add(obj)
        self.assert_(obj._p_oid is not None)
        self.assert_(obj._p_jar is self.datamgr)
        self.assert_(self.datamgr[obj._p_oid] is obj)

        # Only first-class persistent objects may be added.
        self.assertRaises(TypeError, self.datamgr.add, object())

        # Adding to the same connection does not fail. Object keeps the
        # same oid.
        oid = obj._p_oid
        self.datamgr.add(obj)
        self.assertEqual(obj._p_oid, oid)

        # Cannot add an object from a diffrerent connection.
        obj2 = StubObject()
        obj2._p_jar = object()
        self.assertRaises(InvalidObjectReference, self.datamgr.add, obj2)

    def checkResetOnAbort(self):
        # Check that _p_oid and _p_jar are reset when a transaction is
        # aborted.
        obj = StubObject()
        self.datamgr.add(obj)
        oid = obj._p_oid
        self.datamgr.abort(obj, self.transaction)
        self.assert_(obj._p_oid is None)
        self.assert_(obj._p_jar is None)
        self.assertRaises(KeyError, self.datamgr.__getitem__, oid)

    def checkResetOnTpcAbort(self):
        obj = StubObject()
        self.datamgr.add(obj)
        oid = obj._p_oid

        # This case simulates when an error occurred committing some other
        # object, so tpc_abort is called, clearing everything.
        self.datamgr.tpc_begin(self.transaction)
        # Let's pretend something bad happens here.
        self.datamgr.tpc_abort(self.transaction)
        self.assert_(obj._p_oid is None)
        self.assert_(obj._p_jar is None)
        self.assertRaises(KeyError, self.datamgr.__getitem__, oid)

    def checkTcpAbortAfterCommit(self):
        obj = StubObject()
        self.datamgr.add(obj)
        oid = obj._p_oid

        self.datamgr.tpc_begin(self.transaction)
        self.datamgr.commit(obj, self.transaction)
        # Let's pretend something bad happened here.
        self.datamgr.tpc_abort(self.transaction)
        self.assert_(obj._p_oid is None)
        self.assert_(obj._p_jar is None)
        self.assertRaises(KeyError, self.datamgr.__getitem__, oid)
        self.assertEquals(self.db._storage._stored, [oid])

    def checkCommit(self):
        obj = StubObject()
        self.datamgr.add(obj)
        oid = obj._p_oid

        self.datamgr.tpc_begin(self.transaction)
        self.datamgr.commit(obj, self.transaction)
        self.datamgr.tpc_finish(self.transaction)
        self.assert_(obj._p_oid is oid)
        self.assert_(obj._p_jar is self.datamgr)

        # This next assert_ is covered by an assert in tpc_finish.
        ##self.assert_(not self.datamgr._added)

        self.assertEquals(self.db._storage._stored, [oid])
        self.assertEquals(self.db._storage._finished, [oid])

    def checkModifyOnGetstate(self):
        subobj = StubObject()
        obj = ModifyOnGetStateObject(subobj)
        
        self.datamgr.tpc_begin(self.transaction)
        self.datamgr.commit(obj, self.transaction)
        self.datamgr.tpc_finish(self.transaction)
        storage = self.db._storage
        self.assert_(obj._p_oid in storage._stored, "object was not stored")
        self.assert_(subobj._p_oid in storage._stored,
                "subobject was not stored")
        self.assert_(self.datamgr._added_during_commit is None)

    def checkErrorDuringCommit(self):
        # We need to check that _added_during_commit still gets set to None
        # when there is an error during commit()/
        obj = ErrorOnGetstateObject()
        
        self.datamgr.tpc_begin(self.transaction)
        self.assertRaises(ErrorOnGetstateException,
                self.datamgr.commit, obj, self.transaction)
        self.assert_(self.datamgr._added_during_commit is None)

    def checkUnusedAddWorks(self):
        # When an object is added, but not committed, it shouldn't be stored,
        # but also it should be an error.
        obj = StubObject()
        self.datamgr.add(obj)
        self.datamgr.tpc_begin(self.transaction)
        self.datamgr.tpc_finish(self.transaction)
        self.assert_(obj._p_oid not in self.datamgr._storage._stored)

# ---- stubs

class StubObject(Persistent):
    pass


class StubTransaction:
    pass

class ErrorOnGetstateException(Exception):
    pass
    
class ErrorOnGetstateObject(Persistent):

    def __getstate__(self):
        raise ErrorOnGetstateException

class ModifyOnGetStateObject(Persistent):

    def __init__(self, p):
        self._v_p = p

    def __getstate__(self):
        self._p_jar.add(self._v_p)
        self.p = self._v_p
        return Persistent.__getstate__(self)


class StubStorage:
    """Very simple in-memory storage that does *just* enough to support tests.

    Only one concurrent transaction is supported.
    Voting is not supported.
    Versions are not supported.

    Inspect self._stored and self._finished to see how the storage has been
    used during a unit test. Whenever an object is stored in the store()
    method, its oid is appended to self._stored. When a transaction is
    finished, the oids that have been stored during the transaction are
    appended to self._finished.
    """

    sortKey = 'StubStorage sortKey'

    # internal
    _oid = 1
    _transaction = None

    def __init__(self):
        # internal
        self._stored = []
        self._finished = []
        self._data = {}
        self._transdata = {}
        self._transstored = []

    def new_oid(self):
        oid = str(self._oid)
        self._oid += 1
        return oid

    def tpc_begin(self, transaction):
        if transaction is None:
            raise TypeError('transaction may not be None')
        elif self._transaction is None:
            self._transaction = transaction
        elif self._transaction != transaction:
            raise RuntimeError(
                'StubStorage uses only one transaction at a time')

    def tpc_abort(self, transaction):
        if transaction is None:
            raise TypeError('transaction may not be None')
        elif self._transaction != transaction:
            raise RuntimeError(
                'StubStorage uses only one transaction at a time')
        del self._transaction
        self._transdata.clear()

    def tpc_finish(self, transaction, callback):
        if transaction is None:
            raise TypeError('transaction may not be None')
        elif self._transaction != transaction:
            raise RuntimeError(
                'StubStorage uses only one transaction at a time')
        self._finished.extend(self._transstored)
        self._data.update(self._transdata)
        callback(transaction)
        del self._transaction
        self._transdata.clear()
        self._transstored = []

    def load(self, oid, version):
        if version != '':
            raise TypeError('StubStorage does not support versions.')
        return self._data[oid]

    def store(self, oid, serial, p, version, transaction):
        if version != '':
            raise TypeError('StubStorage does not support versions.')
        if transaction is None:
            raise TypeError('transaction may not be None')
        elif self._transaction != transaction:
            raise RuntimeError(
                'StubStorage uses only one transaction at a time')
        self._stored.append(oid)
        self._transstored.append(oid)
        self._transdata[oid] = (p, serial)
        # Explicitly returing None, as we're not pretending to be a ZEO
        # storage
        return None


class StubDatabase:

    def __init__(self):
        self._storage = StubStorage()

    _classFactory = None

    def invalidate(self, transaction, dict_with_oid_keys, connection):
        pass


def test_suite():
    s = unittest.makeSuite(ConnectionDotAdd, 'check')
    return s
