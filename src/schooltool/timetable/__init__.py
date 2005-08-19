#
# SchoolTool - common information systems platform for school administration
# Copyright (c) 2003 Shuttleworth Foundation
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
"""
Timetabling in SchoolTool
=========================

Note: timetabling here refers to the management of timetables of resources,
persons and groups.  It is not related to automatic timetable generation
or constraint solving.

Every application object (person, group or a resource) can have a number of
timetables.  First, the timetables can vary in the timetable schema (e.g. a
school may have a 4-day rotating timetable for classes, and then another
timetable for events that recur weekly). Second, there are separate timetables
for different time periods (terms).

Global containers
-----------------

A list of all defined timetable schemas is available in app['ttschemas']
(see ISchoolToolApplication, ITimetableSchemaContainer).

A list of all defined terms is available in app['terms'] (see
ISchoolToolApplication, ITermContainer).

Every timetable is defined for a given schema and a given term.  A tuple
consisting of the schema's ID and the terms's ID is often refered to as a
timetable's key.

Objects that have timetables
----------------------------

An object that has (or may have) timetables implements ITimetables.

An object's composite timetable is derived by combining the object's
timetable with composite timetables of other objects, acquired by
calling subscribers of ITimetableSource interface.

Timetables
----------

A timetable consists of several days, each of which has several periods (the
sets of periods for different days may be different), and each period may have
zero or more timetable activities (two or more activities represent scheduling
conflicts).  See ITimetable, ITimetableDay, ITimetableActivity.

A timetable model describes the mapping between timetable days and calendar
days, and also the mapping between period IDs and time of the day.  Currently
SchoolTool has two kinds of timetable models:

  - Sequential days model may jump over calendar days if they are not school
    days.  For example, if July 3 was timetable day 3, and July 4 is a holiday,
    then July 5 will be timetable day 4.

  - Weekly model maps week days directly to timetable days, that is, Monday is
    always timetable day 1, and sunday is always timetable day 7.

It is possible to define additional models.  See ITimetableModel.

Example of a timetable::

    day_id:     Monday      Tuesday     ... Friday
    period_ids: 8:00-8:45   8:00-8:45   ... 8:00-8:40
                9:00-9:45   9:00-9:45   ... 8:55-9:35
                10:00-10:45 10:00-10:45 ... 10:50-10:30
                ...         ...         ... ...
                17:00-17:45 17:00-17:45 ... 16:15-16:55

    For this particular timetable, timetable days are named after week days
    (but note that there is no Saturday or Sunday because there are no classes
    on those days), periods are named after time periods, and the set of
    periods is the same for all days except for Friday.  This timetable
    will be used with a weekly timetable model.

Another example:

    day_id:     Day 1  Day 2 ... Day 10
    period_ids: 8:00   8:00  ... 8:00
                9:00   9:00  ... 9:00
                10:00  10:00 ... 10:00
                ...    ...   ... ...
                17:00  17:00 ... 17:00

    For this particular timetable, timetable days are named sequentially,
    periods are named after time periods (but only include the starting time),
    and the set of periods is the same for all days.  This timetable will
    be used with a sequential timetable model.

Another example:

    day_id:     Day 1  Day 2 ... Day 4
    period_ids: A      B     ... D
                B      C     ... A
                C      D     ... B
                D      A     ... C

    For this particular timetable, timetable days are named sequentially,
    periods are named arbitrarily, and the set of periods is the same for all
    days, but listed in a different order.  This timetable will be used with a
    sequential timetable model.

Timetable schemas
-----------------

A timetable schema is like a timetable that has no activities and no exeptions.
You can create an empty timetable by calling the createTimetable method of a
schema.  See ITimetableSchema, ITimetableSchemaDay.

Terms
-----

A term defines a range in time (e.g. September 1 to December 31, 2004) and for
every day within that range it defines whether that day is a schoolday or a
holiday.


$Id$
"""

import datetime
from sets import Set, ImmutableSet

import zope.event
from persistent import Persistent
from persistent.list import PersistentList
from persistent.dict import PersistentDict
from zope.component import provideAdapter, adapts
from zope.interface import implements
from zope.interface import directlyProvides

