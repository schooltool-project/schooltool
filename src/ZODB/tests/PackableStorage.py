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
"""Run some tests relevant for storages that support pack()."""

try:
    import cPickle
    pickle = cPickle
    #import cPickle as pickle
except ImportError:
    import pickle

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

import threading
import time

from ZODB import DB
from persistent import Persistent
from ZODB.referencesf import referencesf
from ZODB.tests.MinPO import MinPO
from ZODB.tests.StorageTestBase import snooze
from ZODB.POSException import ConflictError

ZERO = '\0'*8


# This class is for the root object.  It must not contain a getoid() method
# (really, attribute).  The persistent pickling machinery -- in the dumps()
# function below -- will pickle Root objects as normal, but any attributes
# which reference persistent Object instances will get pickled as persistent
# ids, not as the object's state.  This makes the referencesf stuff work,
# because it pickle sniffs for persistent ids (so we have to get those
# persistent ids into the root object's pickle).
class Root:
    pass


# This is the persistent Object class.  Because it has a getoid() method, the
# persistent pickling machinery -- in the dumps() function below -- will
# pickle the oid string instead of the object's actual state.  Yee haw, this
# stuff is deep. ;)
class Object:
    def __init__(self, oid):
        self._oid = oid

    def getoid(self):
        return self._oid


class C(Persistent):
    pass

# Here's where all the magic occurs.  Sadly, the pickle module is a bit
# underdocumented, but here's what happens: by setting the persistent_id
# attribute to getpersid() on the pickler, that function gets called for every
# object being pickled.  By returning None when the object has no getoid
# attribute, it signals pickle to serialize the object as normal.  That's how
# the Root instance gets pickled correctly.  But, if the object has a getoid
# attribute, then by returning that method's value, we tell pickle to
# serialize the persistent id of the object instead of the object's state.
# That sets the pickle up for proper sniffing by the referencesf machinery.
# Fun, huh?
def dumps(obj):
    def getpersid(obj):
        if hasattr(obj, 'getoid'):
            return obj.getoid()
        return None
    s = StringIO()
    p = pickle.Pickler(s)
    p.persistent_id = getpersid
    p.dump(obj)
    return s.getvalue()



class PackableStorageBase:
    # We keep a cache of object ids to instances so that the unpickler can
    # easily return any persistent object.
    _cache = {}

    def _newobj(self):
        # This is a convenience method to create a new persistent Object
        # instance.  It asks the storage for a new object id, creates the
        # instance with the given oid, populates the cache and returns the
        # object.
        oid = self._storage.new_oid()
        obj = Object(oid)
        self._cache[obj.getoid()] = obj
        return obj

    def _makeloader(self):
        # This is the other side of the persistent pickling magic.  We need a
        # custom unpickler to mirror our custom pickler above.  By setting the
        # persistent_load function of the unpickler to self._cache.get(),
        # whenever a persistent id is unpickled, it will actually return the
        # Object instance out of the cache.  As far as returning a function
        # with an argument bound to an instance attribute method, we do it
        # this way because it makes the code in the tests more succinct.
        #
        # BUT!  Be careful in your use of loads() vs. pickle.loads().  loads()
        # should only be used on the Root object's pickle since it's the only
        # special one.  All the Object instances should use pickle.loads().
        def loads(str, persfunc=self._cache.get):
            fp = StringIO(str)
            u = pickle.Unpickler(fp)
            u.persistent_load = persfunc
            return u.load()
        return loads

    def _initroot(self):
        try:
            self._storage.load(ZERO, '')
        except KeyError:
            from persistent import mapping
            from ZODB.Transaction import Transaction
            file = StringIO()
            p = cPickle.Pickler(file, 1)
            p.dump((mapping.PersistentMapping, None))
            p.dump({'_container': {}})
            t=Transaction()
            t.description='initial database creation'
            self._storage.tpc_begin(t)
            self._storage.store(ZERO, None, file.getvalue(), '', t)
            self._storage.tpc_vote(t)
            self._storage.tpc_finish(t)

