##############################################################################
#
# Copyright (c) 2001, 2002 Zope Corporation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.1 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################
"""Persistence Interfaces

$Id$
"""
try:
    from zope.interface import Interface
    from zope.interface import Attribute
except ImportError:

    # just allow the module to compile if zope isn't available

    class Interface(object):
        pass

    def Attribute(s):
        return s

class IPersistent(Interface):
    """Python persistent interface

    A persistent object can be in one of several states:

    - Unsaved

      The object has been created but not saved in a data manager.

      In this state, the _p_changed attribute is non-None and false
      and the _p_jar attribute is None.

    - Saved

      The object has been saved and has not been changed since it was saved.

      In this state, the _p_changed attribute is non-None and false
      and the _p_jar attribute is set to a data manager.

    - Sticky

      This state is identical to the saved state except that the
      object cannot transition to the ghost state.  This is a special
      state used by C methods of persistent objects to make sure that
      state is not unloaded in the middle of computation.

      In this state, the _p_changed attribute is non-None and false
      and the _p_jar attribute is set to a data manager.

      There is no Python API for detecting whether an object is in the
      sticky state.

    - Changed

      The object has been changed.

      In this state, the _p_changed attribute is true
      and the _p_jar attribute is set to a data manager.

    - Ghost

      the object is in memory but its state has not been loaded from
      the database (or its state has been unloaded).  In this state,
      the object doesn't contain any application data.

      In this state, the _p_changed attribute is None, and the _p_jar
      attribute is set to the data manager from which the object was
      obtained.

    In all the above, _p_oid (the persistent object id) is set when
    _p_jar first gets set.

    The following state transactions are possible:

    - Unsaved -> Saved

      This transition occurs when an object is saved in the
      database.  This usually happens when an unsaved object is added
      to (e.g. as an attribute or item of) a saved (or changed) object
      and the transaction is committed.

    - Saved  -> Changed
      Sticky -> Changed

      This transition occurs when someone sets an attribute or sets
      _p_changed to a true value on a saved or sticky object.  When the
      transition occurs, the persistent object is required to call the
      register() method on its data manager, passing itself as the
      only argument.

    - Saved -> Sticky

      This transition occurs when C code marks the object as sticky to
      prevent its deactivation.

    - Saved -> Ghost

      This transition occurs when a saved object is deactivated or
      invalidated.  See discussion below.

    - Sticky -> Saved

      This transition occurs when C code unmarks the object as sticky to
      allow its deactivation.

    - Changed -> Saved

      This transition occurs when a transaction is committed.  After
      saving the state of a changed object during transaction commit,
      the data manager sets the object's _p_changed to a non-None false
      value.

    - Changed -> Ghost

      This transition occurs when a transaction is aborted.  All changed
      objects are invalidated by the data manager by an abort.

    - Ghost -> Saved

      This transition occurs when an attribute or operation of a ghost
      is accessed and the object's state is loaded from the database.

    Note that there is a separate C API that is not included here.
    The C API requires a specific data layout and defines the sticky
    state.


    About Invalidation, Deactivation and the Sticky & Ghost States

    The sticky state is intended to be a short-lived state, to prevent
    an object's state from being discarded while we're in C routines.  It
    is an error to invalidate an object in the sticky state.

    Deactivation is a request that an object discard its state (become
    a ghost).  Deactivation is an optimization, and a request to
    deactivate may be ignored.  There are two equivalent ways to
    request deactivation:

          - call _p_deactivate()
          - set _p_changed to None

    There is one way to invalidate an object:  delete its _p_changed
    attribute.  This cannot be ignored, and is used when semantics
    require invalidation.  Normally, an invalidated object transitions
    to the ghost state.  However, some objects cannot be ghosts.  When
    these objects are invalidated, they immediately reload their state
    from their data manager, and are then in the saved state.

    """

    _p_jar = Attribute(
        """The data manager for the object.

        The data manager implements the IPersistentDataManager interface.
        If there is no data manager, then this is None.
        """)

    _p_oid = Attribute(
        """The object id.

        It is up to the data manager to assign this.
        The special value None is reserved to indicate that an object
        id has not been assigned.  Non-None object ids must be hashable
        and totally ordered.
        """)

    _p_changed = Attribute(
        """The persistent state of the object

        This is one of:

        None -- The object is a ghost.

        false but not None -- The object is saved (or has never been saved).

        true -- The object has been modified since it was last saved.

        The object state may be changed by assigning or deleting this
        attribute; however, assigning None is ignored if the object is
        not in the saved state, and may be ignored even if the object is
        in the saved state.

        Note that an object can transition to the changed state only if
        it has a data manager.  When such a state change occurs, the
        'register' method of the data manager must be called, passing the
        persistent object.

        Deleting this attribute forces invalidation independent of
        existing state, although it is an error if the sticky state is
        current.
        """)

    _p_serial = Attribute(
        """The object serial number.

        This member is used by the data manager to distiguish distinct
        revisions of a given persistent object.

        This is an 8-byte string (not Unicode).
        """)

    def __getstate__():
        """Get the object data.

        The state should not include persistent attributes ("_p_name").
        The result must be picklable.
        """

    def __setstate__(state):
        """Set the object data.
        """

    def _p_activate():
        """Activate the object.

        Change the object to the saved state if it is a ghost.
        """

    def _p_deactivate():
        """Deactivate the object.

        Possibly change an object in the saved state to the
        ghost state.  It may not be possible to make some persistent
        objects ghosts, and, for optimization reasons, the implementation
        may choose to keep an object in the saved state.
        """