from zope.app import zapi
from zope.app.annotation.interfaces import IAttributeAnnotatable
from zope.app.annotation.interfaces import IAnnotatable, IAnnotations
from zope.app.container.btree import BTreeContainer
from zope.app.container.contained import Contained
from zope.app.location.interfaces import ILocation
from zope.app.location.traversing import LocationPhysicallyLocatable
from zope.app.traversing.api import getPath

from schooltool.app.cal import CalendarEvent
from schooltool.calendar.simple import ImmutableCalendar

from schooltool.timetable.interfaces import ITimetableSchema
from schooltool.timetable.interfaces import ITimetableSchemaDay
from schooltool.timetable.interfaces import ITimetableSchemaWrite
from schooltool.timetable.interfaces import ITimetable, ITimetableWrite
from schooltool.timetable.interfaces import ITimetableDay, ITimetableDayWrite
from schooltool.timetable.interfaces import ITimetableDict
from schooltool.timetable.interfaces import ITimetableActivity
from schooltool.timetable.interfaces import ITimetableActivityAddedEvent
from schooltool.timetable.interfaces import ITimetableActivityRemovedEvent
from schooltool.timetable.interfaces import ITimetableReplacedEvent
from schooltool.timetable.interfaces import ISchooldayPeriod
from schooltool.timetable.interfaces import ISchooldayTemplate
from schooltool.timetable.interfaces import ISchooldayTemplateWrite
from schooltool.timetable.interfaces import ITimetables
from schooltool.timetable.interfaces import ITimetableSchemaContainer
from schooltool.timetable.interfaces import ITermContainer
from schooltool.timetable.interfaces import ITermWrite, ITerm
from schooltool.timetable.interfaces import ITimetableSource
from schooltool.timetable.interfaces import Unchanged
from schooltool.timetable.interfaces import IDateRange
from schooltool.app.app import getSchoolToolApplication

# Imports for ZODB compatibility
from schooltool.timetable.model import BaseTimetableModel
from schooltool.timetable.model import WeeklyTimetableModel
from schooltool.timetable.model import SequentialDaysTimetableModel
from schooltool.timetable.model import SequentialDayIdBasedTimetableModel
from schooltool.timetable.model import TimetableCalendarEvent

__metaclass__ = type



#
# Date ranges and terms
#

class DateRange:

    implements(IDateRange)

    def __init__(self, first, last):
        self.first = first
        self.last = last
        if last < first:
            # import timemachine
            raise ValueError("Last date %r less than first date %r" %
                             (last, first))

    def __iter__(self):
        date = self.first
        while date <= self.last:
            yield date
            date += datetime.date.resolution

    def __len__(self):
        return (self.last - self.first).days + 1

    def __contains__(self, date):
        return self.first <= date <= self.last


class Term(DateRange, Persistent):

    implements(ITerm, ITermWrite, ILocation)

    __name__ = None
    __parent__ = None

    def __init__(self, title, first, last):
        DateRange.__init__(self, first, last)
        self.title = title
        self._schooldays = Set()

    def _validate(self, date):
        if not date in self:
            raise ValueError("Date %r not in term [%r, %r]" %
                             (date, self.first, self.last))

    def isSchoolday(self, date):
        self._validate(date)
        if date in self._schooldays:
            return True
        return False

    def add(self, date):
        self._validate(date)
        self._schooldays.add(date)
        self._schooldays = self._schooldays  # persistence

    def remove(self, date):
        self._validate(date)
        self._schooldays.remove(date)
        self._schooldays = self._schooldays  # persistence

    def addWeekdays(self, *weekdays):
        for date in self:
            if date.weekday() in weekdays:
                self.add(date)

    def removeWeekdays(self, *weekdays):
        for date in self:
            if date.weekday() in weekdays and self.isSchoolday(date):
                self.remove(date)

    def toggleWeekdays(self, *weekdays):
        for date in self:
            if date.weekday() in weekdays:
                if self.isSchoolday(date):
                    self.remove(date)
                else:
                    self.add(date)

    def reset(self, first, last):
        if last < first:
            # import timemachine
            raise ValueError("Last date %r less than first date %r" %
                             (last, first))
        self.first = first
        self.last = last
        self._schooldays.clear()


