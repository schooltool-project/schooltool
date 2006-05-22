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
Unit tests for groups

$Id$
"""

import unittest

from zope.interface import directlyProvides
from zope.interface.verify import verifyObject
from zope.testing import doctest
from zope.app.testing import setup, ztapi
from zope.app.container.contained import ObjectAddedEvent
from zope.traversing.interfaces import IContainmentRoot

from schooltool.testing.util import run_unit_tests


def doctest_GroupContainer():
    """Tests for GroupContainer

        >>> from schooltool.group.interfaces import IGroupContainer
        >>> from schooltool.group.group import GroupContainer
        >>> c = GroupContainer()
        >>> verifyObject(IGroupContainer, c)
        True

    Let's make sure it acts like a proper container should act

        >>> from zope.app.container.tests.test_btree import TestBTreeContainer
        >>> class Test(TestBTreeContainer):
        ...    def makeTestObject(self):
        ...        return GroupContainer()
        >>> run_unit_tests(Test)
    """


def doctest_Group():
    r"""Tests for Group

        >>> from schooltool.group.interfaces import IGroupContained
        >>> from schooltool.group.group import Group
        >>> group = Group()
        >>> verifyObject(IGroupContained, group)
        True

    Groups can have titles and descriptions too

        >>> illuminati = Group(title='Illuminati', description='Secret Group')
        >>> illuminati.title
        'Illuminati'
        >>> illuminati.description
        'Secret Group'
    """


def doctest_addGroupContainerToApplication():
    """Tests for addGroupContainerToApplication

    This test needs annotations, dependencies and traversal

        >>> setup.placelessSetUp()
        >>> setup.setUpAnnotations()
        >>> setup.setUpDependable()
        >>> setup.setUpTraversal()

    addGroupContainerToApplication is a subscriber for IObjectAddedEvent.

        >>> from schooltool.group.group import addGroupContainerToApplication
        >>> from schooltool.app.app import SchoolToolApplication
        >>> app = SchoolToolApplication()
        >>> event = ObjectAddedEvent(app)

    we want app to have a location

        >>> directlyProvides(app, IContainmentRoot)

    When you call the subscriber

        >>> addGroupContainerToApplication(event)

    it adds a container for groups

        >>> app['groups']
        <schooltool.group.group.GroupContainer object at ...>

    and a few built-in groups

        >>> for name, group in sorted(app['groups'].items()):
        ...     print '%-15s %-25s %s' % (name, group.title, group.description)
        administrators  School Administrators     School Administrators.
        clerks          Clerks                    Clerks.
        manager         Site Managers             Manager Group.
        students        Students                  Students.
        teachers        Teachers                  Teachers.

    These new groups are required for the application to function properly.  To
    express that requirement we add explicit dependencies:

        >>> from zope.app.dependable.interfaces import IDependable
        >>> for group in app['groups'].values():
        ...     assert IDependable(group).dependents() == (u'/groups/',)

    Clean up

        >>> setup.placelessTearDown()

    """


def test_suite():
    return unittest.TestSuite([
                doctest.DocTestSuite(optionflags=doctest.ELLIPSIS),
           ])

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
