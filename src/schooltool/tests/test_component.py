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
Unit tests for schooltool.component

$Id$
"""

import unittest
from sets import Set
from zope.interface import Interface, implements, directlyProvides
from zope.interface.verify import verifyObject
from schooltool.interfaces import ISpecificURI, IRelatable, IQueryLinks
from schooltool.interfaces import IFacet
from schooltool.tests.utils import LocatableEventTargetMixin
from schooltool.tests.utils import EventServiceTestMixin
from schooltool.tests.utils import RelationshipTestMixin
from schooltool.tests.utils import EqualsSortedMixin

__metaclass__ = type


class I1(Interface):
    def foo():
        pass

class I2(Interface):
    pass

class C1:
    implements(I1)
    def __init__(self, context):
        self.context = context

    def foo(self):
        return "foo"

class TestGetAdapter(unittest.TestCase):

    def setUp(self):
        from schooltool.component import adapterRegistry
        self.reg = adapterRegistry.copy()

    def tearDown(self):
        from schooltool.component import adapterRegistry
        self.adapterRegistry = self.reg

    def test_getAdapter(self):
        from schooltool.component import getAdapter, provideAdapter
        from schooltool.interfaces import ComponentLookupError
        provideAdapter(I1, C1)
        self.assertEqual(getAdapter(object(), I1).foo(), "foo")
        self.assertRaises(ComponentLookupError, getAdapter, object(), I2)

    def test_getAdapter_provided(self):
        from schooltool.component import getAdapter, provideAdapter
        ob = C1(None)
        self.assertEqual(getAdapter(ob, I1), ob)


class TestCanonicalPath(unittest.TestCase):

    def test_api(self):
        from schooltool import component
        from schooltool.interfaces import IContainmentAPI
        verifyObject(IContainmentAPI, component)

    def test_path(self):
        from schooltool.component import getPath
        from schooltool.interfaces import ILocation, IContainmentRoot

        class Stub:
            implements(ILocation)

            def __init__(self, parent, name):
                self.__parent__ = parent
                self.__name__ = name

        a = Stub(None, 'root')
        self.assertRaises(TypeError, getPath, a)
        directlyProvides(a, IContainmentRoot)
        self.assertEqual(getPath(a), '/')
        b = Stub(a, 'foo')
        self.assertEqual(getPath(b), '/foo')
        c = Stub(b, 'bar')
        self.assertEqual(getPath(c), '/foo/bar')


class TestFacetFunctions(unittest.TestCase, EqualsSortedMixin):

    def setUp(self):
        from schooltool.interfaces import IFaceted
        class Stub:
            implements(IFaceted)
            __facets__ = Set()

        class FacetStub:
            implements(IFacet)
            active = False
            owner = None
            __parent__ = None

        self.ob = Stub()
        self.facet = FacetStub()
        self.facetclass = FacetStub

    def test_api(self):
        from schooltool import component
        from schooltool.interfaces import IFacetAPI
        verifyObject(IFacetAPI, component)

    def test_setFacet_removeFacet(self):
        from schooltool.component import setFacet, removeFacet
        owner_marker = object()
        self.facet.owner = owner_marker
        self.assertRaises(TypeError, setFacet, self.ob, object())
        setFacet(self.ob, self.facet)
        self.assert_(self.facet.owner is owner_marker)
        self.assert_(self.facet.__parent__ is self.ob)
        self.assert_(self.facet.active)
        self.assert_(self.facet in self.ob.__facets__)
        self.assertRaises(TypeError, setFacet, object(), self.facet)
        removeFacet(self.ob, self.facet)
        self.assert_(self.facet not in self.ob.__facets__)

        owner = object()
        setFacet(self.ob, self.facet, owner=owner)
        self.assert_(self.facet.owner is owner)

    def test_iterFacets(self):
        from schooltool.component import iterFacets
        self.ob.__facets__.add(self.facet)
        self.assertEqual(list(iterFacets(self.ob)), [self.facet])
        self.assertRaises(TypeError, iterFacets, object())

    def test_facetsByOwner(self):
        from schooltool.component import facetsByOwner
        owner_marker = object()
        self.assertEqual(list(facetsByOwner(self.ob, owner_marker)), [])
        facet1 = self.facetclass()
        facet1.owner = owner_marker
        facet2 = self.facetclass()
        facet3 = self.facetclass()
        facet3.owner = owner_marker
        self.ob.__facets__.add(facet1)
        self.ob.__facets__.add(facet2)
        self.ob.__facets__.add(facet3)
        self.assertEqualSorted(list(facetsByOwner(self.ob, owner_marker)),
                               [facet1, facet3])

class TestServiceAPI(unittest.TestCase):

    def test_api(self):
        from schooltool import component
        from schooltool.interfaces import IServiceAPI
        verifyObject(IServiceAPI, component)

    def test_getEventService(self):
        from schooltool.component import getEventService
        from schooltool.interfaces import IServiceManager, ILocation
        from schooltool.interfaces import ComponentLookupError

        class RootStub:
            implements(IServiceManager)
            eventService = object()

        class ObjectStub:
            implements(ILocation)

            def __init__(self, parent, name='foo'):
                self.__parent__ = parent
                self.__name__ = name

        root = RootStub()
        a = ObjectStub(root)
        b = ObjectStub(a)
        cloud = ObjectStub(None)

        self.assertEquals(getEventService(root), root.eventService)
        self.assertEquals(getEventService(a), root.eventService)
        self.assertEquals(getEventService(b), root.eventService)
        self.assertRaises(ComponentLookupError, getEventService, cloud)
        self.assertRaises(ComponentLookupError, getEventService, None)


class TestSpecificURI(unittest.TestCase):

    def test_api(self):
        from schooltool import component
        from schooltool.interfaces import IURIAPI
        verifyObject(IURIAPI, component)

    def test_inspectSpecificURI(self):
        from schooltool.component import inspectSpecificURI
        from schooltool.interfaces import ISpecificURI
        self.assertRaises(TypeError, inspectSpecificURI, object())
        self.assertRaises(TypeError, inspectSpecificURI, I1)
        self.assertRaises(TypeError, inspectSpecificURI, ISpecificURI)
        class IURI(ISpecificURI):
            """http://example.com/foo

            Doc text
            """
        uri, doc = inspectSpecificURI(IURI)
        self.assertEqual(uri, "http://example.com/foo")
        self.assertEqual(doc, """Doc text
            """)

        class IURI2(ISpecificURI): """http://example.com/foo"""
        uri, doc = inspectSpecificURI(IURI2)
        self.assertEqual(uri, "http://example.com/foo")
        self.assertEqual(doc, "")

        class IURI3(ISpecificURI): """foo"""
        self.assertRaises(ValueError, inspectSpecificURI, IURI3)

        class IURI4(ISpecificURI):
            """\
            mailto:foo
            """
        uri, doc = inspectSpecificURI(IURI4)
        self.assertEqual(uri, "mailto:foo")
        self.assertEqual(doc, "")

        class IURI5(ISpecificURI):
            """
            mailto:foo
            """
        self.assertRaises(ValueError, inspectSpecificURI, IURI5)

    def test__isURI(self):
        from schooltool.component import isURI
        good = ["http://foo/bar?baz#quux",
                "HTTP://foo/bar?baz#quux",
                "mailto:root",
                ]
        bad = ["2HTTP://foo/bar?baz#quux",
               "\nHTTP://foo/bar?baz#quux",
               "mailto:postmaster ",
               "mailto:postmaster text"
               "nocolon",
               ]
        for string in good:
            self.assert_(isURI(string), string)
        for string in bad:
            self.assert_(not isURI(string), string)