class PackableStorage(PackableStorageBase):

    def checkPackEmptyStorage(self):
        self._storage.pack(time.time(), referencesf)

    def checkPackTomorrow(self):
        self._initroot()
        self._storage.pack(time.time() + 10000, referencesf)

    def checkPackYesterday(self):
        self._initroot()
        self._storage.pack(time.time() - 10000, referencesf)

    def _PackWhileWriting(self, pack_now=0):
        # A storage should allow some reading and writing during
        # a pack.  This test attempts to exercise locking code
        # in the storage to test that it is safe.  It generates
        # a lot of revisions, so that pack takes a long time.

        db = DB(self._storage)
        conn = db.open()
        root = conn.root()

        for i in range(10):
            root[i] = MinPO(i)
        get_transaction().commit()

        snooze()
        packt = time.time()

        choices = range(10)
        for dummy in choices:
            for i in choices:
                root[i].value = MinPO(i)
                get_transaction().commit()

        threads = [ClientThread(db, choices) for i in range(4)]
        for t in threads:
            t.start()

        if pack_now:
            db.pack(time.time())
        else:
            db.pack(packt)

        for t in threads:
            t.join(30)
        for t in threads:
            t.join(1)
            self.assert_(not t.isAlive())

        # Iterate over the storage to make sure it's sane, but not every
        # storage supports iterators.
        if not hasattr(self._storage, "iterator"):
            return

        iter = self._storage.iterator()
        for txn in iter:
            for data in txn:
                pass
        iter.close()

    def checkPackWhileWriting(self):
        self._PackWhileWriting(pack_now=0)

    def checkPackNowWhileWriting(self):
        self._PackWhileWriting(pack_now=1)

