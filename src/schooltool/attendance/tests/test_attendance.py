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
Unit tests for schooltool.attendance.

$Id$
"""
__docformat__ = 'reStructuredText'


import unittest
import datetime
import logging

from pytz import utc, timezone
from persistent import Persistent
from zope.interface import implements, directlyProvides
from zope.interface.verify import verifyObject
from zope.testing import doctest
from zope.app.testing import setup
from zope.app.annotation.interfaces import IAnnotations, IAttributeAnnotatable
from zope.wfmc.interfaces import IParticipant, IProcessDefinition
from zope.component import provideAdapter, provideUtility
from zope.app.testing import ztapi
from zope.security.management import endInteraction
from zope.security.management import newInteraction
from zope.security.management import restoreInteraction
from zope.publisher.browser import TestRequest

import schooltool.app # Dead chicken to appease the circle of import gods
from schooltool.app.interfaces import ISchoolToolApplication
from schooltool.app.interfaces import IApplicationPreferences
from schooltool.person.interfaces import IPerson
from schooltool.calendar.interfaces import ICalendarEvent
from schooltool.attendance.interfaces import IHomeroomAttendance
from schooltool.attendance.interfaces import IHomeroomAttendanceRecord
from schooltool.attendance.interfaces import ISectionAttendance
from schooltool.attendance.interfaces import ISectionAttendanceRecord
from schooltool.attendance.interfaces import UNKNOWN, PRESENT, ABSENT, TARDY
from schooltool.attendance.interfaces import ACCEPTED, REJECTED
from schooltool.attendance.interfaces import AttendanceError
from schooltool.attendance.tests import stubProcessDefinition


#
# Stubs
#

class PersonStub(object):
    implements(IPerson, IAttributeAnnotatable)

    def __init__(self, name=None):
        self.__name__ = name


class SectionStub(object):

    def __init__(self, title=None, name=None):
        self.title = title
        self.__name__ = name

    def __repr__(self):
        if self.title:
            return 'SectionStub(%r)' % self.title
        else:
            return 'SectionStub()'


some_dt = datetime.datetime(2006, 4, 14, 12, 13, tzinfo=utc)


class ExplanationStub(object):
    pass


class AttendanceRecordStub(object):

    def __init__(self, date, status):
        self.date = date
        self.status = status

    def isTardy(self):
        return self.status == TARDY

    def isAbsent(self):
        return self.status == ABSENT

    def makeTardy(self, arrival_time):
        print "made tardy (%s)" % arrival_time

    def addExplanation(self, explanation):
        print "added an explanation"

    def acceptExplanation(self, code):
        print "accepted the explanation"

    def rejectExplanation(self):
        print "rejected the explanation"



class ApplicationStub(object):
    implements(ISchoolToolApplication, IApplicationPreferences)

    timezone = 'UTC'


class ActivityStub(object):

    def workItemFinished(self, work_item, *args):
        print "workItemFinished: %s %r" % (work_item.__class__.__name__, args)


class ParticipantStub(object):
    activity = ActivityStub()


def doctest_getRequestFromInteraction():
    """Tests for getRequestFromInteraction.

        >>> endInteraction()

    If there is no interaction - function returns None:

        >>> from schooltool.attendance.attendance import getRequestFromInteraction
        >>> getRequestFromInteraction() is None
        True


        >>> from zope.app.appsetup.appsetup import SystemConfigurationParticipation
        >>> newInteraction(SystemConfigurationParticipation())
        >>> getRequestFromInteraction() is None
        True

        >>> restoreInteraction()
        >>> endInteraction()

        >>> from zope.publisher.browser import TestRequest
        >>> request = TestRequest()
        >>> newInteraction(request)
        >>> getRequestFromInteraction() is request
        True

        >>> restoreInteraction()

    """


def doctest_AttendanceLoggingProxy():
    """Tests for AttendanceLoggingProxy.

        >>> endInteraction()

        >>> from schooltool.attendance.attendance import AttendanceLoggingProxy
        >>> proxy = AttendanceLoggingProxy("record", "person")
        >>> proxy._getLogger() is logging.getLogger("attendance")
        True

        >>> print proxy.__dict__
        {'person': 'person', 'attendance_record': 'record'}

        >>> proxy._getLoggedInPerson() is None
        True

        >>> request = TestRequest()
        >>> request.setPrincipal(PersonStub(name="Jonas"))
        >>> newInteraction(request)
        >>> proxy._getLoggedInPerson()
        'Jonas'

        >>> restoreInteraction()

    """


class LoggerStub(object):

    def info(self, message):
        # XXX - setting up handlers to the real logger would be
        # cleaner
        print message


def doctest_AttendanceLoggingProxy_logging():
    """Tests for AttendanceLoggingProxy logging facilities.

        >>> from schooltool.attendance.attendance import AttendanceLoggingProxy
        >>> class DummyLogger(AttendanceLoggingProxy):
        ...     def _getLoggedInPerson(self):
        ...         return "john"
        ...     def _getLogger(self):
        ...         return LoggerStub()

        >>> proxy = DummyLogger(AttendanceRecordStub("2005-01-01", ABSENT),
        ...                     PersonStub(name="peter"))
        >>> repr(proxy)
        '<schooltool.attendance.tests.test_attendance.AttendanceRecordStub object at ...>'

        >>> proxy.log("dummy message")
        2...-...-...,
        john,
        <...AttendanceRecordStub object at ...> of peter:
        dummy message

        >>> proxy.addExplanation("explanation")
        added an explanation
        2..., john, <...> of peter: added an explanation

        >>> proxy.acceptExplanation('001')
        accepted the explanation
        2..., john, <...> of peter: accepted explanation

        >>> proxy.rejectExplanation()
        rejected the explanation
        2..., john, <...> of peter: rejected explanation

        >>> proxy.makeTardy("arrival time")
        made tardy (arrival time)
        2..., john, <...> of peter: made attendance record a tardy, arrival time (arrival time)

    """


def doctest_SectionAttendanceLoggingProxy():
    r"""Tests for SectionAttendanceLoggingProxy.

        >>> from schooltool.attendance.attendance import \
        ...     SectionAttendanceLoggingProxy
        >>> proxy = SectionAttendanceLoggingProxy(None, None)

        >>> ISectionAttendanceRecord.providedBy(proxy)
        True

    """


def doctest_HomeroomAttendanceLoggingProxy():
    r"""Tests for HomeroomAttendanceLoggingProxy.

        >>> from schooltool.attendance.attendance import \
        ...     HomeroomAttendanceLoggingProxy
        >>> proxy = HomeroomAttendanceLoggingProxy(None, None)

        >>> IHomeroomAttendanceRecord.providedBy(proxy)
        True

    """


#
# Attendance record classes
#

class FakeProcessDef(object):
    def start(self, arg, person):
        print "starting process for %r" % arg
        print person

directlyProvides(FakeProcessDef, IProcessDefinition)


def doctest_AttendanceRecord():
    """Tests for AttendanceRecord.

        >>> from schooltool.attendance.attendance import AttendanceRecord
        >>> section = SectionStub()
        >>> dt = datetime.datetime(2005, 11, 23, 14, 55, tzinfo=utc)
        >>> ar = AttendanceRecord(section, dt, UNKNOWN, 'person')

        >>> from schooltool.attendance.interfaces import IAttendanceRecord
        >>> verifyObject(IAttendanceRecord, ar)
        True

    """

def doctest_AttendanceRecord_cmp():
    """Tests for AttendanceRecord.__cmp__.

        >>> from schooltool.attendance.attendance import AttendanceRecord
        >>> section = SectionStub()
        >>> dt = datetime.datetime(2005, 11, 23, 14, 55, tzinfo=utc)
        >>> ar = AttendanceRecord(section, dt, UNKNOWN, 'person')

        >>> ar == ar
        True
        >>> ar == AttendanceRecord(section, dt, UNKNOWN, 'person')
        True
        >>> ar == AttendanceRecord(section, dt, ABSENT, 'person')
        False
        >>> ar > AttendanceRecord(section, dt, ABSENT, 'person')
        True

    """


def doctest_AttendanceRecord_createWorkflow():
    """Tests for AttendanceRecord._createWorkflow

        >>> from schooltool.attendance.attendance import AttendanceRecord
        >>> ar = AttendanceRecord(None, some_dt, UNKNOWN, None)

        >>> provideUtility(FakeProcessDef, IProcessDefinition,
        ...                name='schooltool.attendance.explanation')

        >>> ar._createWorkflow('person')
        starting process for <schooltool.attendance.attendance.AttendanceRecord ...>
        person

    """


def doctest_AttendanceRecord_isUnknown_isPresent_isAbsent_isTardy():
    r"""Tests for AttendanceRecord.isSomething functions

        >>> from schooltool.attendance.attendance import AttendanceRecord

        >>> for status in (UNKNOWN, PRESENT, ABSENT, TARDY):
        ...     ar = AttendanceRecord(None, some_dt, UNKNOWN, 'person')
        ...     ar.status = status
        ...     print "%-7s %-5s %-5s %-5s %-5s" % (ar.status,
        ...                 ar.isUnknown(), ar.isPresent(), ar.isAbsent(),
        ...                 ar.isTardy())
        UNKNOWN True  False False False
        PRESENT False True  False False
        ABSENT  False False True  False
        TARDY   False False False True

    """


def doctest_AttendanceRecord_makeTardy():
    r"""Tests for AttendanceRecord.makeTardy

        >>> from schooltool.attendance.attendance import AttendanceRecord

    If you have an absence

        >>> ar = AttendanceRecord(None, some_dt, ABSENT, 'person')
        >>> ar._createWorkflow('person')

    you can convert it to a tardy

        >>> ar.makeTardy(datetime.datetime(2005, 12, 16, 15, 03))

        >>> ar.isTardy()
        True
        >>> ar.late_arrival
        datetime.datetime(2005, 12, 16, 15, 3)

    In all other cases you can't.

        >>> for status in (UNKNOWN, PRESENT, TARDY):
        ...     ar = AttendanceRecord(None, some_dt, UNKNOWN, 'person')
        ...     ar.status = status
        ...     try:
        ...         ar.makeTardy(datetime.datetime(2005, 12, 16, 15, 03))
        ...     except AttendanceError:
        ...         pass
        ...     else:
        ...         print "no AttendanceError when status=%s" % status

    """


def doctest_AttendanceRecord_isExplained_addExplanation():
    r"""Tests for AttendanceRecord.addExplanation

        >>> from schooltool.attendance.attendance import AttendanceRecord

    If you have an absence

        >>> ar = AttendanceRecord(None, some_dt, ABSENT, 'fake person')
        >>> ar._createWorkflow('fake person')

    In the beginning it is not explained:

        >>> ar.isExplained()
        False

    You can add an explanation to it:

        >>> ar.addExplanation("Was ill")
        >>> len(ar.explanations)
        1

    If you have any unprocessed explanations - you can't add another
    one:

        >>> ar.addExplanation("Was very ill")
        Traceback (most recent call last):
          ...
        AttendanceError: you have unprocessed explanations.

    Having explanations in itself does not make the absence explained:

        >>> ar.isExplained()
        False

    However, if explanation is accepted, the workflow will procede
    into AcceptExplanation activity:

        >>> ar.acceptExplanation('001')
        Accepted explanation

    That should set the status of the last explanation to ACCEPTED:

        >>> ar.isExplained()
        True

    There even can be unaccepted and rejected explanations, though we
    will need a new attendance record for that, because we can't add
    explanations to an explained record:

        >>> ar.addExplanation("Dog ate homework")
        Traceback (most recent call last):
          ...
        AttendanceError: can't add an explanation to an explained absence.

    Now with a new record:

        >>> ar = AttendanceRecord(None, some_dt, ABSENT, 'bad pupil')
        >>> ar._createWorkflow('bad pupil')
        >>> ar.addExplanation("Dog ate homework")

    Rejecting it proceeds with the workflow:

        >>> ar.rejectExplanation()
        Rejected explanation

    And sets the status of the last explanation:

        >>> ar.addExplanation("Solar eclipse")
        >>> len(ar.explanations)
        2
        >>> ar.acceptExplanation('001')
        Accepted explanation

    If the record's status is not ABSENT or TARDY, isExplained raises
    an exception:

        >>> ar = AttendanceRecord(None, some_dt, UNKNOWN, 'person')
        >>> ar.isExplained()
        Traceback (most recent call last):
          ...
        AttendanceError: only absences and tardies can be explained.

        >>> ar.status = PRESENT
        >>> ar.isExplained()
        Traceback (most recent call last):
          ...
        AttendanceError: only absences and tardies can be explained.

        >>> ar.status = TARDY
        >>> ar.isExplained()
        False

    Likewise for addExplanation, it is only legal for absences and tardies:

        >>> ar.status = UNKNOWN
        >>> ar.addExplanation("whatever")
        Traceback (most recent call last):
          ...
        AttendanceError: only absences and tardies can be explained.

        >>> ar.status = PRESENT
        >>> ar.addExplanation("whatever")
        Traceback (most recent call last):
          ...
        AttendanceError: only absences and tardies can be explained.

        >>> ar = AttendanceRecord(None, some_dt, ABSENT, 'person')
        >>> ar.status = TARDY
        >>> ar.addExplanation("whatever")
        >>> ar.explanations[-1]
        <schooltool.attendance.attendance.AbsenceExplanation object at ...>

    """


def doctest_AttendanceRecord_accept_reject_explaination():
    r"""Tests for AttendanceRecord.accept/rejectExplanation.

        >>> from schooltool.attendance.attendance import AttendanceRecord
        >>> from schooltool.attendance.interfaces import ABSENT
        >>> ar = AttendanceRecord(None, some_dt, ABSENT, None)

    If there are no explanations, you cannot accept nor reject them.

        >>> ar.acceptExplanation('001')
        Traceback (most recent call last):
          ...
        AttendanceError: there are no outstanding explanations.

        >>> ar.rejectExplanation()
        Traceback (most recent call last):
          ...
        AttendanceError: there are no outstanding explanations.

    """


def doctest_AbsenceExplanation():
    """Absence explanation is a text with a status

        >>> from schooltool.attendance.attendance import AbsenceExplanation
        >>> from schooltool.attendance.attendance import ACCEPTED, REJECTED
        >>> from schooltool.attendance.interfaces import IAbsenceExplanation
        >>> expn = AbsenceExplanation("My dog ate my pants")
        >>> verifyObject(IAbsenceExplanation, expn)
        True

        >>> expn.text
        'My dog ate my pants'

    First the explanation is not accepted and not processed:

        >>> expn.isAccepted()
        False
        >>> expn.isProcessed()
        False

        >>> expn.status
        'NEW'

    If it's status is ACCEPTED it becomes an accepted explanation:

        >>> expn.status = ACCEPTED
        >>> expn.isAccepted()
        True

    And it is marked as a processed explanation:

        >>> expn.isProcessed()
        True

    If not - it is unaccepted explanation:

        >>> expn.status = REJECTED
        >>> expn.isAccepted()
        False
        >>> expn.isProcessed()
        True

    """


def doctest_SectionAttendanceRecord():
    r"""Tests for SectionAttendanceRecord

        >>> from schooltool.attendance.attendance \
        ...     import SectionAttendanceRecord

    Let's create an UNKNOWN record

        >>> section = SectionStub()
        >>> dt = datetime.datetime(2005, 11, 23, 14, 55, tzinfo=utc)
        >>> ar = SectionAttendanceRecord(section, dt, UNKNOWN, 'person')
        >>> verifyObject(ISectionAttendanceRecord, ar)
        True

        >>> isinstance(ar, Persistent)
        True

        >>> ar.status == UNKNOWN
        True
        >>> ar.section == section
        True
        >>> ar.datetime == dt
        True

        >>> ar.duration
        datetime.timedelta(0)
        >>> ar.period_id is None
        True
        >>> ar.late_arrival is None
        True
        >>> ar.explanations
        ()

    Let's create a regular record

        >>> section = SectionStub()
        >>> dt = datetime.datetime(2005, 11, 23, 14, 55, tzinfo=utc)
        >>> duration = datetime.timedelta(minutes=45)
        >>> period_id = 'Period A'
        >>> ar = SectionAttendanceRecord(section, dt, PRESENT, 'person',
        ...                              duration, period_id)

        >>> ar.status == PRESENT
        True
        >>> ar.section == section
        True
        >>> ar.datetime == dt
        True
        >>> ar.duration == duration
        True
        >>> ar.period_id == period_id
        True

        >>> ar.late_arrival is None
        True
        >>> ar.explanations
        ()

    """


def doctest_SectionAttendanceRecord_date():
    r"""Tests for SectionAttendanceRecord

        >>> from schooltool.attendance.attendance \
        ...     import SectionAttendanceRecord

    The date of an attendance record usually matches the date portion of the
    section meeting datetime.

        >>> section = SectionStub()
        >>> dt = datetime.datetime(2005, 11, 23, 14, 55, tzinfo=utc)
        >>> ar = SectionAttendanceRecord(section, dt, UNKNOWN, 'person')
        >>> ar.date == dt.date()
        True

    Sometimes the date portion may differ.  2005-11-23 23:00 UTC is
    2005-11-24 08:00 Tokyo time.  The timezone of the school is determined
    from the application preferences.

        >>> app = ISchoolToolApplication(None)
        >>> IApplicationPreferences(app).timezone = 'Asia/Tokyo'

        >>> dt = datetime.datetime(2005, 11, 23, 23, 00, tzinfo=utc)
        >>> ar = SectionAttendanceRecord(section, dt, UNKNOWN, 'person')
        >>> ar.date
        datetime.date(2005, 11, 24)

    """


def doctest_HomeroomAttendanceRecord():
    r"""Tests for HomeroomAttendanceRecord

        >>> from schooltool.attendance.attendance \
        ...     import HomeroomAttendanceRecord

    Homeroom attendance record acts the same as section attendance
    record does, but has different str, repr and implements a diffrent
    interface:

        >>> from schooltool.attendance.interfaces import IHomeroomAttendanceRecord
        >>> section = SectionStub(name='Art')
        >>> dt = datetime.datetime(2005, 11, 23, 14, 55, tzinfo=utc)
        >>> ar = HomeroomAttendanceRecord(section, dt, UNKNOWN, 'person')
        >>> IHomeroomAttendanceRecord.providedBy(ar)
        True

        >>> str(ar)
        'HomeroomAttendanceRecord(2005-11-23 14:55:00+00:00, UNKNOWN, section=Art)'

        >>> repr(ar)
        'HomeroomAttendanceRecord(SectionStub(),
             datetime.datetime(2005, 11, 23, 14, 55, tzinfo=<UTC>),
             UNKNOWN)'

    """

#
# Attendance storage classes
#

def doctest_AttendanceFilteringMixin_filter():
    r"""Tests for AttendanceFilteringMixin.filter

        >>> d1 = datetime.date(2005, 12, 5)
        >>> d2 = datetime.date(2005, 12, 7)
        >>> d3 = datetime.date(2005, 12, 9)

        >>> dt1 = datetime.datetime(2005, 12, 5, tzinfo=utc)
        >>> dt2 = datetime.datetime(2005, 12, 7, tzinfo=utc)
        >>> dt3 = datetime.datetime(2005, 12, 9, tzinfo=utc)

        >>> from schooltool.attendance.attendance \
        ...         import AttendanceFilteringMixin
        >>> from schooltool.attendance.attendance import SectionAttendanceRecord
        >>> class AttendanceStub(AttendanceFilteringMixin):
        ...     def __iter__(self):
        ...         return iter(SectionAttendanceRecord(None, dt, status, None)
        ...                     for (dt, status) in [(dt1, PRESENT),
        ...                                          (dt2, PRESENT),
        ...                                          (dt2, ABSENT),
        ...                                          (dt3, PRESENT)])

        >>> attendance = AttendanceStub()

        >>> def print_for(first, last):
        ...     for r in attendance.filter(first, last):
        ...         print r.date, r.isPresent()

        >>> print_for(d1, d1)
        2005-12-05 True

        >>> print_for(d1, d2)
        2005-12-05 True
        2005-12-07 True
        2005-12-07 False

        >>> print_for(d2, d3)
        2005-12-07 True
        2005-12-07 False
        2005-12-09 True

        >>> print_for(d1, d3)
        2005-12-05 True
        2005-12-07 True
        2005-12-07 False
        2005-12-09 True

        >>> print_for(d3, d1)

    """


def doctest_AttendanceCalendarMixin_makeCalendar():
    r"""Tests for AttendanceCalendarMixin.makeCalendar

        >>> from schooltool.attendance.attendance \
        ...         import AttendanceCalendarMixin
        >>> class MixinUserStub(AttendanceCalendarMixin):
        ...     def __init__(self):
        ...         self.events = []
        ...     def __iter__(self):
        ...         return iter(self.events)
        ...     def incidentDescription(self, record):
        ...         return "Description"
        >>> acm = MixinUserStub()

    When there are no incidents stored, makeCalendar returns an empty
    ImmutableCalendar:

        >>> cal = acm.makeCalendar()
        >>> cal
        <schooltool.calendar.simple.ImmutableCalendar object at ...>
        >>> list(cal)
        []

    Let's add some incidents:

        >>> dt1a = datetime.datetime(2005, 12, 5, 13, 30)
        >>> dt1b = datetime.datetime(2005, 12, 5, 15, 30)
        >>> dt2a = datetime.datetime(2005, 12, 7, 13, 30)
        >>> dt2b = datetime.datetime(2005, 12, 7, 15, 30)
        >>> dt3a = datetime.datetime(2005, 12, 9, 13, 30)

        >>> r1 = AttendanceRecordStub(dt1a, PRESENT)
        >>> r2 = AttendanceRecordStub(dt2a, PRESENT)
        >>> r3 = AttendanceRecordStub(dt2a, ABSENT)
        >>> r4 = AttendanceRecordStub(dt2b, TARDY)
        >>> r5 = AttendanceRecordStub(dt3a, PRESENT)

        >>> from schooltool.calendar.simple import SimpleCalendarEvent
        >>> acm.events = [r1, r2, r3, r4, r5]
        >>> acm.absenceEventTitle = lambda record: 'Was absent'
        >>> acm.tardyEventTitle = lambda record: 'Was late'
        >>> acm.makeCalendarEvent = lambda r, title, desc: SimpleCalendarEvent(
        ...                             r.date, datetime.timedelta(0), title)

    Now let's inspect the calendar:

        >>> def display():
        ...     def key(event):
        ...         return (event.dtstart, event.title)
        ...     for ev in sorted(acm.makeCalendar(), key=key):
        ...         print ev.dtstart, ev.title

        >>> display()
        2005-12-07 13:30:00+00:00 Was absent
        2005-12-07 15:30:00+00:00 Was late

    """


def doctest_AttendanceCalendarMixin_incidentDescription():
    r"""Tests for AttendanceCalendarMixin.incidentDescription

        >>> from schooltool.attendance.attendance import AttendanceCalendarMixin
        >>> acm = AttendanceCalendarMixin()
        >>> class RecordStub(object):
        ...     def __init__(self, explained):
        ...         self.explained = explained
        ...     def isExplained(self):
        ...         return self.explained

        >>> acm.incidentDescription(RecordStub(False))
        u'Is not explanained yet.'

        >>> acm.incidentDescription(RecordStub(True))
        u'Explanation was accepted.'

    """


def doctest_SectionAttendance():
    """Test for SectionAttendance

        >>> from schooltool.attendance.attendance import SectionAttendance
        >>> person = object()
        >>> sa = SectionAttendance(person)
        >>> sa.person is person
        True
        >>> verifyObject(ISectionAttendance, sa)
        True

        >>> isinstance(sa, Persistent)
        True

    """


def doctest_SectionAttendance_record():
    """Tests for SectionAttendance.record

        >>> from schooltool.attendance.attendance import SectionAttendance
        >>> sa = SectionAttendance(PersonStub())

        >>> len(list(sa))
        0

    Let's record a presence

        >>> section = SectionStub()
        >>> dt = datetime.datetime(2005, 12, 9, 13, 30, tzinfo=utc)
        >>> duration = datetime.timedelta(minutes=45)
        >>> period_id = 'P1'
        >>> sa.record(section, dt, duration, period_id, True)

    We can check that it is there

        >>> len(list(sa))
        1

        >>> ar = sa.get(section, dt)
        >>> ar
        SectionAttendanceRecord(SectionStub(),
                datetime.datetime(2005, 12, 9, 13, 30, tzinfo=<UTC>),
                PRESENT)
        >>> ISectionAttendanceRecord.providedBy(ar)
        True

    It has all the data

        >>> ar.section is section
        True
        >>> ar.datetime == dt
        True
        >>> ar.duration == duration
        True
        >>> ar.period_id == period_id
        True
        >>> ar.status == PRESENT
        True

    Let's record an absence for the same section

        >>> dt = datetime.datetime(2005, 12, 9, 14, 30, tzinfo=utc)
        >>> duration = datetime.timedelta(minutes=30)
        >>> period_id = 'P2'
        >>> sa.record(section, dt, duration, period_id, False)

    We can check that it is there

        >>> len(list(sa))
        2

        >>> ar = sa.get(section, dt)
        >>> ar.section is section
        True
        >>> ar.datetime == dt
        True
        >>> ar.duration == duration
        True
        >>> ar.period_id == period_id
        True
        >>> ar.status == ABSENT
        True

    Let's record a presence for another section at the same time

        >>> section2 = SectionStub()
        >>> sa.record(section2, dt, duration, period_id, True)

        >>> len(list(sa))
        3

        >>> ar = sa.get(section2, dt)
        >>> ar.section is section2
        True

    However we cannot override existing records

        >>> sa.record(section2, dt, duration, period_id, True)
        Traceback (most recent call last):
          ...
        AttendanceError: record for SectionStub() at 2005-12-09 14:30:00+00:00
                         already exists

    """


def doctest_SectionAttendance_get():
    """Tests for SectionAttendance.get

        >>> from schooltool.attendance.attendance import SectionAttendance
        >>> sa = SectionAttendance(PersonStub())

        >>> section1 = SectionStub()
        >>> section2 = SectionStub()
        >>> dt = datetime.datetime(2005, 12, 9, 13, 30, tzinfo=utc)

    If you try to see the attendance record that has never been
    recorded, you get a "null object".

        >>> ar = sa.get(section1, dt)
        >>> ar
        SectionAttendanceRecord(SectionStub(),
                datetime.datetime(2005, 12, 9, 13, 30, tzinfo=<UTC>),
                UNKNOWN)
        >>> ISectionAttendanceRecord.providedBy(ar)
        True
        >>> ar.status == UNKNOWN
        True
        >>> ar.section == section1
        True
        >>> ar.datetime == dt
        True

    Most of the attributes do not make much sense

        >>> ar.duration
        datetime.timedelta(0)
        >>> ar.period_id

    Otherwise you get the correct record for a (section, datetime) pair.

        >>> dt1 = datetime.datetime(2005, 12, 9, 13, 30, tzinfo=utc)
        >>> dt2 = datetime.datetime(2005, 12, 10, 13, 0, tzinfo=utc)
        >>> duration = datetime.timedelta(minutes=50)
        >>> sa.record(section1, dt1, duration, 'P1', True)
        >>> sa.record(section2, dt1, duration, 'P2', False)
        >>> sa.record(section1, dt2, duration, 'P3', False)
        >>> sa.record(section2, dt2, duration, 'P4', True)

        >>> for dt in (dt1, dt2):
        ...     for section in (section1, section2):
        ...         ar = sa.get(section, dt)
        ...         assert ar.section == section
        ...         assert ar.datetime == dt
        ...         print ar.period_id, ar.isPresent()
        P1 True
        P2 False
        P3 False
        P4 True

    Real objects are getting wrapped too:

        >>> type(sa.get(section1, dt1))
        <class 'schooltool.attendance.attendance.SectionAttendanceLoggingProxy'>

    """


def doctest_SectionAttendance_getAllForDay():
    """Tests for SectionAttendance.getAllForDay

        >>> from schooltool.attendance.attendance import SectionAttendance
        >>> sa = SectionAttendance(PersonStub())

        >>> section1 = SectionStub('Math')
        >>> section2 = SectionStub('Chem')
        >>> dt1a = datetime.datetime(2005, 12, 5, 13, 30, tzinfo=utc)
        >>> dt1b = datetime.datetime(2005, 12, 5, 15, 30, tzinfo=utc)
        >>> dt2a = datetime.datetime(2005, 12, 7, 13, 30, tzinfo=utc)
        >>> dt2b = datetime.datetime(2005, 12, 7, 15, 30, tzinfo=utc)
        >>> dt3a = datetime.datetime(2005, 12, 9, 13, 30, tzinfo=utc)
        >>> dt3b = datetime.datetime(2005, 12, 9, 15, 30, tzinfo=utc)
        >>> duration = datetime.timedelta(minutes=45)

        >>> sa.record(section1, dt1a, duration, 'A', True)
        >>> sa.record(section1, dt2a, duration, 'A', True)
        >>> sa.record(section2, dt2a, duration, 'A', False)
        >>> sa.record(section1, dt2b, duration, 'B', False)
        >>> sa.record(section2, dt3a, duration, 'A', True)

        >>> def print_for(day):
        ...     def key(ar):
        ...         return (ar.datetime, ar.section.title)
        ...     for ar in sorted(sa.getAllForDay(day), key=key):
        ...         print ar.date, ar.period_id, ar.section.title, ar.isPresent()

        >>> print_for(dt1a.date())
        2005-12-05 A Math True

        >>> print_for(dt2a.date())
        2005-12-07 A Chem False
        2005-12-07 A Math True
        2005-12-07 B Math False

        >>> print_for(dt3a.date())
        2005-12-09 A Chem True

        >>> print_for(datetime.date(2005, 12, 4))

    """


def doctest_SectionAttendance_tardyEventTitle():
    r"""Tests for SectionAttendance.tardyEventTitle

        >>> from schooltool.attendance.attendance import SectionAttendance
        >>> from schooltool.attendance.attendance \
        ...     import SectionAttendanceRecord
        >>> sa = SectionAttendance(None)

        >>> section = SectionStub(title="Lithomancy")
        >>> dt = datetime.datetime(2005, 11, 23, 14, 55, tzinfo=utc)
        >>> duration = datetime.timedelta(minutes=45)
        >>> period_id = 'Period A'
        >>> ar = SectionAttendanceRecord(section, dt, ABSENT, duration,
        ...                              period_id)
        >>> minutes_late = 14
        >>> ar.makeTardy(dt + datetime.timedelta(minutes=minutes_late))

        >>> print sa.tardyEventTitle(ar)
        Was late for Lithomancy (14 minutes).

    """


def doctest_SectionAttendance_absenceEventTitle():
    r"""Tests for SectionAttendance.absenceEventTitle

        >>> from schooltool.attendance.attendance import SectionAttendance
        >>> from schooltool.attendance.attendance \
        ...     import SectionAttendanceRecord
        >>> sa = SectionAttendance(None)

        >>> section = SectionStub(title="Lithomancy")
        >>> dt = datetime.datetime(2005, 11, 23, 14, 55, tzinfo=utc)
        >>> duration = datetime.timedelta(minutes=45)
        >>> period_id = 'Period A'
        >>> ar = SectionAttendanceRecord(section, dt, ABSENT, duration,
        ...                              period_id)

        >>> print sa.absenceEventTitle(ar)
        Was absent from Lithomancy.

    """


def doctest_SectionAttendance_filter():
    """Tests for SectionAttendance.filter

        >>> from schooltool.attendance.attendance import SectionAttendance
        >>> sa = SectionAttendance(None)

        >>> class BTreeStub(object):
        ...     records = []
        ...     def values(self, **kwargs):
        ...         print sorted(kwargs.items())
        ...         return self.records

        >>> sa._records = BTreeStub()

    Filter uses facilities provided by OOBTree to get the values:

        >>> list(sa.filter(datetime.date(2005, 11, 23),
        ...                datetime.date(2005, 11, 27)))
        [('excludemax', True),
         ('max', datetime.datetime(2005, 11, 28, 0, 0, tzinfo=<UTC>)),
         ('min', datetime.datetime(2005, 11, 23, 0, 0, tzinfo=<UTC>))]
        []

    And then extracts the records themselves:

        >>> sa._records.records = [('record1', 'record2',), ('record3',), ()]
        >>> list(sa.filter(datetime.date(2005, 11, 21),
        ...                datetime.date(2005, 11, 27)))
        [('excludemax', True),
         ('max', datetime.datetime(2005, 11, 28, 0, 0, tzinfo=<UTC>)),
         ('min', datetime.datetime(2005, 11, 21, 0, 0, tzinfo=<UTC>))]
        ['record1', 'record2', 'record3']

    """


def doctest_SectionAttendance_makeCalendarEvent():
    r"""Tests for SectionAttendance.makeCalendarEvent

        >>> from schooltool.attendance.attendance import SectionAttendance
        >>> from schooltool.attendance.attendance \
        ...     import SectionAttendanceRecord
        >>> sa = SectionAttendance(None)

        >>> section = SectionStub()
        >>> dt = datetime.datetime(2005, 11, 23, 14, 55, tzinfo=utc)
        >>> duration = datetime.timedelta(minutes=45)
        >>> period_id = 'Period A'
        >>> ar = SectionAttendanceRecord(section, dt, ABSENT, 'person',
        ...                              duration, period_id)

        >>> ev = sa.makeCalendarEvent(ar, 'John was bad today', 'Very bad')
        >>> ICalendarEvent.providedBy(ev)
        True
        >>> print ev.dtstart, ev.duration, ev.title, ev.description
        2005-11-23 14:55:00+00:00 0:45:00 John was bad today Very bad

    """


def doctest_HomeroomAttendance_wrapRecordForLogging():
    r"""Tests for HomeroomAttendance._wrapRecordForLogging

        >>> from schooltool.attendance.attendance import HomeroomAttendance
        >>> ha = HomeroomAttendance(None)

        >>> from schooltool.attendance.attendance import HomeroomAttendanceRecord
        >>> dt = datetime.datetime(2005, 11, 23, 14, 55, tzinfo=utc)
        >>> ar = HomeroomAttendanceRecord(None, dt, UNKNOWN)

    _wrapRecordForLogging should wrap atendance records in a
    HomeroomAttendanceLoggingProxy:

        >>> proxied_ar = ha._wrapRecordForLogging(ar)
        >>> type(proxied_ar)
        <class 'schooltool.attendance.attendance.HomeroomAttendanceLoggingProxy'>

        >>> proxied_ar.attendance_record is ar
        True

    """


def doctest_HomeroomAttendance_wrapRecordForLogging():
    r"""Tests for HomeroomAttendance.getHomeroomPeriodForRecord.

        >>> from schooltool.attendance.attendance import HomeroomAttendance
        >>> ha = HomeroomAttendance(None)

    getHomeroomPeriodForRecord returns homeroom AR that the given
    section AR belongs to, which means the closest attendance record
    recorded at the same time or before the given section attendance
    record:

        >>> section = SectionStub('History')
        >>> def makeDT(hour, minutes):
        ...     return datetime.datetime(2005, 1, 1, hour, minutes, tzinfo=utc)
        >>> timestamps = [makeDT(hour, 0) for hour in range(10, 14)]

        >>> from schooltool.attendance.attendance import HomeroomAttendanceRecord
        >>> def getAllForDay(self):
        ...     return [HomeroomAttendanceRecord(section, dt, PRESENT, 'p')
        ...             for dt in timestamps]
        >>> ha.getAllForDay = getAllForDay

        >>> from schooltool.attendance.attendance import SectionAttendanceRecord
        >>> ar = SectionAttendanceRecord(section, makeDT(10, 55), PRESENT, 'p')
        >>> str(ha.getHomeroomPeriodForRecord(ar))
        'HomeroomAttendanceRecord(2005-01-01 10:00:00+00:00, PRESENT, section=None)'

        >>> from schooltool.attendance.attendance import SectionAttendanceRecord
        >>> ar = SectionAttendanceRecord(section, makeDT(10, 0), PRESENT, 'p')
        >>> str(ha.getHomeroomPeriodForRecord(ar))
        'HomeroomAttendanceRecord(2005-01-01 10:00:00+00:00, PRESENT, section=None)'

        >>> from schooltool.attendance.attendance import SectionAttendanceRecord
        >>> ar = SectionAttendanceRecord(section, makeDT(11, 0), PRESENT, 'p')
        >>> str(ha.getHomeroomPeriodForRecord(ar))
        'HomeroomAttendanceRecord(2005-01-01 11:00:00+00:00, PRESENT, section=None)'

        >>> from schooltool.attendance.attendance import SectionAttendanceRecord
        >>> ar = SectionAttendanceRecord(section, makeDT(16, 0), PRESENT, 'p')
        >>> str(ha.getHomeroomPeriodForRecord(ar))
        'HomeroomAttendanceRecord(2005-01-01 13:00:00+00:00, PRESENT, section=None)'

    If there is no such record a HomeroomAttendanceRecord with status
    UNKNOWN, matching datetime and the same section is returned:

        >>> ar = SectionAttendanceRecord(section, makeDT(9, 55), PRESENT, 'p')
        >>> str(ha.getHomeroomPeriodForRecord(ar))
        "HomeroomAttendanceRecord(SectionStub('History'),
             datetime.datetime(2005, 1, 1, 9, 55, tzinfo=<UTC>), UNKNOWN)"

    """

#
# Adapters
#

def doctest_getSectionAttendance():
    """Tests for getSectionAttendance.

        >>> setup.setUpAnnotations()
        >>> from schooltool.attendance.attendance import getSectionAttendance
        >>> provideAdapter(getSectionAttendance, [IPerson], ISectionAttendance)

    getSectionAttendance lets us get ISectionAttendance for a person

        >>> person = PersonStub()
        >>> attendance = ISectionAttendance(person)
        >>> attendance
        <schooltool.attendance.attendance.SectionAttendance object at ...>

    The attendance object is stored in person's annotations

        >>> annotations = IAnnotations(person)
        >>> attendance is annotations['schooltool.attendance.SectionAttendance']
        True

    If you adapt more than once, you will get the same object

        >>> attendance is ISectionAttendance(person)
        True

    Attendance object has a reference to the person:

        >>> attendance.person is person
        True

    """


#
# Workflow
#

def doctest_AttendanceAdmin():
    """Tests for AttendanceAdmin.

        >>> from schooltool.attendance.attendance import AttendanceAdmin
        >>> participant = AttendanceAdmin('activity')
        >>> participant.activity
        'activity'

    Well, it does nothing else.  Move along.
    """


def doctest_WaitForExplanation():
    """Tests for WaitForExplanation.

        >>> from schooltool.attendance.attendance import WaitForExplanation
        >>> participant = ParticipantStub()
        >>> work_item = WaitForExplanation(participant)

    When you start the work item, it gets recorded as an attribute of
    the attendance record.

        >>> ar = AttendanceRecordStub(None, None)
        >>> work_item.start(ar)
        >>> ar._work_item is work_item
        True

    One way to complete the work item is to mark a tardy arrival

        >>> late_arrival_time = datetime.datetime(2005, 12, 30, 13, 21)
        >>> work_item.makeTardy(late_arrival_time)
        workItemFinished: WaitForExplanation ('tardy', datetime.datetime(2005, 12, 30, 13, 21), None)

    Another way to complete it is to reject an explanation

        >>> work_item.rejectExplanation()
        workItemFinished: WaitForExplanation ('reject', None, None)

    Or accept it is to reject an explanation

        >>> work_item.acceptExplanation('001')
        workItemFinished: WaitForExplanation ('accept', None, '001')

    """


def doctest_MakeTardy():
    """Tests for MakeTardy.

        >>> from schooltool.attendance.attendance import MakeTardy
        >>> participant = ParticipantStub()
        >>> work_item = MakeTardy(participant)

    When you start the work item, it gets finished in record time

        >>> ar = AttendanceRecordStub(None, None)
        >>> late_arrival_time = datetime.datetime(2005, 12, 30, 13, 21)
        >>> work_item.start(ar, late_arrival_time)
        workItemFinished: MakeTardy ()

    The state of the attendance record changes

        >>> ar.status == TARDY
        True
        >>> ar.late_arrival
        datetime.datetime(2005, 12, 30, 13, 21)

    """


def doctest_AcceptExplanation():
    """Tests for AcceptExplanation.

        >>> from schooltool.attendance.attendance import AcceptExplanation
        >>> participant = ParticipantStub()
        >>> work_item = AcceptExplanation(participant)

    When you start the work item, it gets finished in record time

        >>> ar = AttendanceRecordStub(None, None)
        >>> ar.explanations = [ExplanationStub()]
        >>> work_item.start(ar, '001')
        workItemFinished: AcceptExplanation ()

        >>> ar.explanations[-1].status == ACCEPTED
        True

    """


def doctest_RejectExplanation():
    """Tests for RejectExplanation.

        >>> from schooltool.attendance.attendance import RejectExplanation
        >>> participant = ParticipantStub()
        >>> work_item = RejectExplanation(participant)

    When you start the work item, it gets finished in record time

        >>> ar = AttendanceRecordStub(None, None)
        >>> ar.explanations = [ExplanationStub()]
        >>> work_item.start(ar)
        workItemFinished: RejectExplanation ()

        >>> ar.explanations[-1].status == REJECTED
        True

    """


def doctest_UnresolvedAbsenceCache_add_remove():
    r"""Tests for UnresolvedAbsenceCache.

    Some setup:

        >>> from schooltool.attendance.attendance import UnresolvedAbsenceCache
        >>> from schooltool.attendance.interfaces import \
        ...     IUnresolvedAbsenceCache

    Check the interface:

        >>> cache = UnresolvedAbsenceCache()
        >>> verifyObject(IUnresolvedAbsenceCache, cache)
        True

    The contents are stored in the attribute `_cache`:

        >>> dict(cache._cache.items())
        {}

    Let's test the add and remove operations:

        >>> class StudentStub:
        ...     __name__ = 'student'
        ...     def __repr__(self): return 'student'
        >>> student = StudentStub()
        >>> from schooltool.attendance.interfaces import ABSENT
        >>> class RecordStub:
        ...     status = ABSENT
        ...     def __repr__(self): return 'absence'

    When we add a record, a bucket should be created:

        >>> absence = RecordStub()
        >>> cache.add(student, absence)
        >>> dict(cache._cache.items())
        {'student': [absence]}

    The next record should just append to the list:

        >>> absence2 = RecordStub()
        >>> cache.add(student, absence2)
        >>> dict(cache._cache.items())
        {'student': [absence, absence]}

    Let's check __iter__ on our way:

        >>> list(cache)
        [('student', [absence, absence])]

    Remove works:

        >>> cache.remove(student, absence)
        >>> dict(cache._cache.items())
        {'student': [absence]}

    If no absences are left for a student, the bucket is deleted:

        >>> cache.remove(student, absence2)
        >>> dict(cache._cache.items())
        {}

    """


def doctest_getUnresolvedAbsenceCache():
    r"""Tests for getUnresolvedAbsenceCache.

        >>> setup.setUpAnnotations()
        >>> from schooltool.attendance.attendance import \
        ...     getUnresolvedAbsenceCache

        >>> class Annotatable(object):
        ...     implements(IAttributeAnnotatable)
        >>> adminstub = Annotatable()
        >>> groupstub = {'administrators': adminstub}
        >>> appstub = {'groups': groupstub}

    Now the cache does not yet exist in annotations:

        >>> IAnnotations(adminstub)
        {}

    But if we ask for one, it will be created:

        >>> cache = getUnresolvedAbsenceCache(appstub)

        >>> IAnnotations(adminstub)
        {'schooltool.attendance.absencecache':
           <...attendance.UnresolvedAbsenceCache ...>}

        >>> from schooltool.attendance.interfaces import \
        ...     IUnresolvedAbsenceCache
        >>> verifyObject(IUnresolvedAbsenceCache, cache)
        True

        >>> cache2 = getUnresolvedAbsenceCache(appstub)
        >>> cache is cache2
        True

    """


def doctest_add_or_removeAttendanceRecordFromCache():
    r"""Tests for addAttendanceRecordToCache, removeAttendanceRecordFromCache.

    Some setup:

        >>> ztapi.provideAdapter(None, ISchoolToolApplication,
        ...                      lambda none: 'virtual schooltool')
        >>> from schooltool.attendance.interfaces import \
        ...     IUnresolvedAbsenceCache
        >>> class CacheStub(object):
        ...     def __init__(self):
        ...         self._cache = {}
        ...     def add(self, student, record):
        ...         self._cache[record] = student
        ...     def remove(self, student, record):
        ...         del self._cache[record]
        >>> cache = CacheStub()
        >>> def cacheAdapter(app):
        ...     assert app == 'virtual schooltool'
        ...     return cache
        >>> ztapi.provideAdapter(None, IUnresolvedAbsenceCache,
        ...                      cacheAdapter)

        >>> class ARStub(object):
        ...     def __repr__(self): return 'ar'
        >>> ar = ARStub()

    We can get away with this, because the event is not modified:

        >>> pdi = 'schooltool.attendance.explanation'
        >>> class Event(object):
        ...     class process(object):
        ...         process_definition_identifier = pdi
        ...         class workflowRelevantData(object):
        ...             student = 'a student'
        ...             attendanceRecord = ar

        >>> event = Event()

    We can add the record to the cache:

        >>> from schooltool.attendance.attendance import \
        ...     addAttendanceRecordToCache, removeAttendanceRecordFromCache
        >>> addAttendanceRecordToCache(event)

    And it has landed there!

        >>> cache._cache
        {ar: 'a student'}

    Let's test removal too:

        >>> removeAttendanceRecordFromCache(event)

        >>> cache._cache
        {}

    """


def doctest_AttendanceCalendarProvider_getAuthenticatedUser():
    """Tests for AttendanceCalendarProvider._getAuthenticatedUser.

        >>> from schooltool.attendance.attendance import AttendanceCalendarProvider
        >>> from zope.publisher.browser import TestRequest
        >>> request = TestRequest()
        >>> provider = AttendanceCalendarProvider(None, request)

    If principal of the request can't be adapted to IPerson method returns None:

        >>> provider._getAuthenticatedUser() is None
        True

    If the principal can be adapted - it returns the resulting Person:

        >>> ztapi.provideAdapter(None, IPerson, lambda ctx: "IPerson(%s)" % ctx)

        >>> request.setPrincipal("principal")

        >>> print provider._getAuthenticatedUser()
        IPerson(principal)

    """


def doctest_AttendanceCalendarProvider_isLookingAtOwnCalendar():
    """Tests for AttendanceCalendarProvider._isLookingAtOwnCalendar.

    Some set up:

        >>> from schooltool.app.interfaces import ISchoolToolCalendar
        >>> calendar = object()
        >>> ztapi.provideAdapter(None, ISchoolToolCalendar, lambda ctx: calendar)

    If the calendar of the user passed to this function is not the
    same as the context of the provider - the user is looking at the
    calendar of someone else:

        >>> from schooltool.attendance.attendance import AttendanceCalendarProvider
        >>> provider = AttendanceCalendarProvider(None, None)

        >>> provider._isLookingAtOwnCalendar("User")
        False

    If it is the same calendar - the function should return True:

        >>> provider.context = calendar
        >>> provider._isLookingAtOwnCalendar("User")
        True

    """


def doctest_AttendanceCalendarProvider():
    """Tests for AttendanceCalendarProvider.

        >>> from schooltool.attendance.attendance import AttendanceCalendarProvider
        >>> provider = AttendanceCalendarProvider(None, None)

    If there is no principal in the request (no users logged in) -
    attendance calendar is not visible:

        >>> provider._getAuthenticatedUser = lambda: False
        >>> list(provider.getCalendars())
        []

    Let's log someone in:

        >>> provider._getAuthenticatedUser = lambda: "User"

    If user is looking at the calendar of some one else - he will not
    see anything either:

        >>> provider._isLookingAtOwnCalendar = lambda user: False
        >>> list(provider.getCalendars())
        []

    If he is looking at the calendar of his own - his daily and
    section attendance calendars should be in the list (we'll stub
    them first):

        >>> class AttendanceStub(object):
        ...     def __init__(self, name):
        ...         self.name = name
        ...     def makeCalendar(self):
        ...         return "%s" % self.name

        >>> ztapi.provideAdapter(None, ISectionAttendance,
        ...     lambda user: AttendanceStub("SectionAttendance calendar"))

        >>> provider._isLookingAtOwnCalendar = lambda user: True
        >>> list(provider.getCalendars())
        [('SectionAttendance calendar', '#aa0000', '#ff0000')]

    """


def doctest_date_to_schoolday_start():
    """Tests for date_to_schoolday_start.

    Given a date this function should return the datetime of the
    beginning of the day.

        >>> from schooltool.attendance.attendance import date_to_schoolday_start
        >>> date_to_schoolday_start(datetime.date(2005, 1, 1))
        datetime.datetime(2005, 1, 1, 0, 0, tzinfo=<UTC>)

    Application timezone is taken into account.

        >>> app = ISchoolToolApplication(None)
        >>> IApplicationPreferences(app).timezone = 'Europe/Vilnius'
        >>> date_to_schoolday_start(datetime.date(2005, 1, 1))
        datetime.datetime(2005, 1, 1, 0, 0,
            tzinfo=<DstTzInfo 'Europe/Vilnius' EET+2:00:00 STD>)

    """


def doctest_date_to_schoolday_end():
    """Tests for date_to_schoolday_end.

    Given a date, returns the datetime of the end of the day.

        >>> from schooltool.attendance.attendance import date_to_schoolday_end
        >>> date_to_schoolday_end(datetime.date(2005, 1, 1))
        datetime.datetime(2005, 1, 2, 0, 0, tzinfo=<UTC>)

    Takes application timezone into account.

        >>> app = ISchoolToolApplication(None)
        >>> IApplicationPreferences(app).timezone = 'Europe/Vilnius'
        >>> date_to_schoolday_end(datetime.date(2005, 1, 1))
        datetime.datetime(2005, 1, 2, 0, 0,
            tzinfo=<DstTzInfo 'Europe/Vilnius' EET+2:00:00 STD>)

    """


def setUp(test):
    setup.placelessSetUp()
    app = ApplicationStub()
    provideAdapter(lambda x: app, [None], ISchoolToolApplication)
    stubProcessDefinition()
    logging.getLogger('attendance').disabled = True


def tearDown(test):
    setup.placelessTearDown()
    logging.getLogger('attendance').disabled = False


def test_suite():
    optionflags = doctest.NORMALIZE_WHITESPACE | doctest.ELLIPSIS
    return doctest.DocTestSuite(optionflags=optionflags,
                                setUp=setUp, tearDown=tearDown)


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
