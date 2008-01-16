#
# SchoolTool - common information systems platform for school administration
# Copyright (c) 2004 Shuttleworth Foundation
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
Common utilities (stubs, mixins) for schooltool unit tests.

$Id$
"""
__metaclass__ = type

from StringIO import StringIO

import zope.traversing.namespace
from zope.interface import Interface
from zope.publisher.browser import TestRequest
from zope.app.component.testing import PlacefulSetup
from zope.app.container.interfaces import INameChooser
from zope.app.testing import ztapi, setup
from zope.traversing.interfaces import ITraversable

from schooltool.testing import setup as sbsetup
from schooltool.testing.util import XMLCompareMixin
from schooltool.app.app import SimpleNameChooser
from schooltool.common.xmlparsing import XMLParseError
from schooltool.group.group import Group
from schooltool.group.interfaces import IGroupContainer
from schooltool.group.rest.group import GroupFileFactory, GroupContainerView
from schooltool.resource.interfaces import IResourceContainer
from schooltool.resource.rest.resource import ResourceFileFactory



class ContainerViewTestMixin(XMLCompareMixin):
    """Common code for Container View tests"""

    def setUp(self):
        setup.placefulSetUp()

        from zope.filerepresentation.interfaces import IFileFactory
        ztapi.provideView(Interface, Interface, ITraversable, 'view',
                          zope.traversing.namespace.view)
        ztapi.provideAdapter(IGroupContainer, INameChooser,
                             SimpleNameChooser)
        ztapi.provideAdapter(IGroupContainer, IFileFactory,
                             GroupFileFactory)
        ztapi.provideAdapter(IResourceContainer, IFileFactory,
                             ResourceFileFactory)


        self.app = sbsetup.setUpSchoolToolSite()
        self.groupContainer = self.app['groups']
        self.group = self.app['groups']['root'] = Group("Root group")


    def tearDown(self):
        setup.placefulTearDown()

    def test_post(self, suffix="", view=None,
                  body="""<object xmlns="http://schooltool.org/ns/model/0.1"
                                  title="New Group"/>"""):
        view = GroupContainerView(self.groupContainer,
                                  TestRequest(StringIO(body)))
        result = view.POST()
        response = view.request.response

        self.assertEquals(response.getStatus(), 201)
        self.assertEquals(response._reason, "Created")

        location = response.getHeader('location')
        base = "http://127.0.0.1/groups/"
        self.assert_(location.startswith(base),
                     "%r.startswith(%r) failed" % (location, base))
        name = location[len(base):]
        self.assert_(name in self.app['groups'].keys())
        self.assertEquals(response.getHeader('content-type'),
                          "text/plain; charset=UTF-8")
        self.assert_(location in result)
        return name

    def test_post_with_a_description(self):
        name = self.test_post(body='''
            <object title="New Group"
                    description="A new group"
                    xmlns='http://schooltool.org/ns/model/0.1'/>''')
        self.assertEquals(self.app['groups'][name].title, 'New Group')
        self.assertEquals(self.app['groups'][name].description, 'A new group')
        self.assertEquals(name, 'new-group')

    def test_post_error(self):
        view = GroupContainerView(
            self.groupContainer,
            TestRequest(StringIO('<element title="New Group">')))
        self.assertRaises(XMLParseError, view.POST)


class FileFactoriesSetUp(PlacefulSetup):

    def setUp(self):
        from zope.filerepresentation.interfaces import IFileFactory
        PlacefulSetup.setUp(self)
        ztapi.provideAdapter(IGroupContainer, IFileFactory,
                             GroupFileFactory)
        ztapi.provideAdapter(IResourceContainer, IFileFactory,
                             ResourceFileFactory)


class ApplicationObjectViewTestMixin(ContainerViewTestMixin):

    def setUp(self):
        ContainerViewTestMixin.setUp(self)
        self.personContainer = self.app['persons']
        self.groupContainer = self.app['groups']

    def get(self):
        """Perform a GET of the view being tested."""
        view = self.makeTestView(self.testObject, TestRequest())
        result = view.GET()

        return result, view.request.response