class IPersistentNoReadConflicts(IPersistent):
    def _p_independent():
        """Hook for subclasses to prevent read conflict errors.

        A specific persistent object type can define this method and
        have it return true if the data manager should ignore read
        conflicts for this object.
        """

# XXX TODO:  document conflict resolution.

class IPersistentDataManager(Interface):
    """Provide services for managing persistent state.

    This interface is used by a persistent object to interact with its
    data manager in the context of a transaction.
    """

    def setstate(object):
        """Load the state for the given object.

        The object should be in the ghost state.
        The object's state will be set and the object will end up
        in the saved state.

        The object must provide the IPersistent interface.
        """

    def register(object):
        """Register an IPersistent with the current transaction.

        This method must be called when the object transitions to
        the changed state.
        """

    def mtime(object):
        """Return the modification time of the object.

        The modification time may not be known, in which case None
        is returned.  If non-None, the return value is the kind of
        timestamp supplied by Python's time.time().
        """

# XXX Should we keep the following?  Doesn't seem too useful, and
# XXX we don't actually implement this interface (e.g., we have no
# XXX .statistics() method).

class ICache(Interface):
    """In-memory object cache.

    The cache serves two purposes.  It peforms pointer swizzling, and
    it keeps a bounded set of recently used but otherwise unreferenced
    in objects to avoid the cost of re-loading them.

    Pointer swizzling is the process of converting between persistent
    object ids and Python object ids.  When a persistent object is
    serialized, its references to other persistent objects are
    represented as persitent object ids (oids).  When the object is
    unserialized, the oids are converted into references to Python
    objects.  If several different serialized objects refer to the
    same object, they must all refer to the same object when they are
    unserialized.

    A cache stores persistent objects, but it treats ghost objects and
    non-ghost or active objects differently.  It has weak references
    to ghost objects, because ghost objects are only stored in the
    cache to satisfy the pointer swizzling requirement.  It has strong
    references to active objects, because it caches some number of
    them even if they are unreferenced.

    The cache keeps some number of recently used but otherwise
    unreferenced objects in memory.  We assume that there is a good
    chance the object will be used again soon, so keeping it memory
    avoids the cost of recreating the object.

    An ICache implementation is intended for use by an
    IPersistentDataManager.
    """

    def get(oid):
        """Return the object from the cache or None."""

    def set(oid, obj):
        """Store obj in the cache under oid.

        obj must implement IPersistent
        """

    def remove(oid):
        """Remove oid from the cache if it exists."""

    def invalidate(oids):
        """Make all of the objects in oids ghosts.

        `oids` is an iterable object that yields oids.

        The cache must attempt to change each object to a ghost by
        calling _p_deactivate().

        If an oid is not in the cache, ignore it.
        """

    def clear():
        """Invalidate all the active objects."""

    def activate(oid):
        """Notification that object oid is now active.

        The caller is notifying the cache of a state change.

        Raises LookupError if oid is not in cache.
        """

    def shrink():
        """Remove excess active objects from the cache."""

    def statistics():
        """Return dictionary of statistics about cache size.

        Contains at least the following keys:
        active -- number of active objects
        ghosts -- number of ghost objects
        """