class Relatable(LocatableEventTargetMixin):
    implements(IRelatable, IQueryLinks)

    def __init__(self, parent, name='does not matter'):
        LocatableEventTargetMixin.__init__(self, parent, name)
        self.__links__ = Set()

    def listLinks(self, role):
        return [link for link in self.__links__
                     if link.role.extends(role, False)]

class URISuperior(ISpecificURI):
    """http://army.gov/ns/superior"""

class URICommand(ISpecificURI):
    """http://army.gov/ns/command"""

class URIReport(ISpecificURI):
    """http://army.gov/ns/report"""

class TestRelationships(EventServiceTestMixin, RelationshipTestMixin,
                        unittest.TestCase):

    def setUp(self):
        from schooltool.relationship import setUp as setUpRelationships
        self.setUpRelationshipRegistry()
        setUpRelationships()
        self.setUpEventService()

    def test_api(self):
        from schooltool import component
        from schooltool.interfaces import IRelationshipAPI
        verifyObject(IRelationshipAPI, component)

    def tearDown(self):
        self.tearDownRelationshipRegistry()

    def test_getRelatedObjects(self):
        from schooltool.component import getRelatedObjects, relate
        officer = Relatable(self.serviceManager)
        soldier = Relatable(self.serviceManager)
        self.assertEqual(list(getRelatedObjects(officer, URIReport)), [])

        relate(URICommand, (officer, URISuperior), (soldier, URIReport))
        self.assertEqual(list(getRelatedObjects(officer, URIReport)),
                         [soldier])
        self.assertEqual(list(getRelatedObjects(officer, URISuperior)), [])

    def test_relate_and_registry(self):
        from schooltool.component import registerRelationship
        from schooltool.component import resetRelationshipRegistry
        from schooltool.component import getRelationshipHandlerFor
        from schooltool.component import relate
        from schooltool.interfaces import ISpecificURI, ComponentLookupError

        class URISomething(ISpecificURI):
            """http://ns.example.com/something"""

        def stub(*args, **kw):
            return ('stub', args, kw)

        def stub2(*args, **kw):
            return ('stub2', args, kw)

        resetRelationshipRegistry()
        self.assertRaises(ComponentLookupError,
                          getRelationshipHandlerFor, ISpecificURI)
        self.assertRaises(ComponentLookupError,
                          getRelationshipHandlerFor, URISomething)

        registerRelationship(ISpecificURI, stub)
        self.assertEquals(getRelationshipHandlerFor(ISpecificURI), stub)
        self.assertEquals(getRelationshipHandlerFor(URISomething), stub)

        registerRelationship(URISomething, stub2)
        self.assertEquals(getRelationshipHandlerFor(ISpecificURI), stub)
        self.assertEquals(getRelationshipHandlerFor(URISomething), stub2)

        # Idempotent
        self.assertRaises(ValueError,
                          registerRelationship, ISpecificURI, stub2)
        registerRelationship(ISpecificURI, stub)

        m, g = object(), object()
        args = (URISomething, (m, URISomething), (g, URISomething))
        self.assertEquals(relate(*args), ('stub2', args, {'title': None}))
        title = 'foo'
        args = (ISpecificURI, (m, URISomething), (g, URISomething))
        self.assertEquals(relate(title=title, *args),
                          ('stub', args, {'title': title}))


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestGetAdapter))
    suite.addTest(unittest.makeSuite(TestCanonicalPath))
    suite.addTest(unittest.makeSuite(TestFacetFunctions))
    suite.addTest(unittest.makeSuite(TestServiceAPI))
    suite.addTest(unittest.makeSuite(TestSpecificURI))
    suite.addTest(unittest.makeSuite(TestRelationships))
    return suite

if __name__ == '__main__':
    unittest.main()