#
# Timetabling
#

class TimetableSchema(Persistent, Contained):

    implements(ITimetableSchema, ITimetableSchemaWrite)

    def __init__(self, day_ids, title=None, model=None):
        """Create a new empty timetable schema.

        day_ids is a sequence of the day ids of this timetable.

        The caller must then assign a TimetableDay for each day ID and
        set the model before trying to use the timetable.
        """
        self.title = title
        if self.title is None:
            self.title = "Schema"
        self.day_ids = day_ids
        self.days = PersistentDict()
        self.model = model

    def keys(self):
        return list(self.day_ids)

    def items(self):
        return [(day, self.days[day]) for day in self.day_ids]

    def __getitem__(self, key):
        return self.days[key]

    def __setitem__(self, key, value):
        if not ITimetableSchemaDay.providedBy(value):
            raise TypeError("Timetable schema can only contain"
                            " ITimetableSchemaDay objects (got %r)" % (value,))
        elif key not in self.day_ids:
            raise ValueError("Key %r not in day_ids %r" % (key, self.day_ids))
        self.days[key] = value

    def createTimetable(self):
        other = Timetable(self.day_ids)
        other.model = self.model
        for day_id in self.day_ids:
            other[day_id] = TimetableDay(self[day_id].periods)
        return other

    def __eq__(self, other):
        if ITimetableSchema.providedBy(other):
            return (self.items() == other.items()
                    and self.model == other.model)
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)


class TimetableSchemaDay(Persistent):

    implements(ITimetableSchemaDay)

    def __init__(self, periods=()):
        self.periods = periods

    def keys(self):
        return self.periods

    def items(self):
        return [(period, Set()) for period in self.periods]

    def __getitem__(self, period):
        if period not in self.periods:
            raise KeyError(period)
        return Set()

    def __eq__(self, other):
        if ITimetableSchemaDay.providedBy(other):
            return self.periods == other.periods
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)


class Timetable(Persistent):

    implements(ITimetable, ITimetableWrite)

    __name__ = None
    __parent__ = None

    def __init__(self, day_ids):
        """Create a new empty timetable.

        day_ids is a sequence of the day ids of this timetable.

        The caller must then assign a TimetableDay for each day ID and
        set the model before trying to use the timetable.
        """
        self.day_ids = day_ids
        self.days = PersistentDict()
        self.model = None

    def keys(self):
        return list(self.day_ids)

    def items(self):
        return [(day, self.days[day]) for day in self.day_ids]

    def __repr__(self):
        return '<Timetable: %s, %s, %s>' % (self.day_ids, dict(self.days),
                                            self.model)

    def __getitem__(self, key):
        return self.days[key]

    def __setitem__(self, key, value):
        if not ITimetableDay.providedBy(value):
            raise TypeError("Timetable can only contain ITimetableDay objects "
                            "(got %r)" % (value,))
        elif key not in self.day_ids:
            raise ValueError("Key %r not in day_ids %r" % (key, self.day_ids))
        elif value.timetable is not None:
            raise ValueError("%r already belongs to timetable %r"
                             % (value, value.timetable))
        value.timetable = self
        value.day_id = key
        self.days[key] = value

    def clear(self, send_events=True):
        for day in self.days.itervalues():
            for period in day.periods:
                day.clear(period, send_events)

    def update(self, other):
        if self.cloneEmpty() != other.cloneEmpty():
            raise ValueError("Timetables have different schemas")
        for day, period, activity in other.itercontent():
            self[day].add(period, activity, False)

    def cloneEmpty(self):
        other = Timetable(self.day_ids)
        other.model = self.model
        for day_id in self.day_ids:
            other[day_id] = TimetableDay(self[day_id].periods)
        return other

    def __eq__(self, other):
        if ITimetable.providedBy(other):
            return (self.items() == other.items()
                    and self.model == other.model)
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def itercontent(self):
        for day_id in self.day_ids:
            for period_id, iactivities in self.days[day_id].items():
                for activity in iactivities:
                    yield (day_id, period_id, activity)


