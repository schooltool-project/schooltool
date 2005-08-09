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
SchoolTool application views.

$Id$
"""

import csv

from zope.app.container.interfaces import INameChooser
from zope.security.proxy import removeSecurityProxy

from schoolbell.app.browser import csvimport as sb

from schooltool import SchoolToolMessageID as _
from schooltool import getSchoolToolApplication
from schooltool.interfaces import ISectionContainer
from schooltool.app import Person, Section, Course, Group, Resource
from schooltool.timetable import TimetableActivity
from schooltool.timetable.interfaces import ITimetabled

class ImportErrorCollection(object):

    def __init__(self):
        self.generic = []
        self.day_ids = []
        self.periods = []
        self.persons = []
        self.courses = []
        self.sections = []
        self.locations = []
        self.records = []

    def anyErrors(self):
        return bool(self.generic or self.day_ids or self.periods
                    or self.persons or self.courses or self.sections
                    or self.locations or self.records)

    def __repr__(self):
        return "<%s %r>" % (self.__class__.__name__, self.__dict__)


class InvalidCSVError(Exception):
    pass


class TimetableCSVImporter(object):
    """A timetable CSV parser and importer.

    You will most likely want to use the importFromCSV(csvdata) method.

    This class does not use exceptions for handling errors excessively
    because of the nature of error-checking: we want to gather many errors
    in one sweep and present them to the user at once.
    """

    def __init__(self, container, charset=None):
        # XXX It appears that our security declarations are inadequate,
        #     because things break without this removeSecurityProxy.
        self.app = getSchoolToolApplication()
        self.sections = removeSecurityProxy(container)
        self.persons = self.app['persons']
        self.errors = ImportErrorCollection()
        self.charset = charset

    def importSections(self, sections_csv): # TODO: see importFromCSV
        """Import sections from CSV data.

        At the top of the file there should be a header row:

        timetable_schema_id, term_id

        Then an empty line should follow, and the remaining CSV data should
        consist of chunks like this:

        course_id, instructor_id
        day_id, period_id[, location_id]
        day_id, period_id[, location_id]
        ...
        ***
        student_id
        student_id
        ...

        """
        if '\n' not in sections_csv:
            self.errors.generic.append(_("No data provided"))
            raise InvalidCSVError()

        rows = self.parseCSVRows(sections_csv.splitlines())

        if rows[1]:
            self.errors.generic.append(_("Row 2 is not empty"))
            raise InvalidCSVError()

        self.importHeader(rows[0])
        if self.errors.anyErrors():
            raise InvalidCSVError()

        self.importChunks(rows[2:], dry_run=True)
        if self.errors.anyErrors():
            raise InvalidCSVError()

        self.importChunks(rows[2:], dry_run=False)
        if self.errors.anyErrors():
            raise AssertionError('something bad happened while importing CSV'
                                 ' data, aborting transaction.')

    def importChunks(self, rows, dry_run=True):
        """Import chunks separated by empty lines."""
        chunk_start = 0
        for i, row in enumerate(rows):
            if not row:
                if rows[chunk_start]:
                    self.importChunk(rows[chunk_start:i],
                                     chunk_start + 3, dry_run)
                chunk_start = i + 1
        if rows and rows[-1]:
            self.importChunk(rows[chunk_start:], chunk_start + 3, dry_run)

    def importChunk(self, rows, line, dry_run=True):
        """Import a chunk of data that describes a section.

        You should run this method with dry_run=True before trying the
        real thing, or you might get in trouble.
        """
        # TODO: split up this method
        course_id, instructor_id = rows[0]

        course = self.app['courses'].get(course_id, None)
        if course is None:
            self.errors.courses.append(course_id)

        instructor = self.persons.get(instructor_id, None)
        if instructor is None:
            self.errors.persons.append(instructor_id)

        invalid_location = object() # marker
        line_ofs = 1
        periods = []
        finished = False
        for row in rows[1:]:
            line_ofs += 1
            if row == ['***']:
                finished = True
                break
            elif len(row) == 2:
                day_id, period_id = row
                location_id = None
            elif len(row) == 3:
                day_id, period_id, location_id = row
            else:
                err_msg = _('Malformed line ${line_no} (it should contain a'
                            ' day id, a period id and optionally a location'
                            ' id)')
                err_msg.mapping = {'line_no': line + line_ofs - 1}
                self.errors.generic.append(err_msg)
                continue

            # check resource_id
            if location_id:
                try:
                    location = self.app['resources'][location_id]
                except KeyError:
                    if location_id not in self.errors.locations:
                        location = invalid_location
                        self.errors.locations.append(location_id)
            else:
                location = None

            # check day_id
            try:
                ttday = self.ttschema[day_id]
            except KeyError:
                if day_id not in self.errors.day_ids:
                    self.errors.day_ids.append(day_id)
                continue

            # check period_id
            if (period_id not in ttday.periods
                and period_id not in self.errors.periods):
                self.errors.periods.append(period_id)
                continue

            periods.append((day_id, period_id, location))

        if not finished or len(rows) == line_ofs:
            err_msg = _("Incomplete section description on line ${line}")
            err_msg.mapping = {'line': line}
            self.errors.generic.append(err_msg)
            return

        section = self.createSection(course, instructor, periods,
                                     dry_run=dry_run)
        self.importPersons(rows[line_ofs:], section, dry_run=dry_run)

    def createSection(self, course, instructor, periods, dry_run=True):
        """Create a section.

        `periods` is a list of tuples (day_id, period_id, location).
        `location` is a Resource object, or None, in which case no
        resource is booked.

        A title is generated from the titles of `course` and `instructor`.
        If an existing section with the same title is found, it is used instead
        of creating a new one.

        The created section is returned, or None if dry_run is True.
        """
        if dry_run:
            return None

        # Create or pick a section.
        section_title = '%s - %s' % (course.title, instructor.title)
        for sctn in self.app['sections'].values():
            # Look for an existing section with the same title.
            if sctn.title == section_title:
                section = sctn
                break
        else:
            # No existing sections with this title found, create a new one.
            section = Section(title=section_title)
            chooser = INameChooser(self.sections)
            section_name = chooser.chooseName('', section)
            self.sections[section_name] = section

        # Establish links to course and to teacher
        if course not in section.courses:
            section.courses.add(course)
        if instructor not in section.instructors:
            section.instructors.add(instructor)

        # Create a timetable
        timetables = ITimetabled(section).timetables
        timetable_key = ".".join((self.term.__name__, self.ttschema.__name__))
        if timetable_key not in timetables.keys():
            tt = self.ttschema.createTimetable()
            timetables[timetable_key] = tt
        else:
            tt = timetables[timetable_key]

        # Add timetable activities.
        for day_id, period_id, location in periods:
            if location is not None:
                resources = (location, )
            else:
                resources = ()
            act = TimetableActivity(title=course.title, owner=section,
                                    resources=resources)
            tt[day_id].add(period_id, act)

        return section

    def importPersons(self, person_data, section, dry_run=True):
        """Import persons into a section."""
        for row in person_data:
            person_id = row[0]
            try:
                person = self.persons[person_id]
            except KeyError:
                if person_id not in self.errors.persons:
                    self.errors.persons.append(person_id)
            else:
                if not dry_run:
                    if person not in section.members:
                        section.members.add(person)

    def importHeader(self, row):
        """Read the header row of the CSV file.

        Sets self.term and self.ttschema.
        """
        if len(row) != 2:
            self.errors.generic.append(
                    _("The first row of the CSV file must contain"
                      " the term id and the timetable schema id."))
            return

        term_id, ttschema_id = row

        try:
            self.term = self.app['terms'][term_id]
        except KeyError:
            error_msg = _("The term ${term} does not exist.")
            error_msg.mapping = {'term': term_id}
            self.errors.generic.append(error_msg)

        try:
            self.ttschema = self.app['ttschemas'][ttschema_id]
        except KeyError:
            error_msg = _("The timetable schema ${schema} does not exist.")
            error_msg.mapping = {'schema': ttschema_id}
            self.errors.generic.append(error_msg)

    def parseCSVRows(self, rows):
        """Parse rows (a list of strings) in CSV format.

        Returns a list of rows as lists.  Trailing empty cells are discarded.

        rows must be in the encoding specified during construction of
        TimetableCSVImportView; the returned values are in unicode.

        If the provided data is invalid, self.errors.generic will be updated
        and InvalidCSVError will be returned.
        """
        result = []
        reader = csv.reader(rows)
        line = 0
        try:
            while True:
                line += 1
                values = [v.strip() for v in reader.next()]
                if self.charset:
                    values = [unicode(v, self.charset) for v in values]
                # Remove trailing empty cells.
                while values and not values[-1].strip():
                    del values[-1]
                result.append(values)
        except StopIteration:
            return result
        except csv.Error:
            error_msg = _("Error in timetable CSV data, line ${line_no}")
            error_msg.mapping = {'line_no': line}
            self.errors.generic.append(error_msg)
            raise InvalidCSVError()
        except UnicodeError:
            error_msg = _("Conversion to unicode failed in line ${line_no}")
            error_msg.mapping = {'line_no': line}
            self.errors.generic.append(error_msg)
            raise InvalidCSVError()

    def importFromCSV(self, csvdata):
        """Invoke importSections while playing with BaseCSVImportView nicely.

        Currently sb.BaseCSVImportView expects ImporterClass.importFromCSV
        return True on success, False on error.  It would be nicer if it
        caught InvalidCSVErrors instead.  When this refactoring is performed,
        this method may be removed and importSections can be renamed to
        importFromCSV.
        """
        try:
            self.importSections(csvdata)
        except InvalidCSVError:
            return False
        else:
            return True


class TimetableCSVImportView(sb.BaseCSVImportView):
    """Timetable CSV import view."""

    __used_for__ = ISectionContainer

    importer_class = TimetableCSVImporter

    def _presentErrors(self, err):
        if err.generic:
            self.errors.extend(err.generic)

        for key, msg in [
            ('day_ids', _("Day ids not defined in selected schema: ${args}.")),
            ('periods', _("Periods not defined in selected days: ${args}.")),
            ('persons', _("Persons not found: ${args}.")),
            ('courses', _("Courses not found: ${args}.")),
            ('sections', _("Sections not found: ${args}.")),
            ('locations', _("Locations not found: ${args}.")),
            ('records', _("Invalid records: ${args}."))]:
            v = getattr(err, key)
            if v:
                values = ', '.join([unicode(st) for st in v])
                msg.mapping = {'args': values}
                self.errors.append(msg)


class CourseCSVImporter(sb.BaseCSVImporter):
    """Course CSV Importer"""

    factory = Course

    def createAndAdd(self, data, dry_run=True):
        """Create objects and add them to the container."""

        if len(data) < 1:
            self.errors.fields.append(_('Insufficient data provided.'))
            return

        if not data[0]:
            self.errors.fields.append(_('Titles may not be empty'))
            return

        if len(data) > 1:
            description = data[1]
        else:
            description = ''

        obj = self.factory(title=data[0], description=description)
        name = self.chooser.chooseName('', obj)
        if not dry_run:
            self.container[name] = obj


class CourseCSVImportView(sb.BaseCSVImportView):
    """View for Course CSV importer."""

    importer_class = CourseCSVImporter


class GroupCSVImporter(sb.GroupCSVImporter):
    """Group CSV Importer"""

    factory = Group


class GroupCSVImportView(sb.BaseCSVImportView):
    """View for Group CSV importer."""

    importer_class = GroupCSVImporter


class ResourceCSVImporter(sb.ResourceCSVImporter):
    """Resource CSV Importer"""

    factory = Resource


class ResourceCSVImportView(sb.BaseCSVImportView):
    """View for Resource CSV importer."""

    importer_class = ResourceCSVImporter


class PersonCSVImporter(sb.PersonCSVImporter):
    """Person CSV Importer."""

    def createAndAdd(self, data, dry_run=True):
        """Create a Person object and add it to the container.

        Duplicates are reported as errors.  Both username and fullname (title)
        are required.
        """
        if len(data) < 2:
            self.errors.fields.append(_("Insufficient data provided."))
            return

        if not data[0]:
            self.errors.fields.append(_("username may not be empty"))
            return 

        if not data[1]:
            self.errors.fields.append(_("fullname may not be empty"))
            return

        username = data[0]
        if len(data) > 2:
            password = data[2]
        else:
            password = None

        if username in self.container:
            error_msg = _("Duplicate username: ${username}")
            error_msg.mapping = {'username': ', '.join(data)}
            self.errors.fields.append(error_msg)
            return

        obj = Person(username=data[0], title=data[1])

        if password:
            obj.setPassword(password)

        if not dry_run:
            self.container[data[0]] = obj


class PersonCSVImportView(sb.BaseCSVImportView):
    """View for Person CSV importer."""

    importer_class = PersonCSVImporter

