##############################################################################
#
# Copyright (c) 2003 Zope Corporation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.0 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE
#
##############################################################################

from thread import get_ident
import threading
import time

from zodb.btrees.check import check, display
from zodb.btrees.OOBTree import OOBTree
from zodb.db import DB
from zodb.interfaces import ReadConflictError, ConflictError, VersionLockError

from zodb.zeo.tests.basethread import TestThread
from zodb.zeo.tests.connection import CommonSetupTearDown

from transaction import get_transaction

import logging

# The tests here let several threads have a go at one or more database
# instances simultaneously.  Each thread appends a disjoint (from the
# other threads) sequence of increasing integers to an OOBTree, one at
# at time (per thread).  This provokes lots of conflicts, and BTrees
# work hard at conflict resolution too.  An OOBTree is used because
# that flavor has the smallest maximum bucket size, and so splits buckets
# more often than other BTree flavors.
#
# When these tests were first written, they provoked an amazing number
# of obscure timing-related bugs in cache consistency logic, revealed
# by failure of the BTree to pass internal consistency checks at the end,
# and/or by failure of the BTree to contain all the keys the threads
# thought they added (i.e., the keys for which get_transaction().commit()
# did not raise any exception).

class StressThread(TestThread):

    # Append integers startnum, startnum + step, startnum + 2*step, ...
    # to 'tree' until Event stop is set.  If sleep is given, sleep
    # that long after each append.  At the end, instance var .added_keys
    # is a list of the ints the thread believes it added successfully.
    def __init__(self, testcase, db, stop, threadnum, commitdict,
                 startnum, step=2, sleep=None):
        TestThread.__init__(self, testcase)
        self.db = db
        self.stop = stop
        self.threadnum = threadnum
        self.startnum = startnum
        self.step = step
        self.sleep = sleep
        self.added_keys = []
        self.commitdict = commitdict

    def testrun(self):
        cn = self.db.open()
        while not self.stop.isSet():
            try:
                tree = cn.root()["tree"]
                break
            except (ConflictError, KeyError):
                get_transaction().abort()
                cn.sync()
        key = self.startnum
        while not self.stop.isSet():
            try:
                tree[key] = self.threadnum
                get_transaction().note("add key %s" % key)
                get_transaction().commit()
                self.commitdict[self] = 1
                if self.sleep:
                    time.sleep(self.sleep)
            except (ReadConflictError, ConflictError), msg:
                get_transaction().abort()
                # sync() is necessary here to process invalidations
                # if we get a read conflict.  In the read conflict case,
                # no objects were modified so cn never got registered
                # with the transaction.
                cn.sync()
            else:
                self.added_keys.append(key)
            key += self.step
        cn.close()

class LargeUpdatesThread(TestThread):

    # A thread that performs a lot of updates.  It attempts to modify
    # more than 25 objects so that it can test code that runs vote
    # in a separate thread when it modifies more than 25 objects.
    # XXX ZODB4 doesn't actually run vote in a separate thread then.

    def __init__(self, testcase, db, stop, threadnum, commitdict, startnum,
                 step=2, sleep=None):
        TestThread.__init__(self, testcase)
        self.db = db
        self.stop = stop
        self.threadnum = threadnum
        self.startnum = startnum
        self.step = step
        self.sleep = sleep
        self.added_keys = []
        self.commitdict = commitdict

    def testrun(self):
        cn = self.db.open()
        while not self.stop.isSet():
            try:
                tree = cn.root()["tree"]
                break
            except (ConflictError, KeyError):
                # print "%d getting tree abort" % self.threadnum
                get_transaction().abort()
                cn.sync()

        keys_added = {} # set of keys we commit
        tkeys = []
        while not self.stop.isSet():

            # The test picks 50 keys spread across many buckets.
            # self.startnum and self.step ensure that all threads use
            # disjoint key sets, to minimize conflict errors.

            nkeys = len(tkeys)
            if nkeys < 50:
                tkeys = range(self.startnum, 3000, self.step)
                nkeys = len(tkeys)
            step = max(int(nkeys / 50), 1)
            keys = [tkeys[i] for i in range(0, nkeys, step)]
            for key in keys:
                try:
                    tree[key] = self.threadnum
                except (ReadConflictError, ConflictError), msg:
                    # print "%d setting key %s" % (self.threadnum, msg)
                    get_transaction().abort()
                    cn.sync()
                    break
            else:
                # print "%d set #%d" % (self.threadnum, len(keys))
                get_transaction().note("keys %s" % ", ".join(map(str, keys)))
                try:
                    get_transaction().commit()
                    self.commitdict[self] = 1
                    if self.sleep:
                        time.sleep(self.sleep)
                except ConflictError, msg:
                    # print "%d commit %s" % (self.threadnum, msg)
                    get_transaction().abort()
                    cn.sync()
                    continue
                for k in keys:
                    tkeys.remove(k)
                    keys_added[k] = 1
                # sync() is necessary here to process invalidations
                # if we get a read conflict.  In the read conflict case,
                # no objects were modified so cn never got registered
                # with the transaction.
                cn.sync()
        self.added_keys = keys_added.keys()
        cn.close()

