##############################################################################
#
# Copyright (c) 2001 Zope Corporation and Contributors.
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

"""Berkeley storage with full undo and versioning support.

$Id: bdbfull.py,v 1.30 2003/07/29 22:19:59 bwarsaw Exp $
"""

import time
import cPickle as pickle
from struct import pack, unpack
from zope.interface import implements

from zodb.interfaces import *
from zodb.storage.interfaces import *
from zodb.utils import p64, u64
from zodb.timestamp import TimeStamp, timeStampFromTime
from zodb.conflict import ResolvedSerial
from zodb.interfaces import ITransactionAttrs
from zodb.storage.interfaces import StorageSystemError
from zodb.storage.base import db, BerkeleyBase, PackStop, _WorkThread, \
     splitrefs
from zodb.storage._helper import incr
# For debugging
from zodb.interfaces import _fmt_oid as fo

ABORT = 'A'
COMMIT = 'C'
PRESENT = 'X'

BDBFULL_SCHEMA_VERSION = 'BF03'

EMPTYSTRING = ''
# Special flag for uncreated objects (i.e. Does Not Exist)
DNE = MAXTID
# DEBUGGING
#DNE = 'nonexist'



class BDBFullStorage(BerkeleyBase):

    implements(IStorage, IUndoStorage, IVersionStorage)

    def _init(self):
        # Data Type Assumptions:
        #
        # - Object ids (oid) are 8-bytes
        # - Objects have revisions, with each revision being identified by a
        #   unique serial number.  We sometimes refer to 16-byte strings of
        #   oid+serial as a revision id.
        # - Transaction ids (tid) are 8-bytes
        # - Version ids (vid) are 8-bytes
        # - Data pickles are of arbitrary length
        #
        # Here is a list of tables common between the Berkeley storages.
        # There may be some minor differences in semantics.
        #
        # info -- {key -> value}
        #     This table contains storage metadata information.  The keys and
        #     values are simple strings of variable length.   Here are the
        #     valid keys:
        #
        #         packtime - time of the last pack.  It is illegal to undo to
        #         before the last pack time.
        #
        #         dbversion - the version of the database serialization
        #         protocol (reserved for ZODB4)
        #
        #         version - the underlying Berkeley database schema version
        #
        # serials -- {oid -> [serial | serial+tid]}
        #     Maps oids to serial numbers, to make it easy to look up the
        #     serial number for the current revision of the object.  The value
        #     combined with the oid provides a revision id (revid) which is
        #     used to point into the other tables.  Usually the serial is the
        #     tid of the transaction that modified the object, except in the
        #     case of abortVersion().  Here, the serial number of the object
        #     won't change (by definition), but of course the abortVersion()
        #     happens in a new transaction so the tid pointer must change.  To
        #     handle this rare case, the value in the serials table can be a
        #     16-byte value, in which case it will contain both the serial
        #     number and the tid pointer.
        #
        # pickles -- {oid+serial -> pickle}
        #     Maps the object revisions to the revision's pickle data.
        #
        # refcounts -- {oid -> count}
        #     Maps the oid to the reference count for the object.  This
        #     reference count is updated during the _finish() call.  In the
        #     Full storage the refcounts include all the revisions of the
        #     object, so it is never decremented except at pack time.  When it
        #     goes to zero, the object is automatically deleted.
        #
        # references -- {oid+tid -> oid+oid+...}
        #     For each revision of the object, these are the oids of the
        #     objects referred to in the data record, as a list of 8-byte
        #     oids, concatenated together.
        #
        # oids -- [oid]
        #     This is a list of oids of objects that are modified in the
        #     current uncommitted transaction.
        #
        # pending -- tid -> 'A' | 'C'
        #     This is an optional flag which says what to do when the database
        #     is recovering from a crash.  The flag is normally 'A' which
        #     means any pending data should be aborted.  At the start of the
        #     tpc_finish() this flag will be changed to 'C' which means, upon
        #     recovery/restart, all pending data should be committed.  Outside
        #     of any transaction (e.g. before the tpc_begin()), there will be
        #     no pending entry.  It is a database invariant that if the
        #     pending table is empty, the oids, pvids, and prevrevids tables
        #     must also be empty.
        #
        # packmark -- oid -> [tid]
        #     Every object reachable from the root during a classic pack
        #     operation will have its oid present in this table.
        #
        # oidqueue -- [oid]
        #     This table is a Queue, not a BTree.  It is used during the mark
        #     phase of pack() and contains a list of oids for work to be done.
        #
        # These tables are specific to the BDBFullStorage implementation
        #
        # metadata -- {oid+tid -> vid+nvrevid+lrevid+previd}
        #     Maps object revisions to object metadata.  This mapping is used
        #     to find other information about a particular concrete object
        #     revision.  Essentially it stitches all the other pieces
        #     together.  The object revision is identified by the tid of the
        #     transaction in which the object was modified.  Normally this
        #     will be the serial number (IOW, the serial number and tid will
        #     be the same value), except in the case of abortVersion().  See
        #     above for details.
        #
        #     vid is the id of the version this object revision was modified
        #     in.  It will be zero if the object was modified in the
        #     non-version.
        #
        #     nvrevid is the tid pointing to the most current non-version
        #     object revision.  So, if the object is living in a version and
        #     that version is aborted, the nvrevid points to the object
        #     revision that will soon be restored.  nvrevid will be zero if
        #     the object was never modified in a version.
        #
        #     lrevid is the tid pointing to object revision's pickle state (I
        #     think of it as the "live revision id" since it's the state that
        #     gives life to the object described by this metadata record).
        #
        #     prevrevid is the tid pointing to the previous state of the
        #     object.  This is used for undo.
        #
        # txnMetadata -- {tid -> userlen+desclen+user+desc+ext}
        #     Maps tids to metadata about a transaction.
        #
        #     userlen is the length in characters of the `user' field as an
        #         8-byte unsigned long integer
        #     desclen is the length in characters of the `desc' field as an
        #         8-byte unsigned long integer
        #     user is the user information passed in the transaction object
        #     desc is the description info passed in the transaction object
        #     ext is the extra info passed in the transaction object.  It is a
        #         mapping that we get already pickled by BaseStorage.
        #
        #     Note: txnBegin() can get user and desc as Unicode strings, so
        #     they are stored in this table as utf-8 encoded byte strings, and
        #     decoded back to Unicode when requested.
        #
        # txnoids -- {tid -> [oid]}
        #     Maps transaction ids to the oids of the objects modified by the
        #     transaction.
        #
        # pickleRefcounts -- {oid+tid -> count}
        #     Maps an object revision to the reference count of that
        #     revision's pickle.  In the face of transactional undo, multiple
        #     revisions can point to a single pickle so that pickle can't be
        #     garbage collected until there are no revisions pointing to it.
        #
        # vids -- {version_string -> vid}
        #     Maps version strings (which are arbitrary) to vids.
        #
        # versions -- {vid -> version_string}
        #     Maps vids to version strings.
        #
        # currentVersions -- {vid -> [oid + tid]}
        #     Maps vids to the revids of the objects modified in that version
        #     for all current versions (except the 0th version, which is the
        #     non-version).
        #
        # pvids -- [vid]
        #     This is a list of all the version ids that have been created in
        #     the current uncommitted transaction.
        #
        # prevrevids -- {oid -> tid}
        #     This is a list of previous revision ids for objects which are
        #     modified by transactionalUndo in the current uncommitted
        #     transaction.  It's necessary to properly handle multiple
        #     transactionalUndo()'s in a single ZODB transaction.
        #
        # objrevs -- {newserial+oid -> oldserial}
        #     This table collects object revision information for packing
        #     purposes.  Every time a new object revision is committed, we
        #     write an entry to this table.  When we run pack, we iterate from
        #     the start of this table until newserial > packtime, deleting old
        #     revisions of objects.  Note that when a new revision of an
        #     object is first written to a version, no entry is written here.
        #     We do write an entry when we commit or abort the version.
        #
        # delqueue -- [oid]
        #     This is also a Queue, not a BTree.  It is used during pack to
        #     list objects for which no more references exist, such that the
        #     objects can be completely packed away.
        #
        # Temporary tables which keep information during ZODB transactions
        self._pvids = self._setupDB('pvids')
        self._prevrevids = self._setupDB('prevrevids')
        # Other tables
        self._vids            = self._setupDB('vids')
        self._versions        = self._setupDB('versions')
        self._currentVersions = self._setupDB('currentVersions', db.DB_DUP)
        self._metadata        = self._setupDB('metadata')
        self._txnMetadata     = self._setupDB('txnMetadata')
        self._txnoids         = self._setupDB('txnoids', db.DB_DUP)
        self._pickleRefcounts = self._setupDB('pickleRefcounts')
        # Tables to support packing.
        self._objrevs = self._setupDB('objrevs', db.DB_DUP)
        self._delqueue = self._setupDB('delqueue', 0, db.DB_QUEUE, 8)
        self._oidqueue = self._setupDB('oidqueue', 0, db.DB_QUEUE, 16)

    def _version_check(self, txn):
        version = self._info.get('version')
        if version is None:
            self._info.put('version', BDBFULL_SCHEMA_VERSION, txn=txn)
        elif version <> BDBFULL_SCHEMA_VERSION:
            raise StorageSystemError, 'incompatible storage version'

    def _dorecovery(self):
        # If these tables are non-empty, it means we crashed during a pack
        # operation.  I think we can safely throw out this data since the next
        # pack operation will reproduce it faithfully.
        txn = self._env.txn_begin()
        try:
            self._oidqueue.truncate(txn)
            self._packmark.truncate(txn)
        except:
            txn.abort()
            raise
        else:
            txn.commit()
        # The pendings table may have entries if we crashed before we could
        # abort or commit the outstanding ZODB transaction.
        pendings = self._pending.keys()
        assert len(pendings) <= 1
        if len(pendings) == 0:
            assert len(self._oids) == 0
            assert len(self._pvids) == 0
            assert len(self._prevrevids) == 0
        else:
            # Do recovery
            tid = pendings[0]
            flag = self._pending.get(tid)
            assert flag in (ABORT, COMMIT)
            if flag == ABORT:
                self.log('aborting pending transaction %r', tid)
                self._withtxn(self._doabort, tid)
            else:
                self.log('recovering pending transaction %r', tid)
                self._withtxn(self._docommit, tid)
        # Initialize our cache of the next available version id.
        c = self._versions.cursor()
        try:
            rec = c.last()
        finally:
            c.close()
        if rec:
            # Convert to a Python long integer.  Note that cursor.last()
            # returns key/value, and we want the key (which for the
            # versions table is the vid).
            self._nextvid = u64(rec[0])
        else:
            self._nextvid = 0L
        # Initialize the last transaction
        c = self._txnoids.cursor()
        try:
            rec = c.last()
        finally:
            c.close()
        if rec:
            self._ltid = rec[0]
        else:
            self._ltid = ZERO

    def _make_autopacker(self, event):
        config = self._config
        return _Autopack(self, event,
                         config.frequency, config.packtime, config.gcpack)

    def _doabort(self, txn, tid):
        # First clean up the oid indexed (or oid+tid indexed) tables.
        co = cs = ct = cv = cr = None
        try:
            co = self._oids.cursor(txn=txn)
            cs = self._serials.cursor(txn=txn)
            ct = self._txnoids.cursor(txn=txn)
            cv = self._currentVersions.cursor(txn=txn)
            cr = self._objrevs.cursor(txn=txn)
            rec = co.first()
            while rec:
                oid = rec[0]
                rec = co.next()
                try:
                    cs.set_both(oid, tid)
                except db.DBNotFoundError:
                    pass
                else:
                    cs.delete()
                try:
                    ct.set_both(tid, oid)
                except db.DBNotFoundError:
                    pass
                else:
                    ct.delete()
                # Now clean up the revision-indexed tables
                revid = oid+tid
                vid = self._metadata[revid][:8]
                self._metadata.delete(revid, txn=txn)
                self._pickles.delete(revid, txn=txn)
                if self._references.has_key(revid):
                    self._references.delete(revid, txn=txn)
                # Clean up the object revisions table
                try:
                    cr.set(oid+tid)
                except db.DBNotFoundError:
                    pass
                else:
                    cr.delete()
                # Now we have to clean up the currentVersions table
                if vid <> ZERO:
                    cv.set_both(vid, revid)
                    cv.delete()
        finally:
            # There's a small window of opportunity for leaking cursors here,
            # if one of the earler closes were to fail.  In practice this
            # shouldn't happen.
            if co: co.close()
            if cs: cs.close()
            if cv: cv.close()
            if cr: cr.close()
        # Now clean up the vids and versions tables
        cpv = self._pvids.cursor(txn=txn)
        try:
            rec = cpv.first()
            while rec:
                vid = rec[0]
                rec = cpv.next()
                version = self._versions[vid]
                self._versions.delete(vid, txn=txn)
                self._vids.delete(version, txn=txn)
        finally:
            cpv.close()
        # Now clean up the tid indexed table, and the temporary log tables
        self._txnMetadata.delete(tid, txn=txn)
        self._oids.truncate(txn)
        self._pvids.truncate(txn)
        self._prevrevids.truncate(txn)
        self._pending.truncate(txn)

    def _abort(self):
        pendings = self._pending.keys()
        if len(pendings) == 0:
            # Nothing to abort
            assert len(self._oids) == 0
            assert len(self._pvids) == 0
            assert len(self._prevrevids) == 0
            return
        assert len(pendings) == 1
        tid = pendings[0]
        flag = self._pending.get(tid)
        assert flag == ABORT
        self._withtxn(self._doabort, tid)

    def _docommit(self, txn, tid):
        self._pending.put(self._serial, COMMIT, txn)
        # Almost all the data's already written by now so we don't need to do
        # much more than update reference counts.  Even there, our work is
        # easy because we're not going to decref anything here.
        deltas = {}
        co = cs = None
        try:
            co = self._oids.cursor(txn=txn)
            cs = self._serials.cursor(txn=txn)
            rec = co.first()
            while rec:
                oid = rec[0]
                rec = co.next()
                # Get the pointer to the live pickle data for this revision
                metadata = self._metadata[oid + self._serial]
                lrevid = unpack('>8s', metadata[16:24])[0]
                # Incref all objects referenced by this pickle, but watch out
                # for the George Bailey Event, which has no pickle.
                if lrevid <> DNE:
                    revid = oid + lrevid
                    references = self._references.get(revid, txn=txn)
                    if references:
                        self._update(deltas, references, 1)
                    # Incref this pickle; there's a new revision pointing to it
                    refcount = self._pickleRefcounts.get(revid, ZERO, txn=txn)
                    self._pickleRefcounts.put(revid, incr(refcount, 1),
                                              txn=txn)
                # Now delete all entries from the serials table where the
                # stored tid is not equal to the committing tid.
                srec = cs.set(oid)
                while srec:
                    soid, data = srec
                    if soid <> oid:
                        break
                    if len(data) == 8:
                        stid = data
                    else:
                        # In the face of abortVersion, the first half is the
                        # serial number and the second half is the tid.
                        stid = data[8:]
                    if stid <> tid:
                        cs.delete()
                    srec = cs.next_dup()
        finally:
            # There's a small window of opportunity for leaking a cursor here,
            # if co.close() were to fail.  In practice this shouldn't happen.
            if co: co.close()
            if cs: cs.close()
        # Now incref all references
        for oid, delta in deltas.items():
            refcount = self._refcounts.get(oid, ZERO, txn=txn)
            self._refcounts.put(oid, incr(refcount, delta), txn=txn)
        # Now clean up the temporary log tables
        self._pvids.truncate(txn)
        self._prevrevids.truncate(txn)
        self._pending.truncate(txn)
        self._oids.truncate(txn)

    def _dobegin(self, txn, tid):
        # It's more convenient to store the transaction metadata now, rather
        # than in the _finish() call.  Doesn't matter because if the ZODB
        # transaction were to abort, we'd clean this up anyway.  Watch out for
        # Unicode user or description data.  XXX Assume the extended data is
        # /not/ Unicode -- it's usually a pickle.
        user, desc, ext = self._ude
        userlen = len(user)
        desclen = len(desc)
        lengths = pack('>2I', userlen, desclen)
        data = lengths + user + desc + ext
        # When a transaction begins, we set the pending flag to ABORT,
        # meaning, if we crash between now and the time we vote, all changes
        # will be aborted.
        self._pending.put(tid, ABORT, txn=txn)
        self._txnMetadata.put(tid, data, txn=txn)

    def _begin(self, tid):
        self._withtxn(self._dobegin, self._serial)

    #
    # Storing an object revision in a transaction
    #

    def _dostore(self, txn, oid, serial, data, refs, version):
        conflictresolved = False
        vid = nvrevid = ovid = ZERO
        # Check for conflict errors.  JF says: under some circumstances,
        # it is possible that we'll get two stores for the same object in
        # a single transaction.  It's not clear though under what
        # situations that can occur or what the semantics ought to be.
        # For now, we'll assume this doesn't happen.
        oserial, orevid = self._getSerialAndTidMissingOk(oid)
        if oserial is None:
            # There's never been a previous revision of this object.
            oserial = ZERO
        elif serial <> oserial:
            # The object exists in the database, but the serial number
            # given in the call is not the same as the last stored serial
            # number.  First, attempt application level conflict
            # resolution, and if that fails, raise a ConflictError.
            data, refs = self._conflict.resolve(oid, oserial, serial, data)
            conflictresolved = True
        # Do we already know about this version?  If not, we need to record
        # the fact that a new version is being created.  version will be the
        # empty string when the transaction is storing on the non-version
        # revision of the object.
        if version:
            vid = self._findcreatevid(version, txn)
        # Now get some information and do some checks on the old revision of
        # the object.  We need to get the tid of the previous transaction to
        # modify this object.  If that transaction is in a version, it must
        # be the same version as we're making this change in now.
        if orevid:
            rec = self._metadata[oid+orevid]
            ovid, onvrevid = unpack('>8s8s', rec[:16])
            if ovid == ZERO:
                # The last revision of this object was made on the
                # non-version, we don't care where the current change is
                # made.  But if we're storing this change on a version then
                # the non-version revid will be the previous revid
                if version:
                    nvrevid = orevid
            elif ovid <> vid:
                # Figure out the version name for the exception
                oversion = self._versions[ovid]
                # We're trying to make a change on a version that's different
                # than the version the current revision is on.  Nuh uh.
                raise VersionLockError(oid, oversion)
            else:
                # We're making another change to this object on this version.
                # The non-version revid is the same as for the previous
                # revision of the object.
                nvrevid = onvrevid
        # Now optimistically store data to all the tables
        newserial = self._serial
        revid = oid + newserial
        self._serials.put(oid, newserial, txn=txn)
        # Store object references, but only if the list is non-empty
        if refs:
            references = EMPTYSTRING.join(refs)
            assert len(references) % 8 == 0
            self._references.put(revid, references, txn=txn)
        self._pickles.put(revid, data, txn=txn)
        self._metadata.put(revid, vid+nvrevid+newserial+oserial, txn=txn)
        self._txnoids.put(newserial, oid, txn=txn)
        # Update the object revisions table, but only if this store isn't
        # the first one of this object in a new version.
        if not version or ovid <> ZERO:
            self._objrevs.put(newserial+oid, oserial, txn=txn)
        # Update the log tables
        self._oids.put(oid, PRESENT, txn=txn)
        if vid <> ZERO:
            self._currentVersions.put(vid, revid, txn=txn)
            self._pvids.put(vid, PRESENT, txn=txn)
        # And return the new serial number
        if conflictresolved:
            return ResolvedSerial
        return newserial

    def store(self, oid, serial, data, refs, version, transaction):
        # Lock and transaction wrapper
        if self._is_read_only:
            raise POSException.ReadOnlyError()
        if transaction is not self._transaction:
            raise StorageTransactionError(self, transaction)
        self._lock_acquire()
        try:
            return self._withtxn(self._dostore, oid, serial,
                                 data, refs, version)
        finally:
            self._lock_release()

    def _dorestore(self, txn, oid, serial, data, refs, version, prev_txn):
        tid = self._serial
        vid = nvrevid = ovid = ZERO
        prevrevid = prev_txn
        # self._serial contains the transaction id as set by
        # BaseStorage.tpc_begin().
        revid = oid + tid
        # Calculate and write the entries for version ids
        if version:
            vid = self._findcreatevid(version, txn)
        # Calculate the previous revision id for this object, but only if we
        # weren't told what to believe, via prev_txn
        if prevrevid is None:
            # Get the metadata for the current revision of the object
            cserial, crevid = self._getSerialAndTidMissingOk(oid)
            if crevid is None:
                # There's never been a previous revision of this object
                prevrevid = ZERO
            else:
                prevrevid = crevid
        # Get the metadata for the previous revision, so that we can dig out
        # the non-version revid, but only if there /is/ a previous revision
        if prevrevid <> ZERO:
            try:
                ovid, onvrevid = unpack(
                    '>8s8s', self._metadata[oid+prevrevid][:16])
            except KeyError:
                # prev_txn is just a hint.  If the transaction it points to
                # does not exist, perhaps because it's been packed away, just
                # ignore it.  Also, check to see if the data matches.  If
                # not...
                prevrevid = ZERO
            else:
                if ovid == ZERO:
                    # The last revision of this object was made on the
                    # non-version, we don't care where the current change is
                    # made.  But if we're storing this change on a version
                    # then the non-version revid will be the previous revid
                    if version:
                        nvrevid = prevrevid
                else:
                    # We're making another change to this object on this
                    # version.  The non-version revid is the same as for the
                    # previous revision of the object.
                    nvrevid = onvrevid
        # Check for George Bailey Events
        if data is None:
            lrevid = DNE
        else:
            # Store the pickle record.  Remember that the reference counts are
            # updated in _docommit().
            self._pickles.put(revid, data, txn=txn)
            lrevid = tid
        # Update the serials table, but if the transaction id is different
        # than the serial number, we need to write our special long record
        if serial <> tid:
            self._serials.put(oid, serial+tid, txn=txn)
        else:
            self._serials.put(oid, serial, txn=txn)
        # Update the rest of the tables
        self._metadata.put(revid, vid+nvrevid+lrevid+prevrevid, txn=txn)
        if refs:
            self._references.put(revid, EMPTYSTRING.join(refs), txn=txn)
        self._txnoids.put(tid, oid, txn=txn)
        self._oids.put(oid, PRESENT, txn=txn)
        if vid <> ZERO:
            self._currentVersions.put(vid, revid, txn=txn)
        # Update the object revisions table, but only if this store isn't
        # the first one of this object in a new version.
        if not version or ovid <> ZERO:
            self._objrevs.put(tid+oid, prevrevid, txn=txn)

    def restore(self, oid, serial, data, refs, version, prev_txn, transaction):
        # A lot like store() but without all the consistency checks.  This
        # should only be used when we /know/ the data is good, hence the
        # method name.  While the signature looks like store() there are some
        # differences:
        #
        # - serial is the serial number of /this/ revision, not of the
        #   previous revision.  It is used instead of self._serial, which is
        #   ignored.
        #
        # - Nothing is returned
        #
        # - data can be None, which indicates a George Bailey object
        #   (i.e. one who's creation has been transactionally undone).
        #
        # prev_txn is a backpointer.  In the original database, it's possible
        # that the data was actually living in a previous transaction.  This
        # can happen for transactional undo and other operations, and is used
        # as a space saving optimization.  Under some circumstances the
        # prev_txn may not actually exist in the target database (i.e. self)
        # for example, if it's been packed away.  In that case, the prev_txn
        # should be considered just a hint, and is ignored if the transaction
        # doesn't exist.
        if transaction is not self._transaction:
            raise StorageTransactionError(self, transaction)
        self._lock_acquire()
        try:
            self._withtxn(
                self._dorestore, oid, serial, data, refs, version, prev_txn)
        finally:
            self._lock_release()

    #
    # Things we can do in and to a version
    #

    def _findcreatevid(self, version, txn):
        # Get the vid associated with a version string, or create one if there
        # is no vid for the version.  If we're creating a new version entry,
        # we need to update the pvids table in case the transaction current in
        # progress gets aborted.
        vid = self._vids.get(version)
        if vid is None:
            self._nextvid += 1
            # Convert the version id into an 8-byte string
            vid = p64(self._nextvid)
            # Now update the vids/versions tables, along with the log table
            self._vids.put(version, vid, txn=txn)
            self._versions.put(vid, version, txn=txn)
            self._pvids.put(vid, PRESENT, txn=txn)
        return vid

    def _doAbortVersion(self, txn, version):
        vid = self._vids.get(version)
        if vid is None:
            raise VersionError, 'not a version: %s' % version
        # We need to keep track of the oids that are affected by the abort so
        # that we can return it to the connection, which must invalidate the
        # objects so they can be reloaded.
        rtnoids = {}
        c = self._currentVersions.cursor(txn)
        try:
            try:
                rec = c.set_range(vid)
            except db.DBNotFoundError:
                rec = None
            while rec:
                cvid, revid = rec
                if cvid <> vid:
                    # No more objects modified in this version
                    break
                oid = revid[:8]
                if rtnoids.has_key(oid):
                    # We've already dealt with this oid
                    c.delete()
                    rec = c.next()
                    continue
                # This object was modified
                rtnoids[oid] = True
                # Calculate the values for the new transaction metadata
                serial, tid = self._getSerialAndTid(oid)
                meta = self._metadata[oid+tid]
                curvid, nvrevid = unpack('>8s8s', meta[:16])
                assert curvid == vid
                if nvrevid <> ZERO:
                    # Get the non-version data for the object.  We're mostly
                    # interested in the lrevid, i.e. the pointer to the pickle
                    # data in the non-version
                    nvmeta = self._metadata[oid+nvrevid]
                    xcurvid, xnvrevid, lrevid = unpack('>8s8s8s', nvmeta[:24])
                    assert xcurvid == ZERO
                    assert xnvrevid == ZERO
                else:
                    # This object was created in the version, so there's no
                    # non-version data that might have an lrevid.
                    lrevid = DNE
                # Write all the new data to the serials and metadata tables.
                # Note that in an abortVersion the serial number of the object
                # must be the serial number used in the non-version data,
                # while the transaction id is the current transaction.  This
                # is the one case where serial <> tid, and a special record
                # must be written to the serials table for this.
                newserial = self._serial
                self._serials.put(oid, nvrevid+newserial, txn=txn)
                self._metadata.put(oid+newserial, ZERO+ZERO+lrevid+tid,
                                   txn=txn)
                self._txnoids.put(newserial, oid, txn=txn)
                self._oids.put(oid, PRESENT, txn=txn)
                # Now we need to write two records to the object revisions
                # table.  First, it's the record containing the previous
                # serial number, and then it's a record containing the
                # non-version serial number (but make sure the object wasn't
                # created in the version).
                self._objrevs.put(newserial+oid, tid, txn=txn)
                self._objrevs.put(newserial+oid, nvrevid, txn=txn)
                c.delete()
                rec = c.next()
            # XXX Should we garbage collect vids and versions?  Doing so might
            # interact badly with transactional undo because say we delete the
            # record of the version here, and then we undo the txn with the
            # abortVersion?  We'll be left with metadata records that contain
            # vids for which we know nothing about.  So for now, no, we never
            # remove stuff from the vids or version tables.  I think this is
            # fine in practice since the number of versions should be quite
            # small over the lifetime of the database.  Maybe we can figure
            # out a way to do this in the pack operations.
            return rtnoids.keys()
        finally:
            c.close()

    def abortVersion(self, version, transaction):
        # Abort the version, but retain enough information to make the abort
        # undoable.
        if transaction is not self._transaction:
            raise StorageTransactionError(self, transaction)
        # We can't abort the empty version, because it's not a version!
        if not version:
            raise VersionError
        self._lock_acquire()
        try:
            return self._withtxn(self._doAbortVersion, version)
        finally:
            self._lock_release()

    def _doCommitVersion(self, txn, src, dest):
        # Keep track of the oids affected by this commit.  See abortVersion()
        rtnoids = {}
        # Get the version ids associated with the src and dest version strings
        svid = self._vids[src]
        if not dest:
            dvid = ZERO
        else:
            # Find the vid for the dest version, or create one if necessary.
            dvid = self._findcreatevid(dest, txn)
        c = self._currentVersions.cursor(txn)
        try:
            try:
                rec = c.set_range(svid)
            except db.DBNotFoundError:
                rec = None
            while rec:
                cvid, revid = rec
                if cvid <> svid:
                    # No more objects modified in this version
                    break
                oid = revid[:8]
                if rtnoids.has_key(oid):
                    # We've already dealt with this oid
                    c.delete()
                    rec = c.next()
                    continue
                # This object was modified
                rtnoids[oid] = True
                # Calculate the values for the new transaction metadata
                serial, tid = self._getSerialAndTid(oid)
                meta = self._metadata[oid+tid]
                curvid, nvrevid, lrevid = unpack('>8s8s8s', meta[:24])
                assert curvid == svid
                # If we're committing to the non-version, then the nvrevid
                # ought to be ZERO too, regardless of what it was for the
                # source version.
                if not dest:
                    nvrevid = ZERO
                newserial = self._serial
                self._serials.put(oid, newserial, txn=txn)
                self._metadata.put(oid+newserial, dvid+nvrevid+lrevid+tid,
                                   txn=txn)
                self._txnoids.put(newserial, oid, txn=txn)
                self._oids.put(oid, PRESENT, txn=txn)
                # Now we need to write two records to the object revisions
                # table.  First, it's the record containing the previous
                # serial number, and then it's a record containing the
                # non-version serial number.  However, if we're committing to
                # a different version, don't write the second record.
                self._objrevs.put(newserial+oid, tid, txn=txn)
                if not dest:
                    self._objrevs.put(newserial+oid, nvrevid, txn=txn)
                c.delete()
                rec = c.next()
            return rtnoids.keys()
        finally:
            c.close()

    def commitVersion(self, src, dest, transaction):
        # Commit a source version `src' to a destination version `dest'.  It's
        # perfectly valid to move an object from one version to another.  src
        # and dest are version strings, and if we're committing to a
        # non-version, dest will be empty.
        if transaction is not self._transaction:
            raise StorageTransactionError(self, transaction)
        # Sanity checks
        if not src or src == dest:
            raise VersionCommitError
        self._lock_acquire()
        try:
            return self._withtxn(self._doCommitVersion, src, dest)
        finally:
            self._lock_release()

    def modifiedInVersion(self, oid):
        # Return the version string of the version that contains the most
        # recent change to the object.  The empty string means the change
        # isn't in a version.
        self._lock_acquire()
        try:
            # Let KeyErrors percolate up
            serial, tid = self._getSerialAndTid(oid)
            vid = self._metadata[oid+tid][:8]
            if vid == ZERO:
                # Not in a version
                return ''
            return self._versions[vid]
        finally:
            self._lock_release()

    def versionEmpty(self, version):
        # Return true if version is empty.
        self._lock_acquire()
        try:
            # First, check if we're querying the empty (i.e. non) version
            if not version:
                c = self._serials.cursor()
                try:
                    rec = c.first()
                    return not rec
                finally:
                    c.close()
            # If the named version doesn't exist or there are no objects in
            # the version, then return true.
            missing = []
            vid = self._vids.get(version, missing)
            if vid is missing:
                return True
            return not self._currentVersions.has_key(vid)
        finally:
            self._lock_release()

    def versions(self, max=None):
        # Return the list of current versions, as version strings, up to the
        # maximum requested.
        retval = []
        self._lock_acquire()
        try:
            try:
                c = self._currentVersions.cursor()
                rec = c.first()
                while rec and (max is None or max > 0):
                    # currentVersions maps vids to [oid]'s so dig the key out
                    # of the returned record and look the vid up in the
                    # vids->versions table.
                    retval.append(self._versions[rec[0]])
                    # Since currentVersions has duplicates (i.e. multiple vid
                    # keys with different oids), get the next record that has
                    # a different key than the current one.
                    rec = c.next_nodup()
                    if max is not None:
                        max -= 1
                return retval
            finally:
                c.close()
        finally:
            self._lock_release()

    #
    # Accessor interface
    #

    def load(self, oid, version):
        self._lock_acquire()
        try:
            # Get the current revision information for the object.  As per the
            # protocol, let Key errors percolate up.
            serial, tid = self._getSerialAndTid(oid)
            # Get the metadata associated with this revision of the object.
            # All we really need is the vid, the non-version revid and the
            # pickle pointer revid.
            rec = self._metadata[oid+tid]
            vid, nvrevid, lrevid = unpack('>8s8s8s', rec[:24])
            if lrevid == DNE:
                raise KeyError, 'Object does not exist: %r' % oid
            # If the object isn't living in a version, or if the version the
            # object is living in is the one that was requested, we simply
            # return the current revision's pickle.
            if vid == ZERO or self._versions.get(vid) == version:
                return self._pickles[oid+lrevid], serial
            # The object was living in a version, but not the one requested.
            # Semantics here are to return the non-version revision.  Allow
            # KeyErrors to percolate up (meaning there's no non-version rev).
            lrevid = self._metadata[oid+nvrevid][16:24]
            return self._pickles[oid+lrevid], nvrevid
        finally:
            self._lock_release()

    def _getSerialAndTidMissingOk(self, oid):
        # For the object, return the curent serial number and transaction id
        # of the last transaction that modified the object.  Usually these
        # will be the same, unless the last transaction was an abortVersion.
        # Also note that the serials table is written optimistically so we may
        # have multiple entries for this oid.  We need to collect them in
        # order and return the latest one if the pending flag is COMMIT, or
        # the second to latest one if the pending flag is ABORT.
        #
        # BAW: We must have the application level lock here.
        c = self._serials.cursor()
        try:
            # There can be zero, one, or two entries in the serials table for
            # this oid.  If there are no entries, raise a KeyError (we know
            # nothing about this object).
            #
            # If there is exactly one entry then this has to be the entry for
            # the object, regardless of the pending flag.
            #
            # If there are two entries, then we need to look at the pending
            # flag to decide which to return (there /better/ be a pending flag
            # set!).  If the pending flag is COMMIT then we've already voted
            # so the second one is the good one.  If the pending flag is ABORT
            # then we haven't yet committed to this transaction so the first
            # one is the good one.
            serials = []
            try:
                rec = c.set(oid)
            except db.DBNotFoundError:
                rec = None
            while rec:
                serials.append(rec[1])
                rec = c.next_dup()
            if not serials:
                return None, None
            if len(serials) == 1:
                data = serials[0]
            else:
                pending = self._pending.get(self._serial)
                assert pending in (ABORT, COMMIT), 'pending: %s' % pending
                if pending == ABORT:
                    data = serials[0]
                else:
                    data = serials[1]
            if len(data) == 8:
                return data, data
            return data[:8], data[8:]
        finally:
            c.close()

    def _getSerialAndTid(self, oid):
        # For the object, return the curent serial number and transaction id
        # of the last transaction that modified the object.  Usually these
        # will be the same, unless the last transaction was an abortVersion
        serial, tid = self._getSerialAndTidMissingOk(oid)
        if serial is None and tid is None:
            raise KeyError, 'Object does not exist: %r' % oid
        return serial, tid

    def _loadSerialEx(self, oid, serial):
        # Just like loadSerial, except that it returns the pickle data, the
        # version this object revision is living in, a backpointer, and the
        # object references.  The backpointer is None if the lrevid for this
        # metadata record is the same as the tid.  If not, we have a pointer
        # to previously existing data, so we return that.
        self._lock_acquire()
        try:
            # Get the pointer to the pickle for the given serial number.  Let
            # KeyErrors percolate up.
            metadata = self._metadata[oid+serial]
            vid, ign, lrevid = unpack('>8s8s8s', metadata[:24])
            if vid == ZERO:
                version = ''
            else:
                version = self._versions[vid]
            # Check for an zombification event, possible with transactional
            # undo.  Use data==None to specify that.
            if lrevid == DNE:
                return None, version, None, None
            backpointer = None
            if lrevid <> serial:
                # This transaction shares its pickle data with a previous
                # transaction.  We need to let the caller know, esp. when it's
                # the iterator code, so that it can pass this information on.
                backpointer = lrevid
            # Also return the list of oids referred to by this object
            refs = self._references.get(oid+lrevid)
            if refs is None:
                refs = []
            else:
                refs = splitrefs(refs)
            return self._pickles[oid+lrevid], version, backpointer, refs
        finally:
            self._lock_release()

    def loadSerial(self, oid, serial):
        return self._loadSerialEx(oid, serial)[0]

    def getSerial(self, oid):
        # Return the serial number for the current revision of this object,
        # irrespective of any versions.
        self._lock_acquire()
        try:
            serial, tid = self._getSerialAndTid(oid)
            # See if the object has been uncreated
            lrevid = unpack('>8s', self._metadata[oid+tid][16:24])[0]
            if lrevid == DNE:
                raise KeyError
            return serial
        finally:
            self._lock_release()

    def _last_packtime(self):
        return self._info.get('packtime', ZERO)

    def lastSerial(self, oid):
        """Return last serialno committed for object oid.

        If there is no serialno for this oid -- which can only occur
        if it is a new object -- return None.
        """
        return self._getSerialAndTidMissingOk(oid)[0]

    #
    # Transactional undo
    #

    def _undo_current_tid(self, oid, ctid):
        # Returns (oid, metadata record, None, None).  The last two represent
        # the data and the references, both of which will always be None
        # because there's no conflict resolution necessary.
        vid, nvrevid, lrevid, prevrevid = unpack(
            '>8s8s8s8s', self._metadata[oid+ctid])
        # We can always undo the last transaction.  The prevrevid pointer
        # doesn't necessarily point to the previous transaction, if the
        # revision we're undoing was itself an undo.  Use a cursor to find the
        # previous revision of this object.
        mdc = self._metadata.cursor()
        try:
            mdc.set(oid+ctid)
            mrec = mdc.prev()
            if not mrec or mrec[0][:8] <> oid:
                # The previous transaction metadata record doesn't point to
                # one for this object.  This could be caused by two
                # conditions: either we're undoing the creation of the object,
                # or the object creation transaction has been packed away.
                # Checking the current record's prevrevid will tell us.
                return oid, vid+nvrevid+DNE+ctid, None, None
            # BAW: If the serial number of this object record is the same as
            # the serial we're being asked to undo, then I think we have a
            # problem (since the storage invariant is that it retains only one
            # metadata record per object revision).
            assert mrec[0][8:] <> ctid, 'storage invariant violated'
            # All is good, so just restore this metadata record
            return oid, mrec[1], None, None
        finally:
            mdc.close()

    def _undo_to_same_pickle(self, oid, tid, ctid):
        # Returns (oid, metadata record, data, refs).  Data and refs will both
        # always be None unless conflict resolution was necessary and
        # succeeded.
        #
        # We need to compare the lrevid (pickle pointers) of the transaction
        # previous to the current one, and the transaction previous to the one
        # we want to undo.  If their lrevids are the same, it's undoable
        # because we're undoing to the same pickle state.
        last_prevrevid = self._metadata[oid+ctid][24:]
        target_prevrevid = self._metadata[oid+tid][24:]
        if target_prevrevid == last_prevrevid == ZERO:
            # We're undoing the object's creation, so the only thing to undo
            # from there is the zombification of the object, i.e. the last
            # transaction for this object.
            vid, nvrevid = unpack('>8s8s', self._metadata[oid+tid][:16])
            return oid, vid+nvrevid+DNE+ctid, None, None
        elif target_prevrevid == ZERO or last_prevrevid == ZERO:
            # The object's revision is in its initial creation state but we're
            # asking for an undo of something other than the initial creation
            # state.  No, no.
            raise UndoError, 'Undoing mismatched zombification'
        last_lrevid     = self._metadata[oid+last_prevrevid][16:24]
        target_metadata = self._metadata[oid+target_prevrevid]
        target_lrevid   = target_metadata[16:24]
        # If the pickle pointers of the object's last revision and the
        # undo-target revision are the same, then the transaction can be
        # undone.  Note that we cannot test for pickle equality here because
        # that would allow us to undo to an arbitrary object history.  Imagine
        # a boolean object -- if undo tested for equality and not identity,
        # then half the time we could undo to an arbitrary point in the
        # object's history.
        if target_lrevid == last_lrevid:
            return oid, target_metadata, None, None
        # Check previous undos done in this transaction
        elif target_lrevid == self._prevrevids.get(oid):
            return oid, target_metadata, None, None
        else:
            # Attempt application level conflict resolution
            try:
                data, refs = self._conflict.resolve(
                    oid, ctid, tid, self._pickles[oid+target_lrevid])
            except ConflictError:
                raise UndoError, 'Cannot undo transaction'
            return oid, target_metadata, data, refs

    def _doundo(self, txn, tid):
        # First, make sure the transaction isn't protected by a pack.
        packtime = self._last_packtime()
        if tid <= packtime:
            raise UndoError, 'Transaction cannot be undone'
        # Calculate all the oids of objects modified in this transaction
        newrevs = []
        c = self._txnoids.cursor(txn=txn)
        try:
            rec = c.set(tid)
            while rec:
                oid = rec[1]
                rec = c.next_dup()
                # In order to be able to undo this transaction, we must be
                # undoing either the current revision of the object, or we
                # must be restoring the exact same pickle (identity compared)
                # that would be restored if we were undoing the current
                # revision.  Otherwise, we attempt application level conflict
                # resolution.  If that fails, we raise an exception.
                cserial, ctid = self._getSerialAndTid(oid)
                if ctid == tid:
                    newrevs.append(self._undo_current_tid(oid, ctid))
                else:
                    newrevs.append(self._undo_to_same_pickle(oid, tid, ctid))
        finally:
            c.close()
        # We've checked all the objects affected by the transaction we're
        # about to undo, and everything looks good.  So now we'll write the
        # new metadata records (and potentially new pickle records).
        rtnoids = {}
        for oid, metadata, data, refs in newrevs:
            newserial = self._serial
            revid = oid + self._serial
            # If the data pickle is None, then this undo is simply
            # re-using a pickle stored earlier.  All we need to do then is
            # bump the pickle refcount to reflect this new reference,
            # which will happen during _docommit().  Otherwise we need to
            # store the new pickle data and calculate the new lrevid.
            vid, nvrevid, ign, prevrevid = unpack('>8s8s8s8s', metadata)
            if data is not None:
                # data and refs go hand in hand
                assert refs is not None
                self._pickles.put(revid, data, txn=txn)
                self._references.put(revid, EMPTYSTRING.join(refs), txn=txn)
                metadata = vid+nvrevid+newserial+prevrevid
            else:
                # data and refs go hand in hand
                assert refs is None
            # We need to write all the new records for an object changing in
            # this transaction.  Note that we only write to the serials table
            # if prevrevids hasn't already seen this object, otherwise we'll
            # end up with multiple entries in the serials table for the same
            # object revision.
            if not self._prevrevids.has_key(oid):
                self._serials.put(oid, newserial, txn=txn)
            self._metadata.put(revid, metadata, txn=txn)
            # Only add this oid to txnoids once
            if not rtnoids.has_key(oid):
                self._prevrevids.put(oid, prevrevid, txn=txn)
                self._txnoids.put(newserial, oid, txn=txn)
                if vid <> ZERO:
                    self._currentVersions.put(vid, revid, txn=txn)
            self._oids.put(oid, PRESENT, txn=txn)
            rtnoids[oid] = True
            # Add this object revision to the autopack table
            self._objrevs.put(newserial+oid, prevrevid, txn=txn)
        return rtnoids.keys()

    def undo(self, tid, transaction):
        if transaction is not self._transaction:
            raise StorageTransactionError(self, transaction)
        self._lock_acquire()
        try:
            return self._withtxn(self._doundo, tid)
        finally:
            self._lock_release()

    def _unpack_txnmeta(self, txnmeta):
        userlen, desclen = unpack('>2I', txnmeta[:8])
        usafe = txnmeta[8:8+userlen]
        dsafe = txnmeta[8+userlen:8+userlen+desclen]
        # user and desc are utf-8 encoded
        user = usafe.decode('utf-8')
        desc = dsafe.decode('utf-8')
        extdata = txnmeta[8+userlen+desclen:]
        # ext is a pickled mapping.  Any exceptions are ignored, but XXX can
        # we (and FileStorage :) do better?
        ext = {}
        if extdata:
            try:
                ext = pickle.loads(extdata)
            except Exception, e:
                self.log('Error unpickling extension data: %s', e)
        return user, desc, ext

    def _doundolog(self, first, last, filter):
        # Get the last packtime
        packtime = self._last_packtime()
        i = 0                                     # first <= i < last
        txnDescriptions = []                      # the return value
        c = self._txnMetadata.cursor()
        try:
            # We start at the last transaction and scan backwards because we
            # can stop early if we find a transaction that is earlier than a
            # pack.  We still have the potential to scan through all the
            # transactions.
            rec = c.last()
            while rec and i < last:
                tid, txnmeta = rec
                rec = c.prev()
                if tid <= packtime:
                    break
                user, desc, ext = self._unpack_txnmeta(txnmeta)
                # Create a dictionary for the TransactionDescription
                txndesc = {'id'         : tid,
                           'time'       : TimeStamp(tid).timeTime(),
                           'user_name'  : user,
                           'description': desc,
                           }
                # Update the transaction description dictionary with the
                # extension mapping.
                txndesc.update(ext)
                # Now call the filter to see if this transaction should be
                # added to the return list...
                if filter is None or filter(txndesc):
                    # ...and see if this is within the requested ordinals
                    if i >= first:
                        txnDescriptions.append(txndesc)
                    i += 1
            return txnDescriptions
        finally:
            c.close()

    def undoLog(self, first=0, last=-20, filter=None):
        # Get a list of transaction ids that can be undone, based on the
        # determination of the filter.  filter is a function which takes a
        # transaction description and returns true or false.
        #
        # Note that this method has been deprecated by undoInfo() which itself
        # has some flaws, but is the best we have now.  We don't actually need
        # to implement undoInfo() because BaseStorage (which we eventually
        # inherit from) mixes in the UndoLogCompatible class which provides an
        # implementation written in terms of undoLog().
        #
        # Interface specifies that if last is < 0, its absolute value is the
        # maximum number of transactions to return.
        if last < 0:
            last = abs(last)
        return self._withlock(self._doundolog, first, last, filter)

    # Packing
    #
    # There are two types of pack operations, the classic pack and the
    # autopack.  Autopack's primary job is to periodically delete non-current
    # object revisions.  It runs in a thread and has an `autopack time' which
    # is essentially just a time in the past at which to autopack to.  For
    # example, you might set up autopack to run once per hour, packing away
    # all revisions that are older than 4 hours.  Autopack can also be
    # configured to periodically do a classic pack.
    #
    # Classic pack is like autopack -- it packs away old revisions -- but it
    # also does a mark and sweep through all the known objects, looking for
    # those that are not root reachable as of the pack time.  Such objects are
    # also packed away even if they have current revisions in the packable
    # transactions, because it means that there is no undo operation that can
    # restore the object's reachability.  Remember that you cannot undo
    # previous to the latest pack time.
    #
    # Both packing strategies do reference counting, and the refcounts are
    # sums of the refcounts of all revisions, so if an object's refcount goes
    # to zero, all its object revisions can safely be packed away.
    #
    # We try to interleave BerkeleyDB transactions and non-pack-lock
    # acquisition as granularly as possible so that packing doesn't block
    # other operations for too long.  But remember we don't use Berkeley locks
    # so we have to be careful about our application level locks.

    def pack(self, t, gc=True):
        """Perform a pack on the storage.

        There are two forms of packing: incremental and full gc.  In an
        incremental pack, only old object revisions are removed.  In a full gc
        pack, cyclic garbage detection and removal is also performed.

        t is the pack time.  All non-current object revisions older than t
        will be removed in an incremental pack.

        pack() always performs an incremental pack.  If the gc flag is True,
        then pack() will also perform a garbage collection.  Some storages
        (e.g. FileStorage) always do both phases in a pack() call.  Such
        storages should simply ignore the gc flag.
        """
        self.log('pack started (packtime: %s, gc? %s)', t,
                 (gc and 'yes' or 'no'))
        # A simple wrapper around the bulk of packing, but which acquires a
        # lock that prevents multiple packs from running at the same time.
        self._packlock.acquire()
        self._packing = True
        try:
            # We don't wrap this in _withtxn() because we're going to do the
            # operation across several Berkeley transactions, which allows
            # other work to happen (stores and reads) while packing is being
            # done.
            self._dopack(t, gc)
        finally:
            self._packing = False
            self._packlock.release()
        self.log('pack finished')

    def _dopack(self, t, gc):
        # BAW: should a pack time in the future be a ValueError?  When ZEO is
        # involved, t could come from a remote machine with a skewed clock.
        # Jim wants us to believe t if it's "close", but our algorithm
        # requires synchronicity between the calculation of the pack time and
        # the timestamps used in serial numbers.
        #
        # If a transaction is currently in progress, wait for it to finish
        # before calculating the pack time, by acquiring the commit lock.
        # This guarantees that the next transaction begins after the pack
        # time so that any objects added in that transaction will have a
        # serial number greater than the pack time.  Such objects will be
        # completely ignored for packing purposes.
        #
        # If we don't do this, then it would be possible for some of the
        # current transaction's objects to have been stored with a serial
        # number earlier than the pack time, but not yet linked to the root.
        # Say that thread 1 starts a transaction, and then thread 2 starts a
        # pack.  Thread 2 then marks the root-reachable objects, but before
        # sweeping, object B is stored by thread 1.  If the object linking B
        # to the root hasn't been stored by the time of the sweep, B will be
        # collected as garbage.
        self._commit_lock_acquire()
        try:
            packtime = min(t, time.time())
            packtid = timeStampFromTime(packtime).raw()
        finally:
            self._commit_lock_release()
        # Collect all revisions of all objects earlier than the pack time.
        self._lock_acquire()
        try:
            self._withtxn(self._collect_revs, packtid)
        finally:
            self._lock_release()
        # Collect any objects with refcount zero.
        self._lock_acquire()
        try:
            self._withtxn(self._collect_objs)
        finally:
            self._lock_release()
        # If we're not doing a classic pack, we're done.
        if not gc:
            return
        # Do a mark and sweep for garbage collection.  Calculate the set of
        # objects reachable from the root.  Anything else is a candidate for
        # having all their revisions packed away.  The set of reachable
        # objects lives in the _packmark table.
        self._lock_acquire()
        try:
            self._withtxn(self._mark, packtid)
        finally:
            self._lock_release()
        # Now perform a sweep, using oidqueue to hold all object ids for
        # objects which are not root reachable as of the pack time.
        self._lock_acquire()
        try:
            self._withtxn(self._sweep, packtid)
        finally:
            self._lock_release()
        # Once again, collect any objects with refcount zero due to the mark
        # and sweep garbage collection pass.
        self._lock_acquire()
        try:
            self._withtxn(self._collect_objs)
        finally:
            self._lock_release()

    def _collect_revs(self, txn, packtid):
        ct = co = None
        try:
            co = self._objrevs.cursor(txn=txn)
            ct = self._txnoids.cursor(txn=txn)
            rec = co.first()
            while rec:
                if self._stop:
                    raise PackStop, 'stopped in _collect_revs()'
                revid, oldserial = rec
                newserial = revid[:8]
                oid = revid[8:]
                if newserial > packtid:
                    break
                # If the oldserial is ZERO, then this is the first revision of
                # the object, and thus no old revision to pack away.  We can
                # delete this record from objrevs so we won't have to deal
                # with it again.  Otherwise, we can remove the metadata record
                # for this revision and decref the corresponding pickle.
                if oldserial <> ZERO:
                    orevid = oid+oldserial
                    # It's possible this object revision has already been
                    # deleted, if the oid points to a decref'd away object
                    if self._metadata.has_key(orevid):
                        metadata = self._metadata[orevid]
                        self._metadata.delete(orevid, txn=txn)
                        # Decref the pickle
                        self._decrefPickle(oid, metadata[16:24], txn)
                    try:
                        # Remove the txnoids entry.  We have to use a cursor
                        # here because of the set_both().
                        ct.set_both(oldserial, oid)
                    except db.DBNotFoundError:
                        pass
                    else:
                        ct.delete()
                co.delete()
                rec = co.next()
        finally:
            if co: co.close()
            if ct: ct.close()
        # Note that before we commit this Berkeley transaction, we also need
        # to update the last packtime entry, so we can't have the possibility
        # of a race condition with undoLog().
        self._info.put('packtime', packtid, txn=txn)

    def _decrefPickle(self, oid, lrevid, txn):
        if lrevid == DNE:
            # There is no pickle data
            return
        revid = oid + lrevid
        refcount = u64(self._pickleRefcounts.get(revid, ZERO)) - 1
        assert refcount >= 0
        if refcount == 0:
            # We can collect this pickle and the references
            self._pickleRefcounts.delete(revid, txn=txn)
            self._pickles.delete(revid, txn=txn)
            # And decref all objects pointed to by this pickle
            references = self._references.get(revid, txn=txn)
            if references:
                deltas = {}
                self._update(deltas, references, -1)
                self._decref(deltas, txn)
                self._references.delete(revid, txn=txn)
        else:
            self._pickleRefcounts.put(revid, p64(refcount), txn=txn)

    def _decref(self, deltas, txn):
        for oid, delta in deltas.items():
            refcount = u64(self._refcounts.get(oid, ZERO)) + delta
            if refcount > 0:
                self._refcounts.put(oid, p64(refcount), txn=txn)
            else:
                # This object is no longer referenced by any other object in
                # the system.  We can collect all traces of it.
                self._delqueue.append(oid, txn)

    def _collect_objs(self, txn):
        orec = self._delqueue.consume(txn)
        while orec:
            if self._stop:
                raise PackStop, 'stopped in _collect_objs()'
            oid = orec[1]
            # Delete the object from the serials table
            c = self._serials.cursor(txn)
            try:
                try:
                    rec = c.set(oid)
                except db.DBNotFoundError:
                    rec = None
                while rec and rec[0] == oid:
                    if self._stop:
                        raise PackStop, 'stopped in _collect_objs() loop 1'
                    c.delete()
                    rec = c.next_dup()
                # We don't need the refcounts any more, but note that if the
                # object was never referenced from another object, there may
                # not be a refcounts entry.
                try:
                    self._refcounts.delete(oid, txn=txn)
                except db.DBNotFoundError:
                    pass
            finally:
                c.close()
            # Collect all metadata records for this object
            c = self._metadata.cursor(txn)
            try:
                try:
                    rec = c.set_range(oid)
                except db.DBNotFoundError:
                    rec = None
                while rec and rec[0][:8] == oid:
                    if self._stop:
                        raise PackStop, 'stopped in _collect_objs() loop 2'
                    revid, metadata = rec
                    tid = revid[8:]
                    c.delete()
                    rec = c.next()
                    self._decrefPickle(oid, metadata[16:24], txn)
                    # Delete the txnoid entry for this revision
                    ct = self._txnoids.cursor(txn=txn)
                    try:
                        ct.set_both(tid, oid)
                        ct.delete()
                    finally:
                        ct.close()
                    # Clean up version related tables
                    vid = metadata[:8]
                    if vid <> ZERO:
                        cv = self._currentVersions.cursor(txn=txn)
                        try:
                            try:
                                cv.set_both(vid, revid)
                            except db.DBNotFoundError:
                                pass
                            else:
                                cv.delete()
                        finally:
                            cv.close()
                    # BAW: maybe we want to refcount vids and versions table
                    # entries, but given the rarity of versions, this
                    # seems like too much work for too little gain.
            finally:
                c.close()
            # We really do want this down here, since _decrefPickle() could
            # add more items to the queue.
            orec = self._delqueue.consume(txn)
        assert len(self._delqueue) == 0

    def _findrev(self, oid, packtid, txn):
        # BAW: Maybe this could probably be more efficient by not doing so
        # much searching, but it would also be more complicated, so the
        # tradeoff should be measured.
        serial, tid = self._getSerialAndTid(oid)
        c = self._metadata.cursor(txn=txn)
        try:
            rec = c.set_range(oid)
            while rec:
                revid, metadata = rec
                coid = revid[:8]
                ctid = revid[8:]
                if coid <> oid or ctid > packtid:
                    # We found the end of the metadata records for this
                    # object prior to the pack time.
                    break
                serial = ctid
                rec = c.next()
        finally:
            c.close()
        return serial

    def _rootset(self, packtid, txn):
        # Find the root set for reachability purposes.  A root set is a tuple
        # of oid and tid.  First, the current root object as of the pack time
        # is always in the root set.  Second, any object revision after the
        # pack time that has a back pointer (lrevid) to before the pack time
        # serves as another root because some future undo could then revive
        # any referenced objects.  The root set ends up in the oidqueue.
        try:
            zerorev = self._findrev(ZERO, packtid, txn)
        except KeyError:
            # There's no root object
            return
        self._oidqueue.append(ZERO+zerorev, txn)
        c = self._txnoids.cursor(txn)
        try:
            try:
                rec = c.set_range(packtid)
            except db.DBNotFoundError:
                rec = None
            while rec:
                tid, oid = rec
                revid = oid + tid
                rec = c.next()
                lrevid = self._metadata[revid][16:24]
                if lrevid < packtid:
                    self._oidqueue.append(revid, txn)
        finally:
            c.close()

    # tid is None if all we care about is that any object revision is present.
    def _packmark_has(self, oid, tid, txn):
        if tid is None:
            return self._packmark.has_key(oid)
        c = self._packmark.cursor(txn)
        try:
            try:
                c.set_both(oid, tid)
                return True
            except db.DBNotFoundError:
                return False
        finally:
            c.close()

    def _mark(self, txn, packtid):
        # Find the oids for all the objects reachable from the root, as of the
        # pack time.  To reduce the amount of in-core memory we need to do a
        # pack operation, we'll save the mark data in the packmark table.  The
        # oidqueue is a BerkeleyDB Queue that holds the list of object ids to
        # look at next, and by using this we don't need to keep an in-memory
        # dictionary.
        assert len(self._oidqueue) == 0
        # Quick exit for empty storages
        if not self._serials:
            return
        # Start with the root set, iterating over all reachable objects until
        # we've traversed the entire object tree.
        self._rootset(packtid, txn)
        rec = self._oidqueue.consume(txn)
        while rec:
            if self._stop:
                raise PackStop, 'stopped in _mark()'
            revid = rec[1]
            oid = revid[:8]
            tid = revid[8:]
            # See if this revision is already in the packmark
            if not self._packmark_has(oid, tid, txn):
                # BAW: We are more conservative than FileStorage here, since
                # any reference to an object keeps all the object references
                # alive.  FileStorage will collect individual object
                # revisions.  I think our way is fine since we'll eventually
                # collect everything incrementally anyway, and for Berkeley,
                # all object revisions add to the refcount total.
                self._packmark.put(oid, tid, txn=txn)
                # Say there's no root object (as is the case in some of the
                # unit tests), and we're looking up oid ZERO.  Then serial
                # will be None.
                if tid is not None:
                    lrevid = self._metadata[oid+tid][16:24]
                    # Now get the oids of all the objects referenced by this
                    # object revision
                    references = self._references.get(oid+lrevid)
                    if references:
                        for roid in splitrefs(references):
                            # Find the most recent object revision as of the
                            # timestamp of the under-focus revision.
                            rtid = self._findrev(roid, tid, txn)
                            self._oidqueue.append(roid+rtid, txn)
            # Pop the next oid off the queue and do it all again
            rec = self._oidqueue.consume(txn)
        assert len(self._oidqueue) == 0

    def _sweep(self, txn, packtid):
        c = self._serials.cursor(txn=txn)
        try:
            rec = c.first()
            while rec:
                if self._stop:
                    raise PackStop, 'stopped in _sweep()'
                oid = rec[0]
                rec = c.next()
                serial, tid = self._getSerialAndTid(oid)
                # If the current revision of this object newer than the
                # packtid, we'll ignore this object since we only care about
                # root reachability as of the pack time.
                if tid > packtid:
                    continue
                # Otherwise, if packmark (which knows about all the root
                # reachable objects) doesn't have a record for this guy, then
                # we can zap it.  Do so by appending to oidqueue.
                if not self._packmark_has(oid, None, txn):
                    self._delqueue.append(oid, txn)
        finally:
            c.close()
        # We're done with the mark table
        self._packmark.truncate(txn=txn)

    #
    # Iterator protocol
    #

    def iterator(self, start=None, stop=None):
        """Get a transactions iterator for the storage."""
        return _TransactionsIterator(self, start, stop)

    def _nexttxn(self, tid, first=False):
        self._lock_acquire()
        c = self._txnMetadata.cursor()
        try:
            # Berkeley raises DBNotFound exceptions (a.k.a. KeyError) to
            # signal that it's at the end of records.  Turn these into
            # IndexError to signal the end of iteration.
            try:
                if tid is None:
                    # We want the first transaction
                    rec = c.first()
                else:
                    # Get the next transaction after the specified one.
                    rec = c.set_range(tid)
            except KeyError:
                raise IndexError
            # We're now pointing at the tid >= the requested one.  For all
            # calls but the first one, tid will be the last transaction id we
            # returned, so we really want the next one.
            if not first:
                rec = c.next()
            if rec is None:
                raise IndexError
            tid, txnmeta = rec
            # Now unpack the necessary information.  Don't impedence match the
            # status flag (that's done by the caller).
            packtime = self._last_packtime()
            if tid <= packtime:
                packedp = True
            else:
                packedp = False
            user, desc, ext = self._unpack_txnmeta(txnmeta)
            return tid, packedp, user, desc, ext
        finally:
            if c:
                c.close()
            self._lock_release()