class TimetableDay(Persistent):

    implements(ITimetableDay, ITimetableDayWrite)

    timetable = None
    day_id = None

    def __init__(self, periods=()):
        self.periods = periods
        self.activities = PersistentDict()
        for p in periods:
            self.activities[p] = Set() # MaybePersistentKeysSet()

    def keys(self):
        return self.periods

    def items(self):
        return [(period, self.activities[period]) for period in self.periods]

    def __getitem__(self, period):
        return self.activities[period]

    def clear(self, period, send_events=True):
        if period not in self.periods:
            raise ValueError("Key %r not in periods %r" % (period,
                                                           self.periods))
        activities = [act.replace(timetable=self.timetable)
                      for act in self.activities[period]]
        self.activities[period].clear()
        if send_events:
            for act in activities:
                ev = TimetableActivityRemovedEvent(act, self.day_id, period)
                zope.event.notify(ev)

    def add(self, period, activity, send_events=True):
        if period not in self.periods:
            raise ValueError("Key %r not in periods %r" % (period,
                                                           self.periods))
        if not ITimetableActivity.providedBy(activity):
            raise TypeError("TimetableDay can only contain ITimetableActivity"
                            " objects (got %r)" % (activity, ))
        if activity.timetable is None:
            activity = activity.replace(timetable=self.timetable)
        self.activities[period].add(activity)

        if send_events:
            activity = activity.replace(timetable=self.timetable)
            event = TimetableActivityAddedEvent(activity, self.day_id, period)
            zope.event.notify(event)

    def remove(self, period, value, send_events=True):
        if period not in self.periods:
            raise ValueError("Key %r not in periods %r"
                             % (period, self.periods))
        self.activities[period].remove(value)
        if send_events:
            activity = value.replace(timetable=self.timetable)
            ev = TimetableActivityRemovedEvent(activity, self.day_id, period)
            zope.event.notify(ev)

    def __eq__(self, other):
        if not ITimetableDay.providedBy(other):
            return False
        if self.periods != other.periods:
            return False
        for period in self.periods:
            if Set(self.activities[period]) != Set(other.activities[period]):
                return False
        return True

    def __ne__(self, other):
        return not self.__eq__(other)


class TimetableActivity:
    """Timetable activity.

    Instances are immutable.

    Equivalent timetable activities must compare and hash equally after
    pickling and unpickling.
    """

    implements(ITimetableActivity)

    def __init__(self, title=None, owner=None, resources=(), timetable=None):
        self._title = title
        self._owner = owner
        self._resources = ImmutableSet(resources)
        self._timetable = timetable

    title = property(lambda self: self._title)
    owner = property(lambda self: self._owner)
    resources = property(lambda self: self._resources)
    timetable = property(lambda self: self._timetable)

    def __repr__(self):
        return ("TimetableActivity(%r, %r, %r, %r)"
                % (self.title, self.owner, self.resources, self.timetable))

    def __eq__(self, other):
        # Is it really a good idea to ignore self.timetable?
        # On further thought it does not matter -- we never compare activities
        # that come from timetables with different keys.
        if ITimetableActivity.providedBy(other):
            return (self.title == other.title and self.owner == other.owner
                    and self.resources == other.resources)
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return hash((self.title, self.owner, self.resources))

    def replace(self, title=Unchanged, owner=Unchanged,
                      resources=Unchanged, timetable=Unchanged):
        if title is Unchanged: title = self.title
        if owner is Unchanged: owner = self.owner
        if resources is Unchanged: resources = self.resources
        if timetable is Unchanged: timetable = self.timetable
        return TimetableActivity(title=title, owner=owner,
                                 resources=resources, timetable=timetable)


class TimetableReplacedEvent:

    implements(ITimetableReplacedEvent)

    def __init__(self, object, key, old_timetable, new_timetable):
        self.object = object
        self.key = key
        self.old_timetable = old_timetable
        self.new_timetable = new_timetable

    def __unicode__(self):
        return ("TimetableReplacedEvent object=%s (%s) key=%s"
                % (getPath(self.object), self.object.title, self.key))


class TimetableActivityEvent:

    def __init__(self, activity, day_id, period_id):
        self.activity = activity
        self.day_id = day_id
        self.period_id = period_id


class TimetableActivityAddedEvent(TimetableActivityEvent):
    implements(ITimetableActivityAddedEvent)


