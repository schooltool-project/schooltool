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
Attendance sparkline.

$Id$
"""
__docformat__ = 'reStructuredText'


import StringIO
import datetime
import pytz

from PIL import Image, ImageDraw

from schooltool.app.interfaces import IApplicationPreferences
from schooltool.app.app import getSchoolToolApplication
from schooltool.timetable.interfaces import ICompositeTimetables
from schooltool.term.term import getTermForDate
from schooltool.attendance.interfaces import ISectionAttendance
from schooltool.attendance.interfaces import IHomeroomAttendance


class AttendanceSparkline(object):
    """Attendance sparkline generator.

    Shows the attendance of a given student and a given section for the
    last several school days.
    """

    width = 10  # Minimum number of data points

    # Predefined color palette
    colors = {'black': '#000000', 'red': '#ff0000', 'yellow': '#ffc000'}


    def __init__(self, person, section, date):
        self.person = person
        self.section = section
        self.date = date

    def getLastSchooldays(self):
        """Return last schoolday dates (generator)"""
        date = self.date
        term = getTermForDate(date)
        if not term:
            return
        date -= datetime.date.resolution
        while date >= term.first:
            if term.isSchoolday(date):
                yield date
            date -= datetime.date.resolution

    def getRecordsForDay(self, date):
        """Get all records for ``date`` corresponding to our section."""
        section_attendance = ISectionAttendance(self.person)
        all_records = section_attendance.getAllForDay(date)
        return [record for record in all_records
                if record.section == self.section]

    def getWorstRecordForDay(self, date):
        """Get 'worst' attendance record for day"""
        records = self.getRecordsForDay(date)
        for rec in records:
            if (rec.isAbsent() or rec.isTardy()) and not rec.isExplained():
                return rec
        for rec in records:
            if rec.isAbsent() or rec.isTardy():
                return rec
        for rec in records:
            if rec.isPresent():
                return rec
        return None

    def sectionMeetsOn(self, day, tz, section_calendar):
        """Does a section have a meeting on a given day?

        ``tz`` is the school-wide timezone used to determine when exactly a
        schoolday starts and ends.

        ``section_calendar`` is a calendar containing section meetings
        """
        day_start = tz.localize(datetime.datetime.combine(day, datetime.time()))
        day_end = day_start + datetime.timedelta(1)
        return bool(list(section_calendar.expand(day_start, day_end)))

    def getLastSectionDays(self, count=10):
        section_calendar = ICompositeTimetables(self.section).makeTimetableCalendar()
        timezone = IApplicationPreferences(getSchoolToolApplication()).timezone
        tz = pytz.timezone(timezone)
        result = []
        for day in self.getLastSchooldays():
            if self.sectionMeetsOn(day, tz, section_calendar):
                result.append(day)
                count -= 1
                if count == 0:
                    break
        result.reverse()
        return result

    def getData(self):
        """Get all the data necessary to draw the sparkline.

        Returns list of tuples: (whisker_size, color, sign).
        """
        days = self.getLastSectionDays(self.width)
        hr_attendance = IHomeroomAttendance(self.person)
        data = []
        for day in days:
            section_record = self.getWorstRecordForDay(day)
            hr_period = None
            if section_record:
                hr_period = hr_attendance.getHomeroomPeriodForRecord(section_record)
            if not section_record or section_record.isUnknown():
                data.append(('dot', 'black', '+'))
            elif section_record.isPresent():
                data.append(('full', 'black', '+'))
            elif section_record.isExplained():
                data.append(('full', 'black', '-'))
            elif hr_period.isPresent():
                data.append(('full', 'red', '-'))
            else:
                data.append(('full', 'yellow', '-'))
        return data

    def render(self, height=13, point_width=2, spacing=1):
        """Render sparkline of specified size and return as PIL image."""
        attrs = self.getData()
        number_of_days = len(attrs)
        left_margin = 0
        if number_of_days < self.width:
            left_margin = self.width - number_of_days
        width = (left_margin + number_of_days) * (point_width + spacing)
        image = Image.new('RGB', (width, height), 'white')
        draw = ImageDraw.Draw(image)
        middle = height/2
        for nr, attr in enumerate(attrs):
            size, color_id, sign = attr
            color = self.colors[color_id]
            x = (left_margin + nr) * (point_width + spacing)
            if size == 'dot':
                real_size = 0
            elif size == 'full':
                real_size = height/2
            else:
                real_size = height/4
            if sign == '-':
                draw.rectangle((x, middle, x+point_width-1, middle+real_size),
                               fill=color)
            else:
                draw.rectangle((x, middle, x+point_width-1, middle-real_size),
                               fill=color)
        return image

    def renderAsPngData(self, *args, **kw):
        """Render the sparkline and return PNG data as a string.

        Takes the same arguments as ``render``.
        """
        image = self.render(*args, **kw)
        im_data = StringIO.StringIO()
        image.save(im_data, 'PNG')
        return im_data.getvalue()