class _GetItemBase:
    def __getitem__(self, i):
        # Ignore the index, since we expect .next() will raise the appropriate
        # IndexError when the iterator is exhausted.
        return self.next()



class _TransactionsIterator(_GetItemBase):
    """Provide forward iteration through the transactions in a storage.

    Transactions *must* be accessed sequentially (e.g. with a for loop).
    """

    implements(IStorageIterator)

    def __init__(self, storage, start, stop):
        self._storage = storage
        self._tid = start
        self._stop = stop
        self._closed = False
        self._first = True
        self._iters = []

    # This allows us to pass an iterator as the `other' argument to
    # copyTransactionsFrom() in BaseStorage.  The advantage here is that we
    # can create the iterator manually, e.g. setting start and stop, and then
    # just let copyTransactionsFrom() do its thing.
    def iterator(self):
        return self

    def next(self):
        """Return the ith item in the sequence of transaction data.

        Items must be accessed sequentially, and are instances of
        RecordsIterator.  An IndexError will be raised after all of the items
        have been returned.
        """
        if self._closed:
            raise IOError, 'iterator is closed'
        # Let IndexErrors percolate up.
        tid, packedp, user, desc, ext = self._storage._nexttxn(
            self._tid, self._first)
        self._first = False
        # Did we reach the specified end?
        if self._stop is not None and tid > self._stop:
            raise IndexError
        self._tid = tid
        it = _RecordsIterator(self._storage, tid, packedp, user, desc, ext)
        self._iters.append(it)
        return it

    def close(self):
        for it in self._iters:
            it.close()
        self._closed = True



