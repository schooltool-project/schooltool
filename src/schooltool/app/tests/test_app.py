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
        >>> from schooltool.app.interfaces import ISchoolToolApplication
        >>> from schooltool.app.interfaces import IApplicationPreferences
        >>> provideAdapter(ApplicationPreferences,
        ...                adapts=[ISchoolToolApplication],
        ...                provides=IApplicationPreferences)

    Let's check that SchoolToolApplication satisfies the interface:

        >>> app = sbsetup.createSchoolToolApplication()

        >>> verifyObject(ISchoolToolApplication, app)
        True

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

    Time settings for application:

        >>> prefs = getApplicationPreferences(app)
        >>> prefs.timezone
        'UTC'

        >>> prefs.dateformat
        '%Y-%m-%d'

        >>> prefs.timeformat
        '%H:%M'

        >>> prefs.weekstart
        0

    Clean up

        >>> placelesssetup.tearDown()

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


def test_suite():
    return unittest.TestSuite([
                doctest.DocTestSuite(optionflags=doctest.ELLIPSIS),
                doctest.DocTestSuite('schooltool.app.app',
                                     optionflags=doctest.ELLIPSIS),
                doctest.DocTestSuite('schooltool.app.interfaces',
                                     optionflags=doctest.ELLIPSIS),
                doctest.DocTestSuite('schooltool.app.membership',
                                     optionflags=doctest.ELLIPSIS),
                doctest.DocFileSuite('../README.txt',
                                     optionflags=doctest.ELLIPSIS)
           ])


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