class VersionStressThread(TestThread):

    def __init__(self, testcase, db, stop, threadnum, commitdict, startnum,
                 step=2, sleep=None):
        TestThread.__init__(self, testcase)
        self.db = db
        self.stop = stop
        self.threadnum = threadnum
        self.startnum = startnum
        self.step = step
        self.sleep = sleep
        self.added_keys = []
        self.log = logging.getLogger("thread:%s" % get_ident()).info
        self.commitdict = commitdict

    def testrun(self):
        self.log("thread begin")
        commit = 0
        key = self.startnum
        while not self.stop.isSet():
            version = "%s:%s" % (self.threadnum, key)
            commit = not commit
            self.log("attempt to add key=%s version=%s commit=%d" %
                     (key, version, commit))
            if self.oneupdate(version, key, commit):
                self.added_keys.append(key)
                self.commitdict[self] = 1
            key += self.step

    def oneupdate(self, version, key, commit=1):
        # The mess of sleeps below were added to reduce the number
        # of VersionLockErrors, based on empirical observation.
        # It looks like the threads don't switch enough without
        # the sleeps.

        cn = self.db.open(version)
        while not self.stop.isSet():
            try:
                tree = cn.root()["tree"]
                break
            except (ConflictError, KeyError), msg:
                get_transaction().abort()
                cn.sync()
        while not self.stop.isSet():
            try:
                tree[key] = self.threadnum
                get_transaction().note("add key %d" % key)
                get_transaction().commit()
                if self.sleep:
                    time.sleep(self.sleep)
                break
            except (VersionLockError, ReadConflictError, ConflictError), msg:
                self.log(msg)
                get_transaction().abort()
                # sync() is necessary here to process invalidations
                # if we get a read conflict.  In the read conflict case,
                # no objects were modified so cn never got registered
                # with the transaction.
                cn.sync()
                if self.sleep:
                    time.sleep(self.sleep)
        try:
            while not self.stop.isSet():
                try:
                    if commit:
                        self.db.commitVersion(version)
                        get_transaction().note("commit version %s" % version)
                    else:
                        self.db.abortVersion(version)
                        get_transaction().note("abort version %s" % version)
                    get_transaction().commit()
                    if self.sleep:
                        time.sleep(self.sleep)
                    return commit
                except ConflictError, msg:
                    self.log(msg)
                    get_transaction().abort()
                    cn.sync()
        finally:
            cn.close()
        return 0