class _RecordsIterator(_GetItemBase):
    """Provide transaction meta-data and forward iteration through the
    transactions in a storage.

    Items *must* be accessed sequentially (e.g. with a for loop).
    """

    implements(ITransactionAttrs, ITransactionRecordIterator)

    # Transaction id as an 8-byte timestamp string
    tid = None

    # Transaction status code;
    #   ' ' -- normal
    #   'p' -- Transaction has been packed, and contains incomplete data.
    #
    # Note that undone ('u') and checkpoint transactions ('c') should not be
    # included.
    status = None

    # The standard transaction metadata
    user = None
    description = None
    _extension = None

    def __init__(self, storage, tid, packedp, user, desc, ext):
        self._storage = storage
        self.tid = tid
        # Impedence matching
        if packedp:
            self.status = 'p'
        else:
            self.status = ' '
        self.user = user
        self.description = desc
        self._extension = ext
        # BAW: touching the storage's private parts!
        self._table = self._storage._txnoids
        self._cursor = None
        self._rec = None

    def next(self):
        """Return the ith item in the sequence of record data.

        Items must be accessed sequentially, and are instances of Record.  An
        IndexError will be raised after all of the items have been
        returned.
        """
        # Initialize a txnoids cursor and set it to the start of the oids
        # touched by this transaction.  We do this here to ensure the cursor
        # is closed if there are any problems.  A hole in this approach is if
        # the client never exhausts the iterator.  Then I think we have a
        # problem because I don't think the environment can be closed if
        # there's an open cursor, but you also cannot close the cursor if the
        # environment is already closed (core dumps), so an __del__ doesn't
        # help a whole lot.
        try:
            if self._cursor is None:
                self._cursor = self._table.cursor()
                try:
                    self._rec = self._cursor.set(self.tid)
                except db.DBNotFoundError:
                    pass
            # Cursor exhausted?
            if self._rec is None:
                self.close()
                raise IndexError
            oid = self._rec[1]
            self._rec = self._cursor.next_dup()
            data, version, lrevid, refs = self._storage._loadSerialEx(
                oid, self.tid)
            return _Record(oid, self.tid, version, data, lrevid, refs)
        except:
            self.close()
            raise

    def close(self):
        if self._cursor:
            self._cursor.close()
            self._cursor = None



class _Record:

    implements(IDataRecord)

    # Object Id
    oid = None
    # Object serial number (i.e. revision id)
    serial = None
    # Version string
    version = None
    # Data pickle
    data = None
    # The pointer to the transaction containing the pickle data, if not None
    data_txn = None
    # The list of oids of objects referred to by this object
    refs = []

    def __init__(self, oid, serial, version, data, data_txn, refs):
        self.oid = oid
        self.serial = serial
        self.version = version
        self.data = data
        self.data_txn = data_txn
        self.refs = refs



class _Autopack(_WorkThread):
    NAME = 'autopacking'

    def __init__(self, storage, event, frequency, packtime, gcpack):
        _WorkThread.__init__(self, storage, event, frequency)
        self._packtime = packtime
        self._gcpack = gcpack
        # Bookkeeping
        self._lastgc = 0

    def _dowork(self):
        # Should we do a full gc pack this time?
        if self._gcpack <= 0:
            dofullgc = False
        else:
            v = (self._lastgc + 1) % self._gcpack
            self._lastgc = v
            dofullgc = not v
        # Run the full gc phase
        self._storage.pack(time.time() - self._packtime, dofullgc)
