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
Tests for group views.

$Id$
"""

import unittest

from zope.interface import directlyProvides
from zope.publisher.browser import TestRequest
from zope.testing import doctest
from zope.traversing.interfaces import IContainmentRoot
from zope.component import provideAdapter

from schooltool.app.browser.testing import setUp, tearDown
from schooltool.testing import setup


def doctest_GroupListView():
    r"""Test for GroupListView

    We will need a volunteer for this test:

        # XXX: Should use stub
        >>> from schooltool.person.person import Person
        >>> person = Person(u'ignas')

    One requirement: the person has to know where he is.

        >>> app = setup.setUpSchoolToolSite()
        >>> from schooltool.app.interfaces import ISchoolToolApplication
        >>> provideAdapter(lambda context: app, (None,), ISchoolToolApplication)
        >>> app['persons']['ignas'] = person

    We will be testing the person's awareness of the world, so we will
    create some (empty) groups.

        >>> from schooltool.group.group import Group
        >>> world = app['groups']['the_world'] = Group("Others")
        >>> etria = app['groups']['etria'] = Group("Etria")
        >>> pov = app['groups']['pov'] = Group("PoV")
        >>> canonical = app['groups']['canonical'] = Group("Canonical")
        >>> ms = app['groups']['ms'] = Group("The Enemy")

    And we need a table formatter to display our groups:

        >>> from schooltool.table.table import SchoolToolTableFormatter
        >>> from schooltool.table.interfaces import ITableFormatter
        >>> from zope.publisher.interfaces.browser import IBrowserRequest
        >>> provideAdapter(SchoolToolTableFormatter, (None, IBrowserRequest), ITableFormatter)

    Let's create a view for a person:

        >>> from schooltool.group.browser.group import GroupListView
        >>> request = TestRequest()
        >>> view = GroupListView(person, request)
        >>> view.filter = lambda l: l

    Rendering the view does no harm:

        >>> view.update()

    First, all groups the person is not a member of should be listed:

        >>> sorted([g.title for g in view.getAvailableItems()])
        ['Canonical', 'Etria', 'Others', 'PoV', 'The Enemy']

    As well as all groups the person is currently a member of:

        >>> sorted([g.title for g in view.getSelectedItems()])
        []

    Let's tell the person to join PoV:

        >>> request = TestRequest()
        >>> request.form = {'add_item.pov': 'on', 'ADD_ITEMS': 'Apply'}
        >>> view = GroupListView(person, request)
        >>> view.filter = lambda l: l
        >>> view.update()

    He should have joined:

        >>> [group.title for group in person.groups]
        ['PoV']

    Had we decided to make the guy join Etria but then changed our mind:

        >>> request = TestRequest()
        >>> request.form = {'remove_item.pov': 'on', 'add_group.etria': 'on',
        ...                 'CANCEL': 'Cancel'}
        >>> view = GroupListView(person, request)
        >>> view.filter = lambda l: l
        >>> view.update()

    Nothing would have happened!

        >>> [group.title for group in person.groups]
        ['PoV']

    Yet we would find ourselves in the person info page:

        >>> request.response.getStatus()
        302
        >>> request.response.getHeader('Location')
        'http://127.0.0.1/persons/ignas'

    Finally, let's remove him out of PoV for a weekend and add him
    to The World.

        >>> request = TestRequest()
        >>> request.form = {'remove_item.pov': 'on', 'REMOVE_ITEMS': 'Apply'}
        >>> view = GroupListView(person, request)
        >>> view.filter = lambda l: l
        >>> view.update()

    Mission successful:

        >>> [group.title for group in person.groups]
        []

    """


def doctest_MemberListView():
    r"""Test for MemberListView

    We will be (ab)using a group and three test subjects:

        >>> from schooltool.group.group import Group
        >>> pov = Group('PoV')

        # XXX: Use stub implementation
        >>> from schooltool.person.person import Person
        >>> gintas = Person('gintas', 'Gintas')
        >>> ignas = Person('ignas', 'Ignas')
        >>> alga = Person('alga', 'Albertas')

    We need these objects to live in an application:

        >>> app = setup.setUpSchoolToolSite()
        >>> from schooltool.app.interfaces import ISchoolToolApplication
        >>> provideAdapter(lambda context: app, (None,), ISchoolToolApplication)
        >>> app['groups']['pov'] = pov
        >>> app['persons']['gintas'] = gintas
        >>> app['persons']['ignas'] = ignas
        >>> app['persons']['alga'] = alga

    And we need a table formatter to display our persons:

        >>> from schooltool.table.table import SchoolToolTableFormatter
        >>> from schooltool.table.interfaces import ITableFormatter
        >>> from zope.publisher.interfaces.browser import IBrowserRequest
        >>> provideAdapter(SchoolToolTableFormatter, (None, IBrowserRequest), ITableFormatter)

    Let's create a view for our group:

        >>> from schooltool.group.browser.group import MemberViewPersons
        >>> request = TestRequest()
        >>> view = MemberViewPersons(pov, request)
        >>> view.filter = lambda l: l

    Rendering the view does no harm:

        >>> view.update()

    First, all persons should be listed (the page template puts them in
    alphabetical order later):

        >>> sorted([g.title for g in view.getAvailableItems()])
        ['Albertas', 'Gintas', 'Ignas']

    Let's make Ignas a member of PoV:

        >>> request = TestRequest()
        >>> request.form = {'add_item.ignas': 'on', 'ADD_ITEMS': 'Apply'}
        >>> view = MemberViewPersons(pov, request)
        >>> view.filter = lambda l: l
        >>> view.update()

    He should have joined:

        >>> sorted([person.title for person in pov.members])
        ['Ignas']

    We can cancel an action if we want to:

        >>> request = TestRequest()
        >>> request.form = {'add_item.gintas': 'on', 'CANCEL': 'Cancel'}
        >>> view = MemberViewPersons(pov, request)
        >>> view.filter = lambda l: l
        >>> view.update()
        >>> sorted([person.title for person in pov.members])
        ['Ignas']
        >>> request.response.getStatus()
        302
        >>> request.response.getHeader('Location')
        'http://127.0.0.1/groups/pov'

    Let's remove Ignas from PoV (he went home early today);

        >>> request = TestRequest()
        >>> request.form = {'remove_item.ignas': 'on', 'REMOVE_ITEMS': 'Apply'}
        >>> view = MemberViewPersons(pov, request)
        >>> view.filter = lambda l: l
        >>> view.update()

    and add Albert, who came in late and has to work after-hours:

        >>> request = TestRequest()
        >>> request.form = {'add_item.alga': 'on', 'ADD_ITEMS': 'Apply'}
        >>> view = MemberViewPersons(pov, request)
        >>> view.filter = lambda l: l
        >>> view.update()

    Mission accomplished:

        >>> sorted([person.title for person in pov.members])
        ['Albertas']

    Click 'Done' when we are finished and we go back to the group view

        >>> request = TestRequest()
        >>> request.form = {'CANCEL': 'Cancel'}
        >>> view = MemberViewPersons(pov, request)
        >>> view.filter = lambda l: l
        >>> view.update()
        >>> request.response.getStatus()
        302
        >>> request.response.getHeader('Location')
        'http://127.0.0.1/groups/pov'

    TODO: check resource view

    """


def doctest_GroupView():
    r"""Test for GroupView

    Let's create a view for a group:

        >>> from schooltool.group.browser.group import GroupView
        >>> from schooltool.group.group import Group
        >>> group = Group()
        >>> request = TestRequest()
        >>> view = GroupView(group, request)

    Let's relate some objects to our group:

        >>> from schooltool.person.person import Person
        >>> group.members.add(Person(title='First'))
        >>> group.members.add(Person(title='Last'))
        >>> group.members.add(Person(title='Intermediate'))

    Only persons whose title we can see are in the list, so we must
    define an all alowing security checker:

        >>> from zope.security.checker import defineChecker, Checker
        >>> defineChecker(Person,
        ...               Checker({'title': 'zope.Public'},
        ...                       {'title': 'zope.Public'}))

        >>> sorted([person.title for person in view.getPersons()])
        ['First', 'Intermediate', 'Last']

    """


def doctest_GroupAddView():
    r"""Test for GroupAddView

    Adding views in Zope 3 are somewhat unobvious.  The context of an adding
    view is a view named '+' and providing IAdding.

        >>> class AddingStub:
        ...     pass
        >>> context = AddingStub()

    The container to which items will actually be added is accessible as the
    `context` attribute

        >>> from schooltool.group.group import GroupContainer
        >>> container = GroupContainer()
        >>> context.context = container

    ZCML configuration adds some attributes to GroupAddView, namely `schema`,
    'fieldNames', and `_factory`.

        >>> from schooltool.group.browser.group import GroupAddView
        >>> from schooltool.group.interfaces import IGroup
        >>> from schooltool.group.group import Group
        >>> class GroupAddViewForTesting(GroupAddView):
        ...     schema = IGroup
        ...     fieldNames = ('title', 'description')
        ...     _factory = Group

    We can now finally create the view:

        >>> request = TestRequest()
        >>> view = GroupAddViewForTesting(context, request)

    The `nextURL` method tells Zope 3 where you should be redirected after
    successfully adding a group.  We will pretend that `container` is located
    at the root so that absoluteURL(container) returns 'http://127.0.0.1'.

        >>> directlyProvides(container, IContainmentRoot)
        >>> view.nextURL()
        'http://127.0.0.1'

    We can cancel an action if we want to:

        >>> request = TestRequest()
        >>> request.form = {'CANCEL': 'Cancel'}
        >>> view = GroupAddViewForTesting(context, request)
        >>> view.update()
        >>> request.response.getStatus()
        302
        >>> request.response.getHeader('Location')
        'http://127.0.0.1'

    If 'CANCEL' is not present in the request, the view calls inherited
    'update'.  We will use a trick and set update_status to some value to
    short-circuit AddView.update().

        >>> request = TestRequest()
        >>> request.form = {'field.title': 'a_group',
        ...                 'UPDATE_SUBMIT': 'Add'}
        >>> view = GroupAddViewForTesting(context, request)
        >>> view.update_status = 'Just checking'
        >>> view.update()
        'Just checking'

    """


def doctest_GroupEditView():
    r"""Test for GroupEditView

    Let's create a view for editing a group:

        >>> from schooltool.group.browser.group import GroupEditView
        >>> from schooltool.group.group import Group
        >>> from schooltool.group.interfaces import IGroup
        >>> group = Group()
        >>> directlyProvides(group, IContainmentRoot)
        >>> request = TestRequest()

        >>> class TestGroupEditView(GroupEditView):
        ...     schema = IGroup
        ...     fieldNames = ('title', 'description')
        ...     _factory = Group

        >>> view = TestGroupEditView(group, request)

    We should not get redirected if we did not click on apply button:

        >>> request = TestRequest()
        >>> view = TestGroupEditView(group, request)
        >>> view.update()
        ''
        >>> request.response.getStatus()
        599

    After changing name of the group you should get redirected to the group
    list:

        >>> request = TestRequest()
        >>> request.form = {'UPDATE_SUBMIT': 'Apply',
        ...                 'field.title': u'new_title'}
        >>> view = TestGroupEditView(group, request)
        >>> view.update()
        u'Updated on ${date_time}'
        >>> request.response.getStatus()
        302
        >>> request.response.getHeader('Location')
        'http://127.0.0.1'

        >>> group.title
        u'new_title'

    Even if the title has not changed you should get redirected to the group
    list:

        >>> request = TestRequest()
        >>> request.form = {'UPDATE_SUBMIT': 'Apply',
        ...                 'field.title': u'new_title'}
        >>> view = TestGroupEditView(group, request)
        >>> view.update()
        ''
        >>> request.response.getStatus()
        302
        >>> request.response.getHeader('Location')
        'http://127.0.0.1'

        >>> group.title
        u'new_title'

    We should not get redirected if there were errors:

        >>> request = TestRequest()
        >>> request.form = {'UPDATE_SUBMIT': 'Apply',
        ...                 'field.title': u''}
        >>> view = TestGroupEditView(group, request)
        >>> view.update()
        u'An error occurred.'
        >>> request.response.getStatus()
        599

        >>> group.title
        u'new_title'

    We can cancel an action if we want to:

        >>> request = TestRequest()
        >>> request.form = {'CANCEL': 'Cancel'}
        >>> view = TestGroupEditView(group, request)
        >>> view.update()
        >>> request.response.getStatus()
        302
        >>> request.response.getHeader('Location')
        'http://127.0.0.1'

    """

def doctest_GroupCSVImporter():
    r"""Tests for GroupCSVImporter.

    Create a group container and an importer

        >>> from schooltool.group.browser.csvimport import GroupCSVImporter
        >>> from schooltool.group.group import GroupContainer
        >>> container = GroupContainer()
        >>> importer = GroupCSVImporter(container, None)

    Import some sample data

        >>> csvdata='''Group 1, Group 1 Description
        ... Group2
        ... Group3, Group 3 Description, Some extra data'''
        >>> importer.importFromCSV(csvdata)
        True

    Check that the groups exist

        >>> [group for group in container]
        [u'group-1', u'group2', u'group3']

    Check that descriptions were imported properly

        >>> [group.description for group in container.values()]
        ['Group 1 Description', '', 'Group 3 Description']

    """

def doctest_GroupCSVImportView():
    r"""Tests for GroupCSVImportView

    We'll create a group csv import view

        >>> from schooltool.group.browser.csvimport import \
        ...     GroupCSVImportView
        >>> from schooltool.group.group import GroupContainer
        >>> from zope.publisher.browser import TestRequest
        >>> container = GroupContainer()
        >>> request = TestRequest()

    Now we'll try a text import.  Note that the description is not required

        >>> request.form = {
        ...     'csvtext' : 'A Group, The best Group\nAnother Group',
        ...     'charset' : 'UTF-8',
        ...     'UPDATE_SUBMIT': 1}
        >>> view = GroupCSVImportView(container, request)
        >>> view.update()
        >>> [group for group in container]
        [u'a-group', u'another-group']

    If no data is provided, we naturally get an error

        >>> request.form = {'charset' : 'UTF-8', 'UPDATE_SUBMIT': 1}
        >>> view.update()
        >>> view.errors
        [u'No data provided']

    We also get an error if a line starts with a comma (no title)

        >>> request.form = {'csvtext' : ", No title provided here",
        ...                 'charset' : 'UTF-8',
        ...                 'UPDATE_SUBMIT': 1}
        >>> view = GroupCSVImportView(container, request)
        >>> view.update()
        >>> view.errors
        [u'Failed to import CSV text', u'Titles may not be empty']

    """

def doctest_GroupsViewlet():
    r"""Test for GroupsViewlet

    Let's create a viewlet for a person's groups:

        >>> from schooltool.group.browser.group import GroupsViewlet
        >>> from schooltool.person.person import Person

        >>> school = setup.setUpSchoolToolSite()
        >>> persons = school['persons']
        >>> persons['student'] = student = Person("Student")

    We want to display the generic groups a person is part of that aren't
    sections so we have a filter in the view:

        >>> from schooltool.group.group import Group
        >>> tenth_grade = Group(title="Tenth Grade")
        >>> tenth_grade.members.add(student)
        >>> team = Group(title="Sports Team")
        >>> team.members.add(student)
        >>> student_view = GroupsViewlet(student, TestRequest())
        >>> [group.title for group in student_view.memberOf()]
        ['Tenth Grade', 'Sports Team']
    """

def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(doctest.DocTestSuite(setUp=setUp, tearDown=tearDown,
                                       optionflags=doctest.ELLIPSIS|
                                                   doctest.REPORT_NDIFF))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
