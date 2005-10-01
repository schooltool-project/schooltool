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
Unit tests for schooltool.app.

$Id$
"""
import unittest

from zope.component import provideAdapter
from zope.interface.verify import verifyObject
from zope.testing import doctest
from zope.app.testing import setup, placelesssetup

from schooltool.testing import setup as sbsetup


def doctest_SchoolToolApplication():
    """SchoolToolApplication

    We need to register an adapter to make the title attribute available:

        >>> placelesssetup.setUp()
        >>> from schooltool.app.app import ApplicationPreferences
        >>> from schooltool.app.interfaces import IApplicationPreferences
        >>> provideAdapter(ApplicationPreferences,
        ...                provides=IApplicationPreferences)

        >>> app = sbsetup.createSchoolToolApplication()

    Let's check that the interface is satisfied:

        >>> from schooltool.app.interfaces import ISchoolToolApplication
        >>> verifyObject(ISchoolToolApplication, app)
        True

        >>> placelesssetup.tearDown()

    The most basic containers should be available:

        >>> from schooltool.person.interfaces import IPersonContainer
        >>> verifyObject(IPersonContainer, app['persons'])
        True

        >>> from schooltool.group.interfaces import IGroupContainer
        >>> verifyObject(IGroupContainer, app['groups'])
        True

        >>> from schooltool.resource.interfaces import IResourceContainer
        >>> verifyObject(IResourceContainer, app['resources'])
        True

        >>> from schooltool.course.interfaces import ICourseContainer
        >>> verifyObject(ICourseContainer, app['courses'])
        True

        >>> from schooltool.course.interfaces import ISectionContainer
        >>> verifyObject(ISectionContainer, app['sections'])
        True

    Our ApplicationPreferences title should be 'SchoolTool' by default:

      >>> setup.setUpAnnotations()
      >>> from schooltool.app.app import getApplicationPreferences
      >>> getApplicationPreferences(app).title
      'SchoolTool'

    """


def doctest_getSchoolToolApplication():
    """Tests for getSchoolToolApplication.

      >>> setup.placelessSetUp()

    Let's say we have a SchoolTool app, which is a site.

      >>> from schooltool.app.app import SchoolToolApplication
      >>> app = SchoolToolApplication()

      >>> from zope.app.component.site import LocalSiteManager
      >>> app.setSiteManager(LocalSiteManager(app))

    If site is not a SchoolToolApplication, we get an error

      >>> from schooltool.app.app import getSchoolToolApplication
      >>> getSchoolToolApplication()
      Traceback (most recent call last):
      ...
      ValueError: can't get a SchoolToolApplication

    If current site is a SchoolToolApplication, we get it:

      >>> from zope.app.component.hooks import setSite
      >>> setSite(app)

      >>> getSchoolToolApplication() is app
      True

      >>> setup.placelessTearDown()
    """


def doctest_LocationResourceVocabulary():
    r"""Tests for location choice vocabulary.

        >>> from schooltool.app.app import LocationResourceVocabulary

    Set up:

        >>> root = setup.placefulSetUp(True)

    We should be able to choose any Resource in the resource container that is
    marked with isLocation.

        >>> app = sbsetup.setupSchoolToolSite()

    There's no potential terms:

        >>> vocab = LocationResourceVocabulary(app['sections'])
        >>> vocab.by_token
        {}

    Now we'll add some resources

        >>> from schooltool.resource.resource import Resource
        >>> import pprint
        >>> app['resources']['room1'] = room1 = Resource("Room 1",
        ...                                               isLocation=True)
        >>> app['resources']['room2'] = room2 = Resource("Room 2",
        ...                                               isLocation=True)
        >>> app['resources']['room3'] = room3 = Resource("Room 3",
        ...                                               isLocation=True)
        >>> app['resources']['printer'] = printer = Resource("Printer")

    All of our rooms are available, but the printer is not.

        >>> vocab = LocationResourceVocabulary(app['sections'])
        >>> pprint.pprint(vocab.by_token)
        {'Room 1': <zope.schema.vocabulary.SimpleTerm object at ...,
         'Room 2': <zope.schema.vocabulary.SimpleTerm object at ...,
         'Room 3': <zope.schema.vocabulary.SimpleTerm object at ...}

    Clean up:

        >>> setup.placefulTearDown()
    """


def test_suite():
    return unittest.TestSuite([
                doctest.DocTestSuite(optionflags=doctest.ELLIPSIS),
                doctest.DocTestSuite('schooltool.app.app',
                                     optionflags=doctest.ELLIPSIS),
                doctest.DocTestSuite('schooltool.app.interfaces',
                                     optionflags=doctest.ELLIPSIS),
                doctest.DocTestSuite('schooltool.app.membership',
                                     optionflags=doctest.ELLIPSIS),
                doctest.DocTestSuite('schooltool.app.overlay',
                                     optionflags=doctest.ELLIPSIS),
                doctest.DocFileSuite('../README.txt',
                                     optionflags=doctest.ELLIPSIS)
           ])


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