class TimetableActivityRemovedEvent(TimetableActivityEvent):
    implements(ITimetableActivityRemovedEvent)


class SchooldayPeriod:

    implements(ISchooldayPeriod)

    def __init__(self, title, tstart, duration):
        self.title = title
        self.tstart = tstart
        self.duration = duration

    def __eq__(self, other):
        if not ISchooldayPeriod.providedBy(other):
            return False
        return (self.title == other.title and
                self.tstart == other.tstart and
                self.duration == other.duration)

    def __ne__(self, other):
        return not (self == other)

    def __hash__(self):
        return hash((self.title, self.tstart, self.duration))


class SchooldayTemplate:

    # TODO: ideally, schoolday template should be an object that takes
    # a date and a period id and returns a schoolday period.  This way
    # we would get rid of the bizzare weekday -> schoolday template
    # mapping in the timetable model.

    implements(ISchooldayTemplate, ISchooldayTemplateWrite)

    def __init__(self):
        self.events = Set()

    def __iter__(self):
        return iter(self.events)

    def add(self, obj):
        if not ISchooldayPeriod.providedBy(obj):
            raise TypeError("SchooldayTemplate can only contain "
                            "ISchooldayPeriods (got %r)" % (obj,))
        self.events.add(obj)

    def remove(self, obj):
        self.events.remove(obj)

    def __eq__(self, other):
        if isinstance(other, SchooldayTemplate):
            return self.events == other.events
        else:
            return False

    def __ne__(self, other):
        return not self == other



#
#  Things for integrating timetabling into the core code.
#

class TimetableDict(PersistentDict):

    implements(ILocation, ITimetableDict)

    __name__ = 'timetables'
    __parent__ = None

    def __setitem__(self, key, value):
        assert ITimetable.providedBy(value)
        keys = key.split(".")
        if len(keys) != 2 or not keys[0] or not keys[1]:
            raise ValueError("The key should be composed of a term id and a"
                             " schema id separated with a . (got %r)" % key)
        old_value = self.get(key)
        if old_value is not None:
            old_value.__parent__ = None
            old_value.__name__ = None
        value.__parent__ = self
        value.__name__ = key
        PersistentDict.__setitem__(self, key, value)
        event = TimetableReplacedEvent(self.__parent__, key, old_value, value)
        zope.event.notify(event)

    def __delitem__(self, key):
        value = self[key]
        value.__parent__ = None
        value.__name__ = None
        PersistentDict.__delitem__(self, key)
        zope.event.notify(
            TimetableReplacedEvent(self.__parent__, key, value, None))

    def clear(self):
        for key, value in self.items():
            del self[key]

    def _not_implemented(self, *args, **kw):
        raise NotImplementedError(
                "This method is not implemented in TimetableDict.  Feel free"
                " to implement it, if you need it, but make sure the semantics"
                " of changes are preserved (i.e. update __parent__ and"
                " __name__, and send out events when needed).")

    update = _not_implemented
    setdefault = _not_implemented
    pop = _not_implemented
    popitem = _not_implemented


TIMETABLES_KEY = 'schooltool.timetable.timetables'

