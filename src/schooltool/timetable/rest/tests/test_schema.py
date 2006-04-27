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
Unit tests for schooltool.timetable.rest.schema

$Id$
"""
import unittest
from zope.interface import Interface
from zope.interface import directlyProvides
from zope.interface.verify import verifyObject
from zope.publisher.browser import TestRequest
from zope.filerepresentation.interfaces import IFileFactory, IWriteFile
from zope.app.testing import ztapi, setup
from zope.traversing import namespace
from zope.traversing.interfaces import ITraversable
from zope.traversing.interfaces import IContainmentRoot

from schooltool.testing import setup as sbsetup
from schooltool.testing.util import QuietLibxml2Mixin
from schooltool.testing.util import XMLCompareMixin
from schooltool.app.rest.errors import RestError


class TimetableSchemaMixin(QuietLibxml2Mixin):

    schema_xml = """
        <timetable xmlns="http://schooltool.org/ns/timetable/0.1">
          <title>Title</title>
          <timezone name="Europe/Vilnius"/>
          <model factory="SequentialDaysTimetableModel">
            <daytemplate>
              <used when="default" />
              <period id="A" tstart="9:00" duration="60" />
              <period id="C" tstart="9:00" duration="60" />
              <period id="B" tstart="10:00" duration="60" />
              <period id="D" tstart="10:00" duration="60" />
            </daytemplate>
            <daytemplate>
              <used when="Friday Thursday" />
              <period id="A" tstart="8:00" duration="60" />
              <period id="C" tstart="8:00" duration="60" />
              <period id="B" tstart="11:00" duration="60" />
              <period id="D" tstart="11:00" duration="60" />
            </daytemplate>
            <daytemplate>
              <used when="2005-07-07" />
              <period id="A" tstart="8:00" duration="30" />
              <period id="B" tstart="8:30" duration="30" />
              <period id="C" tstart="9:00" duration="30" />
              <period id="D" tstart="9:30" duration="30" />
            </daytemplate>
            <day when="2005-07-08" id="Day 2" />
            <day when="2005-07-09" id="Day 1" />
          </model>
          <day id="Day 1">
            <period id="A" homeroom="">
            </period>
            <period id="B">
            </period>
          </day>
          <day id="Day 2">
            <period id="C">
            </period>
            <period id="D">
            </period>
          </day>
        </timetable>
        """

    schema_without_title_xml = schema_xml.replace("<title>Title</title>", "")

    def setUp(self):
        from schooltool.timetable.interfaces import ITimetableSchemaContainer
        from schooltool.timetable.rest.schema import TimetableSchemaFileFactory
        from schooltool.timetable import SequentialDaysTimetableModel
        from schooltool.timetable import SequentialDayIdBasedTimetableModel
        from schooltool.timetable.interfaces import ITimetableModelFactory

        self.app = sbsetup.createSchoolToolApplication()
        self.schemaContainer = self.app["ttschemas"]

        setup.placelessSetUp()
        setup.setUpTraversal()

        ztapi.provideAdapter(ITimetableSchemaContainer, IFileFactory,
                             TimetableSchemaFileFactory)

        ztapi.provideUtility(ITimetableModelFactory,
                             SequentialDaysTimetableModel,
                             "SequentialDaysTimetableModel")

        ztapi.provideUtility(ITimetableModelFactory,
                             SequentialDayIdBasedTimetableModel,
                             "SequentialDayIdBasedTimetableModel")

        ztapi.provideView(Interface, Interface, ITraversable, 'view',
                          namespace.view)

        directlyProvides(self.schemaContainer, IContainmentRoot)

        self.setUpLibxml2()

    def tearDown(self):
        self.tearDownLibxml2()
        setup.placelessTearDown()

    def createEmptySchema(self):
        from schooltool.timetable.schema import TimetableSchemaDay
        from schooltool.timetable.schema import TimetableSchema
        schema = TimetableSchema(['Day 1', 'Day 2'])
        schema['Day 1'] = TimetableSchemaDay(['A', 'B'], ['A'])
        schema['Day 2'] = TimetableSchemaDay(['C', 'D'])
        schema.title = "A Schema"
        return schema

    def createExtendedSchema(self):
        from schooltool.timetable import SequentialDaysTimetableModel
        from schooltool.timetable import SchooldaySlot, SchooldayTemplate
        from datetime import time, timedelta, date

        tt = self.createEmptySchema()

        tt.timezone = 'Europe/Vilnius'

        hour = timedelta(minutes=60)
        half = timedelta(minutes=30)

        day_template1 = SchooldayTemplate()
        day_template1.add(SchooldaySlot(time(9, 0), hour))
        day_template1.add(SchooldaySlot(time(10, 0), hour))
        day_template1.add(SchooldaySlot(time(9, 0), hour))
        day_template1.add(SchooldaySlot(time(10, 0), hour))

        day_template2 = SchooldayTemplate()
        day_template2.add(SchooldaySlot(time(8, 0), hour))
        day_template2.add(SchooldaySlot(time(11, 0), hour))
        day_template2.add(SchooldaySlot(time(8, 0), hour))
        day_template2.add(SchooldaySlot(time(11, 0), hour))

        tm = SequentialDaysTimetableModel(['Day 1', 'Day 2'],
                                          {None: day_template1,
                                           3: day_template2,
                                           4: day_template2})
        tt.model = tm

        short_template = [
            ('A', SchooldaySlot(time(8, 0), half)),
            ('B', SchooldaySlot(time(8, 30), half)),
            ('C', SchooldaySlot(time(9, 0), half)),
            ('D', SchooldaySlot(time(9, 30), half))]
        tt.model.exceptionDays[date(2005, 7, 7)] = short_template
        tt.model.exceptionDayIds[date(2005, 7, 8)] = 'Day 2'
        tt.model.exceptionDayIds[date(2005, 7, 9)] = 'Day 1'
        return tt


class TestTimetableSchemaView(TimetableSchemaMixin, XMLCompareMixin,
                              unittest.TestCase):

    empty_xml = """
        <timetable xmlns="http://schooltool.org/ns/timetable/0.1">
          <title>A Schema</title>
          <timezone name="Europe/Vilnius"/>
          <model factory="SequentialDaysTimetableModel">
            <daytemplate>
              <used when="2005-07-07"/>
              <period duration="30" id="A" tstart="08:00"/>
              <period duration="30" id="B" tstart="08:30"/>
              <period duration="30" id="C" tstart="09:00"/>
              <period duration="30" id="D" tstart="09:30"/>
            </daytemplate>
            <daytemplate>
              <used when="Friday Thursday"/>
              <period duration="60" tstart="08:00"/>
              <period duration="60" tstart="11:00"/>
            </daytemplate>
            <daytemplate>
              <used when="default"/>
              <period duration="60" tstart="09:00"/>
              <period duration="60" tstart="10:00"/>
            </daytemplate>
            <day when="2005-07-08" id="Day 2" />
            <day when="2005-07-09" id="Day 1" />
          </model>
          <day id="Day 1">
            <period id="A" homeroom="">
            </period>
            <period id="B">
            </period>
          </day>
          <day id="Day 2">
            <period id="C">
            </period>
            <period id="D">
            </period>
          </day>
        </timetable>
        """

    def test_get(self):
        from schooltool.timetable.rest.schema import TimetableSchemaView
        request = TestRequest()
        view = TimetableSchemaView(self.createExtendedSchema(), request)

        result = view.GET()
        self.assertEquals(request.response.getHeader('content-type'),
                          "text/xml; charset=UTF-8")
        self.assertEqualsXML(result, self.empty_xml)


class DayIdBasedModelMixin:

    empty_xml = """
        <timetable xmlns="http://schooltool.org/ns/timetable/0.1">
          <title>Title</title>
          <timezone name="UTC"/>
          <model factory="SequentialDayIdBasedTimetableModel">
            <daytemplate>
              <used when="Day 1"/>
              <period duration="60" tstart="08:00"/>
              <period duration="60" tstart="11:00"/>
            </daytemplate>
            <daytemplate>
              <used when="Day 2"/>
              <period duration="60" tstart="09:00"/>
              <period duration="60" tstart="10:00"/>
            </daytemplate>
            <day when="2005-07-08" id="Day 2" />
            <day when="2005-07-09" id="Day 1" />
          </model>
          <day id="Day 1">
            <period id="A" homeroom="">
            </period>
            <period id="B">
            </period>
          </day>
          <day id="Day 2">
            <period id="C">
            </period>
            <period id="D">
            </period>
          </day>
        </timetable>
        """

    def createExtendedSchema(self):
        from schooltool.timetable.schema import TimetableSchemaDay
        from schooltool.timetable.schema import TimetableSchema
        from schooltool.timetable import SequentialDayIdBasedTimetableModel
        from schooltool.timetable import SchooldaySlot, SchooldayTemplate
        from datetime import time, timedelta, date

        tt = TimetableSchema(['Day 1', 'Day 2'])
        tt['Day 1'] = TimetableSchemaDay(['A', 'B'], ['A'])
        tt['Day 2'] = TimetableSchemaDay(['C', 'D'])
        tt.title = "Title"

        hour = timedelta(minutes=60)
        half = timedelta(minutes=30)

        day_template1 = SchooldayTemplate()
        day_template1.add(SchooldaySlot(time(8, 0), hour))
        day_template1.add(SchooldaySlot(time(11, 0), hour))
        day_template1.add(SchooldaySlot(time(8, 0), hour))
        day_template1.add(SchooldaySlot(time(11, 0), hour))

        day_template2 = SchooldayTemplate()
        day_template2.add(SchooldaySlot(time(9, 0), hour))
        day_template2.add(SchooldaySlot(time(10, 0), hour))
        day_template2.add(SchooldaySlot(time(9, 0), hour))
        day_template2.add(SchooldaySlot(time(10, 0), hour))

        tm = SequentialDayIdBasedTimetableModel(['Day 1', 'Day 2'],
                                                {'Day 1': day_template1,
                                                 'Day 2': day_template2})
        tt.model = tm

        tt.model.exceptionDayIds[date(2005, 7, 8)] = 'Day 2'
        tt.model.exceptionDayIds[date(2005, 7, 9)] = 'Day 1'
        return tt


class TestTimetableSchemaViewDayIdBased(DayIdBasedModelMixin,
                                        TestTimetableSchemaView):
    pass


class TestTimetableSchemaFileFactory(TimetableSchemaMixin, unittest.TestCase):

    def test(self):
        from schooltool.timetable.rest.schema import TimetableSchemaFileFactory
        verifyObject(IFileFactory,
                     TimetableSchemaFileFactory(self.schemaContainer))

    def test_call(self):
        factory = IFileFactory(self.schemaContainer)
        self.assertRaises(RestError, factory, "two_day", "text/plain",
                          self.schema_xml)

    def test_parseXML(self):
        factory = IFileFactory(self.schemaContainer)
        schema = factory("two_day", "text/xml", self.schema_without_title_xml)
        self.assertEquals(schema.title, "Schema")
        self.assertEquals(schema, self.createExtendedSchema())

        schema = factory("two_day", "text/xml", self.schema_xml)
        self.assertEquals(schema.title, "Title")
        self.assertEquals(schema, self.createExtendedSchema())

    def test_invalid_name(self):
        from schooltool.app.rest.errors import RestError
        self.assertRaises(RestError, IFileFactory(self.schemaContainer),
                          "foo.bar", "text/xml", self.schema_xml)

    def test_setUpSchemaDays_two_homerooms(self):
        from schooltool.app.rest.errors import RestError
        two_homeroom_schema_xml = self.schema_xml.replace(
            '<period id="B">',
            '<period id="B" homeroom="">')
        factory = IFileFactory(self.schemaContainer)
        schema = factory("two_homeroom", "text/xml", two_homeroom_schema_xml)
        extendend_schema = self.createExtendedSchema()
        extendend_schema.days['Day 1'].homeroom_period_ids = ['A', 'B']
        self.assertEquals(schema, extendend_schema, )


class TestTimetableSchemaFileFactoryDayIdBased(DayIdBasedModelMixin,
                                               TestTimetableSchemaFileFactory):

    schema_xml = DayIdBasedModelMixin.empty_xml

    schema_without_title_xml = schema_xml.replace("<title>Title</title>", "")


class TestTimetableSchemaFile(TimetableSchemaMixin, unittest.TestCase):

    def setUp(self):
        TimetableSchemaMixin.setUp(self)
        self.schemaContainer["two_day"] = self.createEmptySchema()

    def test(self):
        from schooltool.timetable.rest.schema import TimetableSchemaFile
        verifyObject(IWriteFile,
                     TimetableSchemaFile(self.schemaContainer["two_day"]))

    def test_write(self):
        from schooltool.timetable.rest.schema import TimetableSchemaFile
        schema = self.schemaContainer["two_day"]
        schemaFile = TimetableSchemaFile(schema)
        schemaFile.write(self.schema_xml)

        schema = self.schemaContainer["two_day"]
        self.assertEquals(schema.title, "Title")
        self.assertEquals(schema, self.createExtendedSchema())


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(TestTimetableSchemaView))
    suite.addTest(unittest.makeSuite(TestTimetableSchemaViewDayIdBased))
    suite.addTest(unittest.makeSuite(TestTimetableSchemaFileFactory))
    suite.addTest(unittest.makeSuite(TestTimetableSchemaFileFactoryDayIdBased))
    suite.addTest(unittest.makeSuite(TestTimetableSchemaFile))
    return suite

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