class InvalidationTests(CommonSetupTearDown):

    level = 2

    # Minimum # of seconds the main thread lets the workers run.  The
    # test stops as soon as this much time has elapsed, and all threads
    # have managed to commit a change.
    MINTIME = 10

    # Maximum # of seconds the main thread lets the workers run.  We
    # stop after this long has elapsed regardless of whether all threads
    # have managed to commit a change.
    MAXTIME = 300

    StressThread = StressThread

    def setUp(self):
        super(InvalidationTests, self).setUp()
        self.dbs = []

    def tearDown(self):
        for db in self.dbs:
            db.close()
        super(InvalidationTests, self).tearDown()

    def db(self, storage):
        db = DB(storage)
        self.dbs.append(db)
        return db

    def _check_tree(self, cn, tree):
        # Make sure the BTree is sane at the C level.
        retries = 3
        while retries:
            retries -= 1
            try:
                check(tree)
                tree._check()
            except ReadConflictError:
                if retries:
                    get_transaction().abort()
                    cn.sync()
                else:
                    raise
            except:
                display(tree)
                raise

    def _check_threads(self, tree, *threads):
        # Make sure the thread's view of the world is consistent with
        # the actual database state.
        expected_keys = []
        errormsgs = []
        err = errormsgs.append
        for t in threads:
            if not t.added_keys:
                err("thread %d didn't add any keys" % t.threadnum)
            expected_keys.extend(t.added_keys)
        expected_keys.sort()
        actual_keys = list(tree.keys())
        if expected_keys != actual_keys:
            err("expected keys != actual keys")
            for k in expected_keys:
                if k not in actual_keys:
                    err("key %s expected but not in tree" % k)
            for k in actual_keys:
                if k not in expected_keys:
                    err("key %s in tree but not expected" % k)
        if errormsgs:
            display(tree)
            self.fail('\n'.join(errormsgs))

    def go(self, stop, commitdict, *threads):
        # Run the threads
        for t in threads:
            t.start()
        delay = self.MINTIME
        start = time.time()
        while time.time() - start <= self.MAXTIME:
            time.sleep(delay)
            delay = 2.0
            if len(commitdict) >= len(threads):
                break
            # Some thread still hasn't managed to commit anything.
        stop.set()
        for t in threads:
            t.cleanup()

    def testConcurrentUpdates2Storages(self):
        self._storage = storage1 = self.openClientStorage()
        storage2 = self.openClientStorage()
        db1 = DB(storage1)
        db2 = DB(storage2)
        stop = threading.Event()

        cn = db1.open()
        tree = cn.root()["tree"] = OOBTree()
        get_transaction().commit()

        # Run two threads that update the BTree
        cd = {}
        t1 = self.StressThread(self, db1, stop, 1, cd, 1)
        t2 = self.StressThread(self, db2, stop, 2, cd, 2)
        self.go(stop, cd, t1, t2)

        cn.sync()
        self._check_tree(cn, tree)
        self._check_threads(tree, t1, t2)

        cn.close()
        db1.close()
        db2.close()

    def testConcurrentUpdates1Storage(self):
        self._storage = storage1 = self.openClientStorage()
        db1 = DB(storage1)
        stop = threading.Event()

        cn = db1.open()
        tree = cn.root()["tree"] = OOBTree()
        get_transaction().commit()

        # Run two threads that update the BTree
        cd = {}
        t1 = self.StressThread(self, db1, stop, 1, cd, 1, sleep=0.001)
        t2 = self.StressThread(self, db1, stop, 2, cd, 2, sleep=0.001)
        self.go(stop, cd, t1, t2)

        cn.sync()
        self._check_tree(cn, tree)
        self._check_threads(tree, t1, t2)

        cn.close()
        db1.close()

    def testConcurrentUpdates2StoragesMT(self):
        self._storage = storage1 = self.openClientStorage()
        db1 = DB(storage1)
        db2 = DB(self.openClientStorage())
        stop = threading.Event()

        cn = db1.open()
        tree = cn.root()["tree"] = OOBTree()
        get_transaction().commit()

        # Run three threads that update the BTree.
        # Two of the threads share a single storage so that it
        # is possible for both threads to read the same object
        # at the same time.

        cd = {}
        t1 = self.StressThread(self, db1, stop, 1, cd, 1, 3)
        t2 = self.StressThread(self, db2, stop, 2, cd, 2, 3, 0.001)
        t3 = self.StressThread(self, db2, stop, 3, cd, 3, 3, 0.001)
        self.go(stop, cd, t1, t2, t3)

        cn.sync()
        self._check_tree(cn, tree)
        self._check_threads(tree, t1, t2, t3)

        cn.close()
        db1.close()
        db2.close()

    def testConcurrentUpdatesInVersions(self):
        self._storage = storage1 = self.openClientStorage()
        db1 = DB(storage1)
        db2 = DB(self.openClientStorage())
        stop = threading.Event()

        cn = db1.open()
        tree = cn.root()["tree"] = OOBTree()
        get_transaction().commit()

        # Run three threads that update the BTree.
        # Two of the threads share a single storage so that it
        # is possible for both threads to read the same object
        # at the same time.

        cd = {}
        t1 = VersionStressThread(self, db1, stop, 1, cd, 1, 3)
        t2 = VersionStressThread(self, db2, stop, 2, cd, 2, 3, 0.001)
        t3 = VersionStressThread(self, db2, stop, 3, cd, 3, 3, 0.001)
        self.go(stop, cd, t1, t2, t3)

        cn.sync()
        self._check_tree(cn, tree)
        self._check_threads(tree, t1, t2, t3)

        cn.close()
        db1.close()
        db2.close()

    def testConcurrentLargeUpdates(self):
        # Use 3 threads like the 2StorageMT test above.
        self._storage = storage1 = self.openClientStorage()
        db1 = DB(storage1)
        db2 = DB(self.openClientStorage())
        stop = threading.Event()

        cn = db1.open()
        tree = cn.root()["tree"] = OOBTree()
        for i in range(0, 3000, 2):
            tree[i] = 0
        get_transaction().commit()

        # Run three threads that update the BTree.
        # Two of the threads share a single storage so that it
        # is possible for both threads to read the same object
        # at the same time.

        cd = {}
        t1 = LargeUpdatesThread(self, db1, stop, 1, cd, 1, 3, 0.001)
        t2 = LargeUpdatesThread(self, db2, stop, 2, cd, 2, 3, 0.001)
        t3 = LargeUpdatesThread(self, db2, stop, 3, cd, 3, 3, 0.001)
        self.go(stop, cd, t1, t2, t3)

        cn.sync()
        self._check_tree(cn, tree)

        # Purge the tree of the dummy entries mapping to 0.
        losers = [k for k, v in tree.items() if v == 0]
        for k in losers:
            del tree[k]
        get_transaction().commit()

        self._check_threads(tree, t1, t2, t3)

        cn.close()
        db1.close()
        db2.close()