class TimetablesAdapter(object):
    """This adapter adapts any annotatable object to be timetabled.

    It provides ``ITimetables`` with the default semantics of
    timetable composition by membership and logic for searching for
    ``ICompositeTimetableProvider`` facets.
    """
    implements(ITimetables)
    adapts(IAnnotatable)

    def __init__(self, context):
        self.object = context
        annotations = IAnnotations(context)
        self.timetables = annotations.get(TIMETABLES_KEY)
        if self.timetables is None:
            self.timetables = annotations[TIMETABLES_KEY] = TimetableDict()
            self.timetables.__parent__ = context

    def getCompositeTimetable(self, period_id, schema_id):
        timetables = []
        # Get the timetables from timetable source subscription adapters
        for adapter in zapi.subscribers((self, ), ITimetableSource):
            tt = adapter.getTimetable(period_id, schema_id)
            if tt is not None:
                timetables.append(tt)

        # Add the individual timetable to the composite
        try:
            timetables.append(self.timetables["%s.%s" % (period_id, schema_id)])
        except KeyError:
            pass

        if not timetables:
            return None

        # Aggregate results
        result = timetables[0].cloneEmpty()
        for tt in timetables:
            result.update(tt)

        parent = TimetableDict()
        parent.__parent__ = self.object
        parent.__name__ = 'composite-timetables'
        parent[".".join((period_id, schema_id))] = result

        return result

    def listCompositeTimetables(self):
        keys = Set([tuple(k.split(".")) for k in self.timetables.keys()])
        for adapter in zapi.subscribers((self, ), ITimetableSource):
            keys |= adapter.listTimetables()
        return keys

    def makeTimetableCalendar(self):
        events = []
        terms = getSchoolToolApplication()["terms"]
        for term_id, schema_id in self.listCompositeTimetables():
            term = terms[term_id]
            tt = self.getCompositeTimetable(term_id, schema_id)
            cal = tt.model.createCalendar(term, tt)
            events += list(cal)
        result = ImmutableCalendar(events)
        # Parent is needed so that we can find out the owner of this calendar.
        directlyProvides(result, ILocation)
        result.__parent__ = self.object
        result.__name__ = 'timetable-calendar'
        return result


class TimetableSchemaContainer(BTreeContainer):

    implements(ITimetableSchemaContainer, IAttributeAnnotatable)

    _default_id = None

    def _set_default_id(self, new_id):
        if new_id is not None and new_id not in self:
            raise ValueError("Timetable schema %r does not exist" % new_id)
        self._default_id = new_id

    default_id = property(lambda self: self._default_id, _set_default_id)

    def __setitem__(self, schema_id, ttschema):
        assert ITimetableSchema.providedBy(ttschema)
        if self.has_key(schema_id):
            BTreeContainer.__delitem__(self, schema_id)
        BTreeContainer.__setitem__(self, schema_id, ttschema)
        if self.default_id is None:
            self.default_id = schema_id

    def __delitem__(self, schema_id):
        BTreeContainer.__delitem__(self, schema_id)
        if schema_id == self.default_id:
            self.default_id = None

    def getDefault(self):
        return self[self.default_id]


class TermContainer(BTreeContainer):

    implements(ITermContainer, IAttributeAnnotatable)


def getTermForDate(date):
    """Find the term that contains `date`.

    Returns None if `date` falls outside all terms.
    """
    terms = getSchoolToolApplication()["terms"]
    for term in terms.values():
        if date in term:
            return term
    else:
        return None


def getNextTermForDate(date):
    """Find the term that contains `date`, or the next one.

    If there is a term that contains `date`, it is returned.  Otherwise, the
    first term that starts after `date` is returned.  If there are none,
    the last term that ended before `date` is returned.

    Returns None if there are no terms.
    """
    terms = getSchoolToolApplication()["terms"]
    before, after = [], []
    for term in terms.values():
        if date in term:
            return term
        if date > term.last:
            before.append((term.last, term))
        if date < term.first:
            after.append((term.first, term))
    if after:
        return after[0][1]
        return min(after)[1]
    if before:
        return max(before)[1]
    return None


def getPeriodsForDay(date):
    """Return a list of timetable periods defined for `date`.

    This function uses the default timetable schema and the appropriate time
    period for `date`.

    Returns a list of ISchooldayPeriod objects.

    Returns an empty list if there are no periods defined for `date` (e.g.
    if there is no default timetable schema, or `date` falls outside all
    time periods, or it happens to be a holiday).
    """
    schooldays = getTermForDate(date)
    ttcontainer = getSchoolToolApplication()['ttschemas']
    if ttcontainer.default_id is None or schooldays is None:
        return []
    ttschema = ttcontainer.getDefault()
    return ttschema.model.periodsInDay(schooldays, ttschema, date)


def addToApplication(event):
    event.object['terms'] = TermContainer()
    event.object['ttschemas'] = TimetableSchemaContainer()


def registerTestSetup():
    from schooltool.testing import registry

    def addTermAndTTSchemasContainer(app):
        app['terms'] = TermContainer()
        app['ttschemas'] = TimetableSchemaContainer()

    registry.register('ApplicationContainers', addTermAndTTSchemasContainer)

registerTestSetup()
del registerTestSetup


