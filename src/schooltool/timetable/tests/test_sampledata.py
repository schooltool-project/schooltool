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
Unit tests for schooltool.timetable.sampledata

$Id$
"""
import unittest
from pprint import pprint

from zope.interface.verify import verifyObject
from zope.testing import doctest
from zope.app.testing import setup

from schooltool.testing.setup import setupLocalGrants
from schooltool.testing import setup as stsetup
from schooltool.relationship.tests import setUpRelationships


def setUp(test):
    setup.placefulSetUp()


def tearDown(test):
    setup.placefulTearDown()


def doctest_SampleTimetableSchema():
    """A sample data plugin that generates a timetable schema

        >>> from schooltool.timetable.sampledata import SampleTimetableSchema
        >>> from schooltool.sampledata.interfaces import ISampleDataPlugin
        >>> plugin = SampleTimetableSchema()
        >>> verifyObject(ISampleDataPlugin, plugin)
        True

        >>> app = stsetup.setupSchoolToolSite()

    This plugin creates a timetable schema:

        >>> plugin.generate(app, 42)
        >>> len(app['ttschemas'])
        1

    The day ids on the timetable schema and on the timetable model are set:

        >>> schema = app['ttschemas']['simple']
        >>> schema.day_ids
        ['Day 1', 'Day 2', 'Day 3', 'Day 4', 'Day 5', 'Day 6']
        >>> schema.model.timetableDayIds
        ['Day 1', 'Day 2', 'Day 3', 'Day 4', 'Day 5', 'Day 6']

    Let's check the slots in the first day template:

        >>> result = []
        >>> for period in schema.model.dayTemplates['Day 1']:
        ...      print period.tstart, period.duration
        08:00:00 0:55:00
        09:00:00 0:55:00
        10:00:00 0:55:00
        11:00:00 0:55:00
        12:30:00 0:55:00
        13:30:00 1:00:00

    The timetable model has schoolday templates for all days in cycle.

        >>> for day in schema.day_ids:
        ...    result = []
        ...    print day,
        ...    for period in schema[day].keys():
        ...         print period,
        ...    print
        Day 1 A B C D E F
        Day 2 B C D E F A
        Day 3 C D E F A B
        Day 4 D E F A B C
        Day 5 E F A B C D
        Day 6 F A B C D E

    The default timetable schema is set:

        >>> app['ttschemas'].getDefault()
        <schooltool.timetable.schema.TimetableSchema object at ...>

    """


def doctest_SampleTerms():
    """A sample data plugin that creates terms

        >>> from schooltool.timetable.sampledata import SampleTerms
        >>> from schooltool.sampledata.interfaces import ISampleDataPlugin
        >>> plugin = SampleTerms()
        >>> verifyObject(ISampleDataPlugin, plugin)
        True

    This plugin generates two terms:

        >>> app = stsetup.setupSchoolToolSite()
        >>> plugin.generate(app, 42)
        >>> len(app['terms'])
        2

    These terms are 90 schooldays long:

        >>> fall = app['terms']['2005-fall']
        >>> schooldays = [day for day in fall if fall.isSchoolday(day)]
        >>> len(schooldays)
        90

        >>> spring = app['terms']['2006-spring']
        >>> schooldays = [day for day in spring if spring.isSchoolday(day)]
        >>> len(schooldays)
        90

    They span these dates:

        >>> print fall.first, fall.last
        2005-08-22 2005-12-23
        >>> print spring.first, spring.last
        2006-01-26 2006-05-31

    """


def test_suite():
    return unittest.TestSuite([
        doctest.DocTestSuite(setUp=setUp, tearDown=tearDown,
                             optionflags=doctest.ELLIPSIS),
        ])


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