class PackableUndoStorage(PackableStorageBase):

    def checkPackAllRevisions(self):
        self._initroot()
        eq = self.assertEqual
        raises = self.assertRaises
        # Create a `persistent' object
        obj = self._newobj()
        oid = obj.getoid()
        obj.value = 1
        # Commit three different revisions
        revid1 = self._dostoreNP(oid, data=pickle.dumps(obj))
        obj.value = 2
        revid2 = self._dostoreNP(oid, revid=revid1, data=pickle.dumps(obj))
        obj.value = 3
        revid3 = self._dostoreNP(oid, revid=revid2, data=pickle.dumps(obj))
        # Now make sure all three revisions can be extracted
        data = self._storage.loadSerial(oid, revid1)
        pobj = pickle.loads(data)
        eq(pobj.getoid(), oid)
        eq(pobj.value, 1)
        data = self._storage.loadSerial(oid, revid2)
        pobj = pickle.loads(data)
        eq(pobj.getoid(), oid)
        eq(pobj.value, 2)
        data = self._storage.loadSerial(oid, revid3)
        pobj = pickle.loads(data)
        eq(pobj.getoid(), oid)
        eq(pobj.value, 3)
        # Now pack all transactions; need to sleep a second to make
        # sure that the pack time is greater than the last commit time.
        now = packtime = time.time()
        while packtime <= now:
            packtime = time.time()
        self._storage.pack(packtime, referencesf)
        # All revisions of the object should be gone, since there is no
        # reference from the root object to this object.
        raises(KeyError, self._storage.loadSerial, oid, revid1)
        raises(KeyError, self._storage.loadSerial, oid, revid2)
        raises(KeyError, self._storage.loadSerial, oid, revid3)

    def checkPackJustOldRevisions(self):
        eq = self.assertEqual
        raises = self.assertRaises
        loads = self._makeloader()
        # Create a root object.  This can't be an instance of Object,
        # otherwise the pickling machinery will serialize it as a persistent
        # id and not as an object that contains references (persistent ids) to
        # other objects.
        root = Root()
        # Create a persistent object, with some initial state
        obj = self._newobj()
        oid = obj.getoid()
        # Link the root object to the persistent object, in order to keep the
        # persistent object alive.  Store the root object.
        root.obj = obj
        root.value = 0
        revid0 = self._dostoreNP(ZERO, data=dumps(root))
        # Make sure the root can be retrieved
        data, revid = self._storage.load(ZERO, '')
        eq(revid, revid0)
        eq(loads(data).value, 0)
        # Commit three different revisions of the other object
        obj.value = 1
        revid1 = self._dostoreNP(oid, data=pickle.dumps(obj))
        obj.value = 2
        revid2 = self._dostoreNP(oid, revid=revid1, data=pickle.dumps(obj))
        obj.value = 3
        revid3 = self._dostoreNP(oid, revid=revid2, data=pickle.dumps(obj))
        # Now make sure all three revisions can be extracted
        data = self._storage.loadSerial(oid, revid1)
        pobj = pickle.loads(data)
        eq(pobj.getoid(), oid)
        eq(pobj.value, 1)
        data = self._storage.loadSerial(oid, revid2)
        pobj = pickle.loads(data)
        eq(pobj.getoid(), oid)
        eq(pobj.value, 2)
        data = self._storage.loadSerial(oid, revid3)
        pobj = pickle.loads(data)
        eq(pobj.getoid(), oid)
        eq(pobj.value, 3)
        # Now pack just revisions 1 and 2.  The object's current revision
        # should stay alive because it's pointed to by the root.
        now = packtime = time.time()
        while packtime <= now:
            packtime = time.time()
        self._storage.pack(packtime, referencesf)
        # Make sure the revisions are gone, but that object zero and revision
        # 3 are still there and correct
        data, revid = self._storage.load(ZERO, '')
        eq(revid, revid0)
        eq(loads(data).value, 0)
        raises(KeyError, self._storage.loadSerial, oid, revid1)
        raises(KeyError, self._storage.loadSerial, oid, revid2)
        data = self._storage.loadSerial(oid, revid3)
        pobj = pickle.loads(data)
        eq(pobj.getoid(), oid)
        eq(pobj.value, 3)
        data, revid = self._storage.load(oid, '')
        eq(revid, revid3)
        pobj = pickle.loads(data)
        eq(pobj.getoid(), oid)
        eq(pobj.value, 3)

    def checkPackOnlyOneObject(self):
        eq = self.assertEqual
        raises = self.assertRaises
        loads = self._makeloader()
        # Create a root object.  This can't be an instance of Object,
        # otherwise the pickling machinery will serialize it as a persistent
        # id and not as an object that contains references (persistent ids) to
        # other objects.
        root = Root()
        # Create a persistent object, with some initial state
        obj1 = self._newobj()
        oid1 = obj1.getoid()
        # Create another persistent object, with some initial state.  Make
        # sure it's oid is greater than the first object's oid.
        obj2 = self._newobj()
        oid2 = obj2.getoid()
        self.failUnless(oid2 > oid1)
        # Link the root object to the persistent objects, in order to keep
        # them alive.  Store the root object.
        root.obj1 = obj1
        root.obj2 = obj2
        root.value = 0
        revid0 = self._dostoreNP(ZERO, data=dumps(root))
        # Make sure the root can be retrieved
        data, revid = self._storage.load(ZERO, '')
        eq(revid, revid0)
        eq(loads(data).value, 0)
        # Commit three different revisions of the first object
        obj1.value = 1
        revid1 = self._dostoreNP(oid1, data=pickle.dumps(obj1))
        obj1.value = 2
        revid2 = self._dostoreNP(oid1, revid=revid1, data=pickle.dumps(obj1))
        obj1.value = 3
        revid3 = self._dostoreNP(oid1, revid=revid2, data=pickle.dumps(obj1))
        # Now make sure all three revisions can be extracted
        data = self._storage.loadSerial(oid1, revid1)
        pobj = pickle.loads(data)
        eq(pobj.getoid(), oid1)
        eq(pobj.value, 1)
        data = self._storage.loadSerial(oid1, revid2)
        pobj = pickle.loads(data)
        eq(pobj.getoid(), oid1)
        eq(pobj.value, 2)
        data = self._storage.loadSerial(oid1, revid3)
        pobj = pickle.loads(data)
        eq(pobj.getoid(), oid1)
        eq(pobj.value, 3)
        # Now commit a revision of the second object
        obj2.value = 11
        revid4 = self._dostoreNP(oid2, data=pickle.dumps(obj2))
        # And make sure the revision can be extracted
        data = self._storage.loadSerial(oid2, revid4)
        pobj = pickle.loads(data)
        eq(pobj.getoid(), oid2)
        eq(pobj.value, 11)
        # Now pack just revisions 1 and 2 of object1.  Object1's current
        # revision should stay alive because it's pointed to by the root, as
        # should Object2's current revision.
        now = packtime = time.time()
        while packtime <= now:
            packtime = time.time()
        self._storage.pack(packtime, referencesf)
        # Make sure the revisions are gone, but that object zero, object2, and
        # revision 3 of object1 are still there and correct.
        data, revid = self._storage.load(ZERO, '')
        eq(revid, revid0)
        eq(loads(data).value, 0)
        raises(KeyError, self._storage.loadSerial, oid1, revid1)
        raises(KeyError, self._storage.loadSerial, oid1, revid2)
        data = self._storage.loadSerial(oid1, revid3)
        pobj = pickle.loads(data)
        eq(pobj.getoid(), oid1)
        eq(pobj.value, 3)
        data, revid = self._storage.load(oid1, '')
        eq(revid, revid3)
        pobj = pickle.loads(data)
        eq(pobj.getoid(), oid1)
        eq(pobj.value, 3)
        data, revid = self._storage.load(oid2, '')
        eq(revid, revid4)
        eq(loads(data).value, 11)
        data = self._storage.loadSerial(oid2, revid4)
        pobj = pickle.loads(data)
        eq(pobj.getoid(), oid2)
        eq(pobj.value, 11)

    def checkPackUnlinkedFromRoot(self):
        eq = self.assertEqual
        db = DB(self._storage)
        conn = db.open()
        root = conn.root()

        txn = get_transaction()
        txn.note('root')
        txn.commit()

        now = packtime = time.time()
        while packtime <= now:
            packtime = time.time()

        obj = C()
        obj.value = 7

        root['obj'] = obj
        txn = get_transaction()
        txn.note('root -> o1')
        txn.commit()

        del root['obj']
        txn = get_transaction()
        txn.note('root -x-> o1')
        txn.commit()

        self._storage.pack(packtime, referencesf)

        log = self._storage.undoLog()
        tid = log[0]['id']
        db.undo(tid)
        txn = get_transaction()
        txn.note('undo root -x-> o1')
        txn.commit()

        conn.sync()

        eq(root['obj'].value, 7)

    def checkPackUndoLog(self):
        self._initroot()
        # Create a `persistent' object
        obj = self._newobj()
        oid = obj.getoid()
        obj.value = 1
        # Commit two different revisions
        revid1 = self._dostoreNP(oid, data=pickle.dumps(obj))
        obj.value = 2
        snooze()
        packtime = time.time()
        snooze()
        self._dostoreNP(oid, revid=revid1, data=pickle.dumps(obj))
        # Now pack the first transaction
        self.assertEqual(3, len(self._storage.undoLog()))
        self._storage.pack(packtime, referencesf)
        # The undo log contains only the most resent transaction
        self.assertEqual(1,len(self._storage.undoLog()))

    def dont_checkPackUndoLogUndoable(self):
        # A disabled test. I wanted to test that the content of the
        # undo log was consistent, but every storage appears to
        # include something slightly different. If the result of this
        # method is only used to fill a GUI then this difference
        # doesnt matter.  Perhaps re-enable this test once we agree
        # what should be asserted.

        self._initroot()
        # Create two `persistent' object
        obj1 = self._newobj()
        oid1 = obj1.getoid()
        obj1.value = 1
        obj2 = self._newobj()
        oid2 = obj2.getoid()
        obj2.value = 2

        # Commit the first revision of each of them
        revid11 = self._dostoreNP(oid1, data=pickle.dumps(obj1),
                                  description="1-1")
        revid22 = self._dostoreNP(oid2, data=pickle.dumps(obj2),
                                  description="2-2")

        # remember the time. everything above here will be packed away
        snooze()
        packtime = time.time()
        snooze()
        # Commit two revisions of the first object
        obj1.value = 3
        revid13 = self._dostoreNP(oid1, revid=revid11,
                                  data=pickle.dumps(obj1), description="1-3")
        obj1.value = 4
        self._dostoreNP(oid1, revid=revid13,
                        data=pickle.dumps(obj1), description="1-4")
        # Commit one revision of the second object
        obj2.value = 5
        self._dostoreNP(oid2, revid=revid22,
                        data=pickle.dumps(obj2), description="2-5")
        # Now pack
        self.assertEqual(6,len(self._storage.undoLog()))
        print '\ninitial undoLog was'
        for r in self._storage.undoLog(): print r
        self._storage.pack(packtime, referencesf)
        # The undo log contains only two undoable transaction.
        print '\nafter packing undoLog was'
        for r in self._storage.undoLog(): print r
        # what can we assert about that?


class ClientThread(threading.Thread):

    def __init__(self, db, choices):
        threading.Thread.__init__(self)
        self.root = db.open().root()
        self.choices = choices

    def run(self):
        from random import choice

        for j in range(50):
            try:
                self.root[choice(self.choices)].value = MinPO(j)
                get_transaction().commit()
            except ConflictError:
                get_transaction().abort()
