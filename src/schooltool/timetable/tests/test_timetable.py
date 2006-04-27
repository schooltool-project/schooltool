#
# SchoolTool - common information systems platform for school administration
# Copyright (c) 2005 Shuttleworth Foundation
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
Unit tests for the schooltool.timetable module.

$Id$
"""

import unittest
from sets import Set
from datetime import time, timedelta, datetime, date

from persistent import Persistent
from zope.app.testing import setup
from zope.interface.verify import verifyObject
from zope.interface import implements, directlyProvides
from zope.traversing.api import getPath
from zope.app.testing.placelesssetup import PlacelessSetup
from zope.app.testing import ztapi
from zope.annotation.interfaces import IAttributeAnnotatable
from zope.location.interfaces import ILocation
from zope.testing import doctest

from schooltool import timetable
from schooltool.timetable.interfaces import ITimetables
from schooltool.timetable.interfaces import ICompositeTimetables
from schooltool.timetable.interfaces import ITimetable, ITimetableActivity
from schooltool.timetable.interfaces import IOwnTimetables
from schooltool.relationship import RelationshipProperty
from schooltool.app.membership import URIGroup, URIMember, URIMembership

from schooltool.testing import setup as stsetup
from schooltool.testing.util import NiceDiffsMixin
from schooltool.testing.util import EqualsSortedMixin
from schooltool.term.tests.test_term import TermStub

class ActivityStub(object):

    implements(ITimetableActivity)
    replaced = False
    timetable = None

    def replace(self, **kwargs):
        self.replaced = True
        if 'timetable' in kwargs:
            self.timetable = kwargs['timetable']
        return self


class TestTimetable(unittest.TestCase):

    def test_interface(self):
        from schooltool.timetable import Timetable
        from schooltool.timetable.interfaces import ITimetable, ITimetableWrite

        t = Timetable(('1', '2'))
        verifyObject(ITimetable, t)
        verifyObject(ITimetableWrite, t)
        verifyObject(ILocation, t)

    def test_keys(self):
        from schooltool.timetable import Timetable
        days = ('Mo', 'Tu', 'We', 'Th', 'Fr')
        t = Timetable(days)
        self.assertEqual(t.keys(), list(days))

    def test_getitem_setitem(self):
        from schooltool.timetable import Timetable
        from schooltool.timetable.interfaces import ITimetableDay

        days = ('Mo', 'Tu', 'We', 'Th', 'Fr')
        t = Timetable(days)
        self.assertRaises(KeyError, t.__getitem__, "Mo")
        self.assertRaises(KeyError, t.__getitem__, "What!?")

        class DayStub:
            implements(ITimetableDay)
            timetable = None
            day_id = None

        self.assertRaises(TypeError, t.__setitem__, "Mo", object())
        self.assertRaises(ValueError, t.__setitem__, "Mon", DayStub())
        monday = DayStub()
        t["Mo"] = monday
        self.assertEqual(t["Mo"], monday)
        self.assert_(monday.timetable is t)
        self.assert_(monday.day_id is 'Mo')

    def test_items(self):
        from schooltool.timetable import Timetable
        from schooltool.timetable.interfaces import ITimetableDay

        days = ('Day 1', 'Day 2', 'Day 3')
        t = Timetable(days)

        class DayStub:
            implements(ITimetableDay)
            timetable = None

        t["Day 1"] = day1 = DayStub()
        t["Day 2"] = day2 = DayStub()
        self.assertRaises(KeyError, t.items)
        t["Day 3"] = day3 = DayStub()
        self.assertEqual(t.items(),
                         [("Day 1", day1), ("Day 2", day2), ("Day 3", day3)])

    def createTimetable(self):
        from schooltool.timetable import Timetable, TimetableDay
        days = ('A', 'B')
        periods = ('Green', 'Blue')
        tt = Timetable(days)
        tt["A"] = TimetableDay(periods)
        tt["B"] = TimetableDay(periods)
        return tt

    def test_clear(self):
        from schooltool.timetable import TimetableActivity
        tt = self.createTimetable()
        english = TimetableActivity("English")
        math = TimetableActivity("Math")
        bio = TimetableActivity("Biology")
        tt["A"].add("Green", english)
        tt["A"].add("Blue", math)
        tt["B"].add("Green", bio)

        tt.clear()

        empty_tt = self.createTimetable()
        self.assertEqual(tt, empty_tt)

    def test_update(self):
        from schooltool.timetable import Timetable, TimetableDay
        from schooltool.timetable import TimetableActivity

        tt = self.createTimetable()
        english = TimetableActivity("English")
        math = TimetableActivity("Math")
        bio = TimetableActivity("Biology")
        tt["A"].add("Green", english)
        tt["A"].add("Blue", math)
        tt["B"].add("Green", bio)

        tt2 = self.createTimetable()
        french = TimetableActivity("French")
        math2 = TimetableActivity("Math 2")
        geo = TimetableActivity("Geography")
        tt2["A"].add("Green", french)
        tt2["A"].add("Blue", math2)
        tt2["B"].add("Blue", geo)

        tt.update(tt2)

        items = [(p, Set(i)) for p, i in tt["A"].items()]
        self.assertEqual(items, [("Green", Set([english, french])),
                                 ("Blue", Set([math, math2]))])

        items = [(p, Set(i)) for p, i in tt["B"].items()]
        self.assertEqual(items, [("Green", Set([bio])),
                                 ("Blue", Set([geo]))])

        tt3 = Timetable(("A", ))
        tt3["A"] = TimetableDay(('Green', 'Blue'))
        self.assertRaises(ValueError, tt.update, tt3)

    def test_cloneEmpty(self):
        from schooltool.timetable import TimetableActivity

        tt = self.createTimetable()
        english = TimetableActivity("English")
        math = TimetableActivity("Math")
        bio = TimetableActivity("Biology")
        tt["A"].add("Green", english)
        tt["A"].add("Blue", math)
        tt["B"].add("Green", bio)
        tt["B"].homeroom_period_ids = ["Blue"]
        tt.model = object()
        tt.timezone = 'Foo/Bar'

        tt2 = tt.cloneEmpty()
        self.assert_(tt2 is not tt)
        self.assertEquals(tt.day_ids, tt2.day_ids)
        self.assert_(tt.model is tt2.model)
        self.assert_(tt.timezone is tt2.timezone)
        for day_id in tt2.day_ids:
            day = tt[day_id]
            day2 = tt2[day_id]
            self.assert_(day is not day2)
            self.assertEquals(day.periods, day2.periods)
            self.assertEquals(day.homeroom_period_ids, day2.homeroom_period_ids)
            for period in day2.periods:
                self.assertEquals(list(day2[period]), [])

    def testComparison(self):
        from schooltool.timetable import TimetableActivity

        model = object()
        tt = self.createTimetable()
        english = TimetableActivity("English")
        math = TimetableActivity("Math")
        bio = TimetableActivity("Biology")
        tt["A"].add("Green", english)
        tt["A"].add("Blue", math)
        tt["B"].add("Green", bio)

        self.assertEquals(tt, tt)
        self.assertNotEquals(tt, None)

        tt2 = self.createTimetable()
        self.assertNotEquals(tt, tt2)

        tt2["A"].add("Green", english)
        tt2["A"].add("Blue", math)
        tt2["B"].add("Green", bio)
        self.assertEquals(tt, tt2)
        tt2.model = model
        self.assertNotEquals(tt, tt2)
        tt.model = model
        self.assertEquals(tt, tt2)

        tt2["B"].remove("Green", bio)
        self.assertNotEquals(tt, tt2)

        tt["B"].remove("Green", bio)
        self.assertEquals(tt, tt2)

        tt2.timezone = 'Europe/Vilnius'
        self.assertNotEquals(tt, tt2)

    def test_itercontent(self):
        from schooltool.timetable import TimetableActivity
        tt = self.createTimetable()
        english = TimetableActivity("English")
        math = TimetableActivity("Math")
        bio = TimetableActivity("Biology")
        tt["A"].add("Green", english)
        tt["A"].add("Blue", math)
        tt["B"].add("Green", bio)
        result = list(tt.itercontent())
        expected = [("A", "Green", english),
                    ("A", "Blue", math),
                    ("B", "Green", bio)]
        self.assertEquals(result, expected)


class EventTestMixin(PlacelessSetup):

    def setUp(self):
        from zope.event import subscribers
        PlacelessSetup.setUp(self)
        self.events = []
        def subscriber(event):
            self.events.append(event)
        subscribers.append(subscriber)

    def checkOneEventReceived(self):
        self.assertEquals(len(self.events), 1, self.events)
        return self.events[0]

    def clearEvents(self):
        self.events[:] = []


class TestTimetableDay(EventTestMixin, unittest.TestCase):

    def test_interface(self):
        from schooltool.timetable import TimetableDay
        from schooltool.timetable.interfaces import ITimetableDay, ITimetableDayWrite

        td = TimetableDay()
        verifyObject(ITimetableDay, td)
        verifyObject(ITimetableDayWrite, td)

    def test_keys(self):
        from schooltool.timetable import TimetableDay

        periods = ('1', '2', '3', '4', '5')
        td = TimetableDay(periods)
        self.assertEqual(td.keys(), periods)

    def testComparison(self):
        from schooltool.timetable import TimetableDay, Timetable

        periods = ('A', 'B')
        td1 = TimetableDay(periods)
        td2 = TimetableDay(periods)
        tt = Timetable(['td1', 'td2'])
        tt['td1'] = td1
        tt['td2'] = td2

        self.assertEquals(td1, td2)
        self.assertNotEquals(td1, None)
        self.failIf(td1 != td2)

        a1 = ActivityStub()
        td1.add("A", a1)
        self.assertNotEquals(td1, td2)
        td2.add("A", a1)
        self.assertEquals(td1, td2)

        td1 = TimetableDay(periods)
        td3 = TimetableDay(('C', 'D'))
        self.assertNotEquals(td1, td3)

        td1 = TimetableDay(periods)
        td4 = TimetableDay(periods, homeroom_period_ids=['B'])
        self.assertNotEquals(td1, td4)

    def test_getitem_add_items_clear_remove(self):
        from schooltool.timetable import TimetableDay, Timetable, TimetableDict
        from schooltool.timetable.interfaces import ITimetableActivityAddedEvent
        from schooltool.timetable.interfaces import ITimetableActivityRemovedEvent

        periods = ('1', '2', '3', '4')
        timetable = Timetable(['td'])
        ttd = TimetableDict()
        ttd['a.key'] = timetable
        td = timetable['td'] = TimetableDay(periods)

        self.assertRaises(KeyError, td.__getitem__, "Mo")
        self.assertEqual(len(list(td["1"])), 0)

        self.assertRaises(TypeError, td.add, "1", object())
        math = ActivityStub()
        self.assertRaises(ValueError, td.add, "Mo", math)

        self.events[:] = []

        td.add("1", math)
        e1 = self.checkOneEventReceived()
        self.assert_(ITimetableActivityAddedEvent.providedBy(e1))
        self.assert_(e1.activity.timetable is timetable)
        self.assertEquals(e1.activity, math)
        self.assertEquals(e1.day_id, 'td')
        self.assertEquals(e1.period_id, '1')

        self.assertEqual(list(td["1"]), [math])
        self.assert_(list(td["1"])[0].replaced)

        result = [(p, Set(i)) for p, i in td.items()]

        self.assertEqual(result, [('1', Set([math])), ('2', Set([])),
                                  ('3', Set([])), ('4', Set([]))])
        english = ActivityStub()
        self.clearEvents()
        td.add("2", english)
        e2 = self.checkOneEventReceived()
        self.assertEquals(e2.period_id, '2')

        result = [(p, Set(i)) for p, i in td.items()]
        self.assertEqual(result, [('1', Set([math])), ('2', Set([english])),
                                  ('3', Set([])), ('4', Set([]))])


        # test clear()
        self.assertEqual(Set(td["2"]), Set([english]))
        self.assertRaises(ValueError, td.clear, "Mo")
        self.clearEvents()
        td.clear("2")
        e2 = self.checkOneEventReceived()
        self.assert_(ITimetableActivityRemovedEvent.providedBy(e2))
        self.assert_(e2.activity.timetable is timetable)
        self.assertEquals(e2.activity, english)
        self.assertEquals(e2.day_id, 'td')
        self.assertEquals(e2.period_id, '2')
        self.assertRaises(ValueError, td.clear, "foo")
        self.assertEqual(Set(td["2"]), Set([]))

        # test remove()
        td.add("1", english)
        result = [(p, Set(i)) for p, i in td.items()]
        self.assertEqual(result, [('1', Set([english, math])),
                                  ('2', Set([])), ('3', Set([])),
                                  ('4', Set([]))])
        self.clearEvents()
        td.remove("1", math)
        e3 = self.checkOneEventReceived()
        self.assert_(ITimetableActivityRemovedEvent.providedBy(e3))
        self.assert_(e3.activity.timetable is timetable)
        self.assertEquals(e3.activity, math)
        self.assertEquals(e3.day_id, 'td')
        self.assertEquals(e3.period_id, '1')
        self.assertRaises(KeyError, td.remove, "1", math)
        result = [(p, Set(i)) for p, i in td.items()]
        self.assertEqual(result, [('1', Set([english])),
                                  ('2', Set([])), ('3', Set([])),
                                  ('4', Set([]))])


class TestTimetableActivity(unittest.TestCase):

    def test(self):
        from schooltool.timetable import TimetableActivity
        from schooltool.timetable.interfaces import ITimetableActivity

        owner = object()
        ta = TimetableActivity("Dancing", owner)
        verifyObject(ITimetableActivity, ta)
        self.assertEqual(ta.title, "Dancing")
        self.assert_(ta.owner is owner)
        self.assertEqual(list(ta.resources), [])

        class FakeThing:
            title = "Dancing"
        fake_thing = FakeThing()
        tb = TimetableActivity("Dancing", owner)
        tc = TimetableActivity("Fencing", owner)
        td = TimetableActivity("Dancing", object())
        res1 = object()
        res2 = object()
        te = TimetableActivity("Dancing", owner, [res1, res2])
        tf = TimetableActivity("Dancing", owner, [res2, res1])
        tg = TimetableActivity("Dancing", owner, [res1, res2],
                               timetable=object())

        # Do we really want to ignore timetable when hashing/comparing?
        # On further thought it does not matter -- we never compare activities
        # that come from timetables with different keys.

        # __eq__
        self.assertEqual(ta, ta)
        self.assertEqual(ta, tb)
        self.assertNotEqual(ta, tc)
        self.assertNotEqual(ta, td)
        self.assertNotEqual(ta, fake_thing)
        self.assertNotEqual(ta, te)
        self.assertEqual(te, tf)
        self.assertEqual(tf, tg)

        # __ne__
        self.failIf(ta != ta)
        self.failIf(ta != tb)
        self.assert_(ta != tc)
        self.assert_(ta != td)
        self.assert_(ta != fake_thing)
        self.assert_(ta != te)
        self.failIf(te != tf)
        self.failIf(tf != tg)

        # __hash__
        self.assertEqual(hash(ta), hash(tb))
        self.assertNotEqual(hash(ta), hash(tc))
        self.assertNotEqual(hash(ta), hash(td))
        self.assertNotEqual(hash(ta), hash(te))
        self.assertEqual(hash(te), hash(tf))
        self.assertEqual(hash(tf), hash(tg))

    def test_immutability(self):
        from schooltool.timetable import TimetableActivity
        owner = object()
        ta = TimetableActivity("Dancing", owner)

        def try_to_assign_title():
            ta.title = "xyzzy"
        def try_to_assign_owner():
            ta.owner = "xyzzy"
        def try_to_assign_resources():
            ta.resources = "xyzzy"
        def try_to_modify_resources():
            ta.resources.add("xyzzy")
        self.assertRaises(AttributeError, try_to_assign_title)
        self.assertRaises(AttributeError, try_to_assign_owner)
        self.assertRaises(AttributeError, try_to_assign_resources)
        self.assertRaises(AttributeError, try_to_modify_resources)
        self.assertEquals(ta.title, "Dancing")

    def test_replace(self):
        from schooltool.timetable import TimetableActivity
        owner = object()
        owner2 = object()
        ta = TimetableActivity("Dancing", owner)
        tb = ta.replace(title=None, owner=owner2)
        self.assertEquals(tb.title, None)
        self.assertEquals(tb.owner, owner2)


class TestTimetableEvents(unittest.TestCase):

    def test_tt_replaced_event(self):
        from schooltool.timetable import TimetableReplacedEvent
        from schooltool.timetable.interfaces import ITimetableReplacedEvent
        obj = object()
        key = ('a', 'b')
        old_timetable = object()
        new_timetable = object()
        e = TimetableReplacedEvent(obj, key, old_timetable, new_timetable)
        verifyObject(ITimetableReplacedEvent, e)

    def test_activity_added_event(self):
        from schooltool.timetable import TimetableActivityAddedEvent
        from schooltool.timetable.interfaces import ITimetableActivityAddedEvent
        obj = object()
        day_id = 'Monday'
        period_id = 'autumn'
        e = TimetableActivityAddedEvent(obj, day_id, period_id)
        verifyObject(ITimetableActivityAddedEvent, e)

    def test_activity_removed_event(self):
        from schooltool.timetable import TimetableActivityRemovedEvent
        from schooltool.timetable.interfaces import ITimetableActivityRemovedEvent
        obj = object()
        day_id = 'Monday'
        period_id = 'autumn'
        e = TimetableActivityRemovedEvent(obj, day_id, period_id)
        verifyObject(ITimetableActivityRemovedEvent, e)


class TestTimetablingPersistence(unittest.TestCase):
    """A functional test for timetables persistence."""

    def setUp(self):
        from ZODB.DB import DB
        from ZODB.MappingStorage import MappingStorage
        self.db = DB(MappingStorage())
        self.datamgr = self.db.open()

    def test(self):
        from schooltool.timetable import Timetable, TimetableDay
        from schooltool.timetable import TimetableActivity
        import transaction
        tt = Timetable(('A', 'B'))
        self.datamgr.root()['tt'] = tt
        transaction.commit()

        periods = ('Green', 'Blue')
        tt["A"] = TimetableDay(periods)
        tt["B"] = TimetableDay(periods)
        transaction.commit()

        try:
            datamgr = self.db.open()
            tt2 = datamgr.root()['tt']
            self.assert_(tt2["A"].periods, periods)
            self.assert_(tt2["B"].periods, periods)
        finally:
            transaction.abort()
            datamgr.close()

        tt["A"].add("Green", TimetableActivity("English"))
        tt["A"].add("Blue", TimetableActivity("Math"))
        tt["B"].add("Green", TimetableActivity("Biology"))
        tt["B"].add("Blue", TimetableActivity("Geography"))
        transaction.commit()

        self.assertEqual(len(list(tt["A"]["Green"])), 1)
        self.assertEqual(len(list(tt["A"]["Blue"])), 1)
        self.assertEqual(len(list(tt["B"]["Green"])), 1)
        self.assertEqual(len(list(tt["B"]["Blue"])), 1)

########## XXX: Fails
##         try:
##             datamgr = self.db.open()
##             tt3 = datamgr.root()['tt']
##             self.assertEqual(len(list(tt3["A"]["Green"])), 1)
##             self.assertEqual(len(list(tt3["A"]["Blue"])), 1)
##             self.assertEqual(len(list(tt3["B"]["Green"])), 1)
##             self.assertEqual(len(list(tt3["B"]["Blue"])), 1)
##             act = iter(tt3["B"]["Blue"]).next()
##             self.assertEqual(act.title, "Geography")
##         finally:
##             transaction.abort()
##             datamgr.close()

    def testTimetableActivity(self):
        from schooltool.timetable import TimetableActivity
        from zope.traversing.interfaces import IContainmentRoot
        import transaction
        from schooltool.person.person import Person
        from schooltool.resource.resource import Resource

        parent = PersistentLocatableStub()
        directlyProvides(parent, IContainmentRoot)
        owner = Person()
        owner.__parent__ = parent
        owner.__name__ = 'parent'
        res1 = Resource()
        res1.__parent__ = parent
        res1.__name__ = 'res1'
        res2 = Resource()
        res2.__parent__ = parent
        res2.__name__ = 'res2'
        ta = TimetableActivity("Pickling", owner, [res1, res2])
        tb = TimetableActivity("Pickling", owner, [res2, res1])
        tseta = Set([ta, tb])
        tsetb = Set([ta, tb])
        self.datamgr.root()['ta'] = ta
        self.datamgr.root()['tb'] = tb
        self.datamgr.root()['tseta'] = tseta
        self.datamgr.root()['tsetb'] = tsetb
        transaction.commit()

        try:
            datamgr = self.db.open()
            ta2 = datamgr.root()['ta']
            tb2 = datamgr.root()['tb']
            tseta2 = datamgr.root()['tseta']
            tsetb2 = datamgr.root()['tsetb']
            self.assertEqual(ta2, tb2)
            self.assertEqual(hash(ta2), hash(tb2))
            self.assertEqual(tseta2, tsetb2)
            ## Activities unpersisted in different DB connections are not
            ## supposed to be compared
            #self.assertEqual(ta, ta2)
            #XXX: self.assertEqual(hash(ta), hash(ta2))
            #self.assertEqual(tset, tset2)
        finally:
            transaction.abort()
            datamgr.close()


class TestSchooldaySlot(unittest.TestCase):

    def test(self):
        from schooltool.timetable import SchooldaySlot
        from schooltool.timetable.interfaces import ISchooldaySlot

        ev = SchooldaySlot(time(9, 00), timedelta(minutes=45))
        verifyObject(ISchooldaySlot, ev)
        self.assertEqual(ev.tstart, time(9,0))
        self.assertEqual(ev.duration, timedelta(seconds=2700))

    def test_eq(self):
        from schooltool.timetable import SchooldaySlot
        self.assertEqual(
            SchooldaySlot(time(9, 00), timedelta(minutes=45)),
            SchooldaySlot(time(9, 00), timedelta(minutes=45)))
        self.assertEqual(
            hash(SchooldaySlot(time(9, 0), timedelta(minutes=45))),
            hash(SchooldaySlot(time(9, 0), timedelta(minutes=45))))
        self.assertNotEqual(
            SchooldaySlot(time(9, 00), timedelta(minutes=45)),
            SchooldaySlot(time(9, 01), timedelta(minutes=45)))
        self.assertNotEqual(
            SchooldaySlot(time(9, 00), timedelta(minutes=45)),
            SchooldaySlot(time(9, 00), timedelta(minutes=90)))
        self.assertNotEqual(
            SchooldaySlot(time(9, 00), timedelta(minutes=45)),
            object())


class TestSchooldayTemplate(unittest.TestCase):

    def test_interface(self):
        from schooltool.timetable import SchooldayTemplate
        from schooltool.timetable.interfaces import ISchooldayTemplate
        from schooltool.timetable.interfaces import ISchooldayTemplateWrite

        tmpl = SchooldayTemplate()
        verifyObject(ISchooldayTemplate, tmpl)
        verifyObject(ISchooldayTemplateWrite, tmpl)

    def test_add_remove_iter(self):
        from schooltool.timetable import SchooldayTemplate, SchooldaySlot

        tmpl = SchooldayTemplate()
        self.assertEqual(list(iter(tmpl)), [])
        self.assertRaises(TypeError, tmpl.add, object())

        lesson1 = SchooldaySlot(time(9, 0), timedelta(minutes=45))
        lesson2 = SchooldaySlot(time(10, 0), timedelta(minutes=45))

        tmpl.add(lesson1)
        self.assertEqual(list(iter(tmpl)), [lesson1])

        # Adding the same thing again.
        tmpl.add(lesson1)
        self.assertEqual(list(iter(tmpl)), [lesson1])

        tmpl.add(lesson2)
        self.assertEqual(len(list(iter(tmpl))), 2)
        tmpl.remove(lesson1)
        self.assertEqual(list(iter(tmpl)), [lesson2])

    def test_eq(self):
        from schooltool.timetable import SchooldayTemplate, SchooldaySlot

        tmpl = SchooldayTemplate()
        tmpl.add(SchooldaySlot(time(9, 0), timedelta(minutes=45)))
        tmpl.add(SchooldaySlot(time(10, 0), timedelta(minutes=45)))

        tmpl2 = SchooldayTemplate()
        tmpl2.add(SchooldaySlot(time(9, 0), timedelta(minutes=45)))
        tmpl2.add(SchooldaySlot(time(10, 0), timedelta(minutes=45)))

        self.assertEqual(tmpl, tmpl)
        self.assertEqual(tmpl, tmpl2)
        self.assert_(not tmpl != tmpl2)


class ContentStub(object):

    implements(IOwnTimetables, IAttributeAnnotatable)

    members = RelationshipProperty(URIMembership, URIGroup, URIMember)
    groups = RelationshipProperty(URIMembership, URIGroup, URIMember)


class Parent(ContentStub):

    implements(ITimetables, ICompositeTimetables)

    def __init__(self):
        self.object = self


class PersistentLocatableStub(Persistent):

    implements(ILocation)
    __name__ = None
    __parent__ = None


class TimetableStub(PersistentLocatableStub):
    implements(ITimetable)


class TestTimetableDict(EventTestMixin, unittest.TestCase):

    def test(self):
        from schooltool.timetable import TimetableDict
        from persistent.dict import PersistentDict
        from schooltool.timetable.interfaces import ITimetableDict

        timetables = TimetableDict()
        self.assert_(isinstance(timetables, PersistentDict))
        verifyObject(ILocation, timetables)
        verifyObject(ITimetableDict, timetables)

    def test_setitem_delitem(self):
        from schooltool.timetable import TimetableDict

        td = TimetableDict()
        item = TimetableStub()
        td['aa.bb'] = item
        self.assertEqual(item.__name__, ('aa.bb'))
        self.assertEqual(item.__parent__, td)
        self.assertEqual(item, td['aa.bb'])

        item2 = TimetableStub()
        td['aa.bb'] = item2
        self.assertEqual(item2, td['aa.bb'])
        self.assertEqual(item.__parent__, None)
        self.assertEqual(item.__name__, None)

        del td['aa.bb']
        self.assertRaises(KeyError, td.__getitem__, ('aa.bb'))
        self.assertEqual(item2.__parent__, None)
        self.assertEqual(item2.__name__, None)

    def test_setitem_delitem_events(self):
        from schooltool.timetable import TimetableDict
        from schooltool.timetable.interfaces import ITimetableReplacedEvent

        td = TimetableDict()
        item = TimetableStub()
        td['aa.bb'] = item
        e = self.checkOneEventReceived()
        self.assert_(ITimetableReplacedEvent.providedBy(e))
        self.assert_(e.object is td.__parent__)
        self.assertEquals(e.key, ('aa.bb'))
        self.assert_(e.old_timetable is None)
        self.assert_(e.new_timetable is item)

        self.clearEvents()
        item2 = TimetableStub()
        td['aa.bb'] = item2
        e = self.checkOneEventReceived()
        self.assert_(ITimetableReplacedEvent.providedBy(e))
        self.assert_(e.object is td.__parent__)
        self.assertEquals(e.key, ('aa.bb'))
        self.assert_(e.old_timetable is item)
        self.assert_(e.new_timetable is item2)

        self.clearEvents()
        del td['aa.bb']
        e = self.checkOneEventReceived()
        self.assert_(ITimetableReplacedEvent.providedBy(e))
        self.assert_(e.object is td.__parent__)
        self.assertEquals(e.key, ('aa.bb'))
        self.assert_(e.old_timetable is item2)
        self.assert_(e.new_timetable is None)

    def test_clear(self):
        from schooltool.timetable import TimetableDict
        td = TimetableDict()
        td['a.b'] = TimetableStub()
        td['b.c'] = TimetableStub()
        self.clearEvents()
        td.clear()
        self.assertEquals(list(td.keys()), [])
        self.assertEquals(len(self.events), 2)

    def test_validation(self):
        from schooltool.timetable import TimetableDict
        td = TimetableDict()
        self.assertRaises(ValueError, td.__setitem__, 'a.b.c',
                          TimetableStub())
        self.assertRaises(ValueError, td.__setitem__, 'abc',
                          TimetableStub())
        self.assertRaises(ValueError, td.__setitem__, 'c.',
                          TimetableStub())
        self.assertRaises(ValueError, td.__setitem__, '.c',
                          TimetableStub())
        td['a.c'] = TimetableStub()


class TestTimetablesAdapter(NiceDiffsMixin, EqualsSortedMixin,
                            unittest.TestCase):

    def setUp(self):
        from schooltool.relationship.tests import setUpRelationships
        from schooltool.timetable.interfaces import ITimetableSource
        from schooltool.timetable import TimetablesAdapter

        self.site = setup.placefulSetUp(True)
        setup.setUpAnnotations()
        setUpRelationships()

        ztapi.provideAdapter(IOwnTimetables, ITimetables,
                             TimetablesAdapter)

    def tearDown(self):
        setup.placefulTearDown()

    def test_interface(self):
        from schooltool.timetable import TimetablesAdapter, TimetableDict

        content = ContentStub()
        tm = TimetablesAdapter(content)
        verifyObject(ITimetables, tm)
        self.assert_(isinstance(tm.timetables, TimetableDict))
        self.assertEqual(tm.timetables.__parent__, content)


class TestCompositeTimetables(NiceDiffsMixin, EqualsSortedMixin,
                              unittest.TestCase):

    def setUp(self):
        from schooltool.relationship.tests import setUpRelationships
        from schooltool.timetable.interfaces import ITimetableSource
        from schooltool.timetable.interfaces import IHaveTimetables
        from schooltool.timetable.interfaces import ICompositeTimetables
        from schooltool.timetable.source import MembershipTimetableSource
        from schooltool.timetable.source import OwnedTimetableSource
        from schooltool.timetable import TimetablesAdapter
        from schooltool.timetable import CompositeTimetables

        self.site = setup.placefulSetUp(True)
        setup.setUpAnnotations()
        setUpRelationships()

        ztapi.subscribe((IHaveTimetables, ), ITimetableSource,
                        MembershipTimetableSource)
        ztapi.subscribe((IOwnTimetables, ), ITimetableSource,
                        OwnedTimetableSource)
        ztapi.provideAdapter(IHaveTimetables, ICompositeTimetables,
                             CompositeTimetables)
        ztapi.provideAdapter(IOwnTimetables, ITimetables,
                             TimetablesAdapter)

    def tearDown(self):
        setup.placefulTearDown()

    def newTimetable(self):
        from schooltool.timetable import Timetable, TimetableDay
        tt = Timetable(("A", "B"))
        tt["A"] = TimetableDay(["Green", "Blue"])
        tt["B"] = TimetableDay(["Green", "Blue"])
        return tt

    def newTimetableSchema(self):
        from schooltool.timetable.schema import TimetableSchema
        from schooltool.timetable.schema import TimetableSchemaDay
        tt = TimetableSchema(("A", "B"))
        tt["A"] = TimetableSchemaDay(["Green", "Blue"])
        tt["B"] = TimetableSchemaDay(["Green", "Blue"])
        return tt

    def test_composite_table_own(self):
        content = ContentStub()
        ct = ICompositeTimetables(content)
        tm = ITimetables(content)

        self.assertEqual(tm.timetables, {})
        self.assertEqual(ct.getCompositeTimetable("a", "b"), None)
        self.assertEqual(ct.listCompositeTimetables(), Set())

        tt = tm.timetables["2003 fall.sequential"] = self.newTimetable()

        result = ct.getCompositeTimetable("2003 fall", "sequential")
        self.assertEqual(result, tt)
        self.assert_(result is not tt)

        self.assertEqual(ct.listCompositeTimetables(),
                         Set([("2003 fall", "sequential")]))

    def test_composite_table_related(self):
        from schooltool.timetable import TimetableActivity
        from schooltool.app.membership import Membership

        content = ContentStub()
        ct = ICompositeTimetables(content)
        tm = ITimetables(content)
        parent = Parent()
        Membership(group=parent, member=content)

        composite = self.newTimetable()
        english = TimetableActivity("English")
        composite["A"].add("Green", english)

        def newComposite(term_id, schema_id):
            if (term_id, schema_id) == ("2003 fall", "sequential"):
                return composite
            else:
                return None

        def listComposites():
            return Set([("2003 fall", "sequential")])

        parent.getCompositeTimetable = newComposite
        parent.listCompositeTimetables = listComposites

        result = ct.getCompositeTimetable("2003 fall", "sequential")
        self.assertEqual(result, composite)
        self.assert_(result is not composite)
        self.assertEqual(ct.listCompositeTimetables(),
                         Set([("2003 fall", "sequential")]))

        # Now test with our object having a private timetable
        private = self.newTimetable()
        math = TimetableActivity("Math")
        private["B"].add("Blue", math)
        tm.timetables["2003 fall.sequential"] = private

        result = ct.getCompositeTimetable("2003 fall", "sequential")
        expected = composite.cloneEmpty()
        expected.update(composite)
        expected.update(private)
        self.assertEqual(result, expected)
        self.assertEqual(ct.listCompositeTimetables(),
                         Set([("2003 fall", "sequential")]))

    def test_paths(self):
        content = ContentStub()
        content.__name__ = 'stub'
        content.__parent__ = self.site
        ct = ICompositeTimetables(content)
        tm = ITimetables(content)
        tt = tm.timetables["2003-fall.sequential"] = self.newTimetable()
        tt1 = ct.getCompositeTimetable("2003-fall", "sequential")

        self.assertEqual(getPath(tt),
                         '/stub/timetables/2003-fall.sequential')
        self.assertEqual(getPath(tt1),
                         '/stub/composite-timetables/2003-fall.sequential')

    def test_makeTimetableCalendar(self):
        from schooltool.timetable import TimetableActivity
        from schooltool.app.cal import Calendar, CalendarEvent

        app = stsetup.setupSchoolToolSite()

        term = app["terms"]['2003 fall'] = TermStub()
        tss = app["ttschemas"]
        tss['sequential'] = self.newTimetableSchema()
        tss['other'] = self.newTimetableSchema()
        tss['and another'] = self.newTimetableSchema()
        ct = ICompositeTimetables(ContentStub())

        tt1 = self.newTimetable()
        tt1["A"].add("Green", TimetableActivity("AG"))
        cal1 = Calendar(None)
        ev1 = CalendarEvent(datetime(2003, 11, 26, 12, 00),
                            timedelta(minutes=30), "AG")
        cal1.addEvent(ev1)

        tt2 = self.newTimetable()
        tt2["A"].add("Blue", TimetableActivity("AB"))
        cal2 = Calendar(None)
        ev2 = CalendarEvent(datetime(2003, 11, 26, 13, 00),
                            timedelta(minutes=30), "AB")
        cal2.addEvent(ev2)

        ttdict = {"2003 fall.sequential": tt1,
                  "2003 fall.other": tt2}
        ct.getCompositeTimetable = lambda p, s: ttdict.get("%s.%s" % (p, s))
        ct.listCompositeTimetables = lambda: [k.split(".")
                                              for k in ttdict.keys()]

        class TimetableModelStub:
            def createCalendar(this_self, schoolday_model, tt, first=None,
                               last=None):
                self.assert_(schoolday_model is term)
                if tt is tt1:
                    return cal1
                elif tt is tt2:
                    return cal2
                else:
                    self.fail("what is %r?" % tt)

        tt1.model = TimetableModelStub()
        tt2.model = TimetableModelStub()
        cal = ct.makeTimetableCalendar()
        self.assertEqualSorted(list(cal), list(cal1) + list(cal2))
        self.assert_(cal.__parent__ is ct.context)

    def test_makeTimetableCalendar_with_filtering(self):
        from schooltool.timetable import TimetablesAdapter
        from schooltool.timetable import CompositeTimetables

        class TimetableModelStub:
            def createCalendar(self, term, timetable, first=None, last=None):
                return ['%s--%s' % (first, last)]

        class TimetableStub:
            model = TimetableModelStub()

        content = ContentStub()
        ct = CompositeTimetables(content)
        fake_term_container = {'term1': 'term1'}
        ct._getTermContainer = lambda: fake_term_container
        ct.listCompositeTimetables = lambda: [('term1', 'schema1')]
        ct.getCompositeTimetable = lambda tid, sid: TimetableStub()
        cal = ct.makeTimetableCalendar(first='last year', last='next week')
        self.assertEquals(list(cal), ['last year--next week'])


def doctest_findRelatedTimetables_forSchoolTimetables():
    """Tests for findRelatedTimetables() with school timetables

       >>> from schooltool.timetable import TimetablesAdapter
       >>> from schooltool.timetable.interfaces import ITimetables
       >>> from schooltool.timetable.interfaces import IOwnTimetables
       >>> setup.placefulSetUp()
       >>> ztapi.provideAdapter(IOwnTimetables, ITimetables,
       ...                      TimetablesAdapter)
       >>> setup.setUpAnnotations()

       >>> from schooltool.testing.setup import createSchoolToolApplication
       >>> from schooltool.timetable import findRelatedTimetables
       >>> app = stsetup.setupSchoolToolSite()
       >>> directlyProvides(app, IOwnTimetables)

    Let's create a timetable schema:

       >>> from schooltool.timetable.schema import TimetableSchema
       >>> from schooltool.timetable.schema import TimetableSchemaDay

       >>> days = ('A', 'B')
       >>> periods1 = ('Green', 'Blue')
       >>> tts = TimetableSchema(days)
       >>> tts["A"] = TimetableSchemaDay(periods1)
       >>> tts["B"] = TimetableSchemaDay(periods1)

       >>> days = ('C', 'D')
       >>> tts2 = TimetableSchema(days)
       >>> tts2["C"] = TimetableSchemaDay(periods1)
       >>> tts2["D"] = TimetableSchemaDay(periods1)

       >>> app['ttschemas']['simple'] = tts
       >>> app['ttschemas']['other'] = tts2

    Now we can call our utility function.  Since our schema is not
    used, an empty list is returned:

       >>> findRelatedTimetables(tts)
       []

    Let's add a timetable to the app object:

       >>> ITimetables(app).timetables['2006.simple'] = tts.createTimetable()
       >>> findRelatedTimetables(tts)
       [<Timetable: ('A', 'B'),
        {'A': <schooltool.timetable.TimetableDay object at ...>,
         'B': <schooltool.timetable.TimetableDay object at ...>}, None>]

    Now, let's add a timetable of a different schema:

       >>> ITimetables(app).timetables['2006.other'] = tts2.createTimetable()
       >>> findRelatedTimetables(tts)
       [<Timetable: ('A', 'B'),
        {'A': <schooltool.timetable.TimetableDay object at ...>,
         'B': <schooltool.timetable.TimetableDay object at ...>}, None>]

    Let's add some persons, groups and resources with timetables:

       >>> from schooltool.person.person import Person
       >>> from schooltool.group.group import Group
       >>> from schooltool.resource.resource import Resource

       >>> app['persons']['p1'] = Person('p1')
       >>> app['persons']['p2'] = Person('p2')
       >>> app['groups']['g'] = Group('friends')
       >>> app['resources']['r'] = Resource('friends')

       >>> for ob in (app['persons']['p1'], app['persons']['p2'],
       ...            app['groups']['g'], app['resources']['r']):
       ...     directlyProvides(ob, IOwnTimetables)

       >>> adapter = ITimetables(app['persons']['p1'])
       >>> adapter.timetables['2006.simple'] = tts.createTimetable()
       >>> adapter.timetables['2005.simple'] = tts.createTimetable()
       >>> adapter.timetables['2006.other'] = tts2.createTimetable()

       >>> adapter = ITimetables(app['persons']['p2'])
       >>> adapter.timetables['2006.simple'] = tts.createTimetable()

       >>> adapter = ITimetables(app['groups']['g'])
       >>> adapter.timetables['2006.simple'] = tts.createTimetable()
       >>> adapter.timetables['2006.other'] = tts2.createTimetable()

       >>> adapter = ITimetables(app['resources']['r'])
       >>> adapter.timetables['2006.simple'] = tts.createTimetable()

    Let's see the timetables for this schema now:

       >>> findRelatedTimetables(tts)
       [<Timetable: ('A', 'B'), ...>,
        <Timetable: ('A', 'B'), ...>,
        <Timetable: ('A', 'B'), ...>,
        <Timetable: ('A', 'B'), ...>,
        <Timetable: ('A', 'B'), ...>,
        <Timetable: ('A', 'B'), ...>]

       >>> [(tt.__parent__.__parent__.__name__, tt.__name__)
       ...   for tt in findRelatedTimetables(tts)]
       [(None, '2006.simple'), (u'p1', '2006.simple'),
        (u'p1', '2005.simple'), (u'p2', '2006.simple'),
        (u'g', '2006.simple'), (u'r', '2006.simple')]

    Let's see the timetables of the other schema:

       >>> findRelatedTimetables(tts2)
       [<Timetable: ('C', 'D'), ...>,
        <Timetable: ('C', 'D'), ...>,
        <Timetable: ('C', 'D'), ...>]

       >>> [(tt.__parent__.__parent__.__name__, tt.__name__)
       ...   for tt in findRelatedTimetables(tts2)]
       [(None, '2006.other'), (u'p1', '2006.other'), (u'g', '2006.other')]

    Clean up:

       >>> setup.placefulTearDown()
    """


def doctest_findRelatedTimetables_forTerm():
    """Tests for findRelatedTimetables() with terms as arguments

       >>> from schooltool.timetable.interfaces import IOwnTimetables
       >>> from schooltool.timetable import TimetablesAdapter
       >>> from schooltool.timetable.interfaces import ITimetables
       >>> setup.placefulSetUp()
       >>> ztapi.provideAdapter(IOwnTimetables, ITimetables,
       ...                      TimetablesAdapter)
       >>> setup.setUpAnnotations()

       >>> from schooltool.testing.setup import createSchoolToolApplication
       >>> from schooltool.timetable import findRelatedTimetables
       >>> app = stsetup.setupSchoolToolSite()
       >>> directlyProvides(app, IOwnTimetables)

    Let's create a couple of terms:

       >>> from schooltool.term.term import Term
       >>> t1 = app['terms']['2005'] = Term('2005', date(2005, 1, 1),
       ...                                  date(2005, 12, 31))
       >>> t2 = app['terms']['2006'] = Term('2006', date(2006, 1, 1),
       ...                                  date(2006, 12, 31))

    We'll also need a timetable schema:

       >>> from schooltool.timetable.schema import TimetableSchema
       >>> from schooltool.timetable.schema import TimetableSchemaDay

       >>> days = ('A', 'B')
       >>> periods1 = ('Green', 'Blue')
       >>> tts = TimetableSchema(days)
       >>> tts["A"] = TimetableSchemaDay(periods1)
       >>> tts["B"] = TimetableSchemaDay(periods1)
       >>> app['ttschemas']['simple'] = tts

    Now we can call our utility function.  Since our schema is not
    used, an empty list is returned:

       >>> findRelatedTimetables(t1)
       []

    Let's add a timetable to the app object:

       >>> ITimetables(app).timetables['2005.simple'] = tts.createTimetable()
       >>> findRelatedTimetables(t1)
       [<Timetable: ('A', 'B'),
        {'A': <schooltool.timetable.TimetableDay object at ...>,
         'B': <schooltool.timetable.TimetableDay object at ...>}, None>]

    Now, let's add a timetable of a different term:

       >>> ITimetables(app).timetables['2006.simple'] = tts.createTimetable()
       >>> findRelatedTimetables(t1)
       [<Timetable: ('A', 'B'),
        {'A': <schooltool.timetable.TimetableDay object at ...>,
         'B': <schooltool.timetable.TimetableDay object at ...>}, None>]

    Let's add some persons, groups and resources with timetables:

       >>> from schooltool.person.person import Person
       >>> from schooltool.group.group import Group
       >>> from schooltool.resource.resource import Resource

       >>> app['persons']['p1'] = Person('p1')
       >>> app['persons']['p2'] = Person('p2')
       >>> app['groups']['g'] = Group('friends')
       >>> app['resources']['r'] = Resource('friends')

       >>> for ob in (app['persons']['p1'], app['persons']['p2'],
       ...            app['groups']['g'], app['resources']['r']):
       ...     directlyProvides(ob, IOwnTimetables)

       >>> adapter = ITimetables(app['persons']['p1'])
       >>> adapter.timetables['2005.simple'] = tts.createTimetable()
       >>> adapter.timetables['2005.other'] = tts.createTimetable()
       >>> adapter.timetables['2006.other'] = tts.createTimetable()

       >>> adapter = ITimetables(app['persons']['p2'])
       >>> adapter.timetables['2005.simple'] = tts.createTimetable()

       >>> adapter = ITimetables(app['groups']['g'])
       >>> adapter.timetables['2006.simple'] = tts.createTimetable()
       >>> adapter.timetables['2005.simple'] = tts.createTimetable()

       >>> adapter = ITimetables(app['resources']['r'])
       >>> adapter.timetables['2005.simple'] = tts.createTimetable()

    Let's see the timetables for this schema now:

       >>> findRelatedTimetables(t1)
       [<Timetable: ('A', 'B'), ...>,
        <Timetable: ('A', 'B'), ...>,
        <Timetable: ('A', 'B'), ...>,
        <Timetable: ('A', 'B'), ...>,
        <Timetable: ('A', 'B'), ...>,
        <Timetable: ('A', 'B'), ...>]

       >>> [(tt.__parent__.__parent__.__name__, tt.__name__)
       ...   for tt in findRelatedTimetables(t1)]
       [(None, '2005.simple'), (u'p1', '2005.other'), (u'p1', '2005.simple'),
        (u'p2', '2005.simple'), (u'g', '2005.simple'), (u'r', '2005.simple')]

    Let's see the timetables of the other schema:

       >>> findRelatedTimetables(t2)
       [<Timetable: ('A', 'B'), ...>,
        <Timetable: ('A', 'B'), ...>,
        <Timetable: ('A', 'B'), ...>]

       >>> [(tt.__parent__.__parent__.__name__, tt.__name__)
       ...   for tt in findRelatedTimetables(t2)]
       [(None, '2006.simple'), (u'p1', '2006.other'), (u'g', '2006.simple')]

    Clean up:

       >>> setup.placefulTearDown()

    """

def doctest_findRelatedTimetables_other():
    """Tests for findRelatedTimetables()

    findRelatedTimetables works only with school timetables and terms,
    and raises if gets anything else:

        >>> from schooltool.timetable import findRelatedTimetables
        >>> findRelatedTimetables(object())
        Traceback (most recent call last):
          ...
        TypeError: Expected a Term or a TimetableSchema, got <object ...>

    """


def test_suite():
    suite = unittest.TestSuite()
    optionflags = (doctest.ELLIPSIS | doctest.REPORT_NDIFF |
                   doctest.NORMALIZE_WHITESPACE)
    suite.addTest(doctest.DocTestSuite(optionflags=optionflags))
    suite.addTest(unittest.makeSuite(TestTimetable))
    suite.addTest(unittest.makeSuite(TestTimetableDay))
    suite.addTest(unittest.makeSuite(TestTimetableActivity))
    suite.addTest(unittest.makeSuite(TestTimetableEvents))
    suite.addTest(unittest.makeSuite(TestTimetablingPersistence))
    suite.addTest(unittest.makeSuite(TestTimetableDict))
    suite.addTest(unittest.makeSuite(TestSchooldaySlot))
    suite.addTest(unittest.makeSuite(TestSchooldayTemplate))
    suite.addTest(unittest.makeSuite(TestTimetablesAdapter))
    suite.addTest(unittest.makeSuite(TestCompositeTimetables))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
