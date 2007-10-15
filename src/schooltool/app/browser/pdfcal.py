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
SchoolBell calendar views.

$Id$
"""

import datetime
from cStringIO import StringIO

from zope.component import subscribers
from zope.publisher.browser import BrowserView
from zope.i18n import translate
from zope.security.proxy import removeSecurityProxy
from schooltool.app.interfaces import ISchoolToolCalendar
from schooltool.app.browser import ViewPreferences, same
from schooltool.app.browser.interfaces import ICalendarProvider
from schooltool.calendar.utils import parse_date, week_start
from schooltool.common import SchoolToolMessage as _


global disabled
disabled = True

SANS = 'Arial_Normal'
SANS_OBLIQUE = 'Arial_Italic'
SANS_BOLD = 'Arial_Bold'
SERIF = 'Times_New_Roman'


class PDFCalendarViewBase(BrowserView):
    """The daily view of a calendar in PDF."""

    # We do imports from reportlab locally to avoid a hard dependency.

    __used_for__ = ISchoolToolCalendar

    title = None # override this in subclasses

    pdf_disabled_text = _("PDF support is disabled."
                          "  It can be enabled by your administrator.")

    def pdfdata(self):
        """Return the PDF representation of a calendar."""
        global disabled
        if disabled:
            return translate(self.pdf_disabled_text, context=self.request)

        from reportlab.platypus import SimpleDocTemplate
        if 'date' in self.request:
            date = parse_date(self.request['date'])
        else:
            date = datetime.date.today()

        datafile = StringIO()
        doc = SimpleDocTemplate(datafile)

        self.configureStyles()
        story = self.buildStory(date)
        doc.build(story)

        data = datafile.getvalue()
        self.setUpPDFHeaders(data)
        return data

    def buildStory(self, date):
        """Build a platypus story that draws the PDF report."""
        owner = self.context.__parent__
        story = self.buildPageHeader(owner.title, date)

        self.calendars = self.getCalendars()
        event_tables = self.buildEventTables(date)
        story.extend(event_tables)
        return story

    def getCalendars(self):
        """Get a list of calendars to display."""
        providers = subscribers((self.context, self.request), ICalendarProvider)

        coloured_calendars = []
        for provider in providers:
            coloured_calendars += provider.getCalendars()

        calendars = [calendar for (calendar, color1, color2)
                     in coloured_calendars]
        return calendars

    def configureStyles(self):
        """Store some styles in instance attributes.

        These would be done in the class declaration if we could do a
        global import of ParagraphStyle.
        """
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.enums import TA_CENTER

        self.normal_style = ParagraphStyle(name='Normal', fontName=SANS,
                                           fontsize=10, leading=12)
        self.title_style = ParagraphStyle(name='Title', fontName=SANS_BOLD,
                                          parent=self.normal_style,
                                          fontsize=18, leading=22,
                                          alignment=TA_CENTER, spaceAfter=6)
        self.subtitle_style = ParagraphStyle(name='Subtitle',
                                             parent=self.title_style,
                                             spaceBefore=16)
        self.italic_style = ParagraphStyle(name='Italic',
                                           parent=self.normal_style,
                                           fontName=SANS_OBLIQUE)

    def setUpPDFHeaders(self, data):
        """Set up HTTP headers to serve data as PDF."""
        response = self.request.response
        response.setHeader('Content-Type', 'application/pdf')
        response.setHeader('Content-Length', len(data))
        # We don't really accept ranges, but Acrobat Reader will not show the
        # report in the browser page if this header is not provided.
        response.setHeader('Accept-Ranges', 'bytes')
        # TODO: test reports with Acrobat Reader

    def buildPageHeader(self, owner_title, date):
        """Build a story that constructs the top of the first page."""
        from reportlab.platypus import Paragraph
        from reportlab.lib.units import cm

        title = translate(self.title, context=self.request) % owner_title
        date_title = self.dateTitle(date)

        story = [Paragraph(title.encode('utf-8'), self.title_style),
                 Paragraph(date_title.encode('utf-8'), self.title_style)]
        return story

    def buildDayTable(self, events):
        """Return the platypus table that shows events."""
        from reportlab.platypus import Paragraph
        from reportlab.platypus import Table, TableStyle
        from reportlab.lib import colors
        from reportlab.lib.units import cm

        rows = []
        for event in events:
            if event.allday:
                time_cell_text = translate(_("all day"), context=self.request)
            else:
                start = event.dtstart.astimezone(self.getTimezone())
                dtend = start + event.duration
                time_cell_text = "%s-%s" % (start.strftime('%H:%M'),
                                            dtend.strftime('%H:%M'))
            time_cell = Paragraph(time_cell_text.encode('utf-8'),
                                  self.italic_style)
            text_cell = self.eventInfoCell(event)
            rows.append([time_cell, text_cell])

        tstyle = TableStyle([('BOX', (0, 0), (-1, -1), 0.25, colors.black),
                       ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.black),
                       ('VALIGN', (0, 0), (0, -1), 'TOP')])
        table = Table(rows, colWidths=(2.5 * cm, 16 * cm), style=tstyle)
        return table

    def eventInfoCell(self, event):
        """Return the contents of an event information cell."""
        from reportlab.platypus import Paragraph
        title = event.title.encode('utf-8')
        paragraphs = [Paragraph(title, self.normal_style)]
        if event.description:
            description = event.description.encode('utf-8')
            paragraphs.append(Paragraph(description, self.italic_style))
        if event.location:
            location_template = translate(
                _('Location: %s'), context=self.request)
            location = location_template % event.location
            paragraphs.append(
                Paragraph(location.encode('utf-8'), self.normal_style))
        if event.resources:
            resource_titles = [resource.title for resource in event.resources]
            resource_str_template = translate(_('Booked resources: %s'),
                                              context=self.request)
            resources = resource_str_template % ', '.join(resource_titles)
            paragraphs.append(Paragraph(resources.encode('utf-8'),
                                        self.normal_style))
        tags = self.eventTags(event)
        if tags:
            tags_text = '(' + ', '.join(tags) + ')'
            paragraphs.append(Paragraph(tags_text.encode('utf-8'),
                                        self.normal_style))
        return paragraphs

    def eventTags(self, event):
        tags = []
        if event.recurrence:
            tags.append(translate(_("recurrent"), context=self.request))
        if (not same(event.__parent__, self.context)
            and event.__parent__ is not None):
            # We have an event from an overlaid calendar.
            tag = translate(_('from the calendar of ${calendar_owner}',
                              mapping={'calendar_owner': event.__parent__.__parent__.title}),
                            context=self.request)
            # We assume that event.__parent__ is a Calendar which belongs to
            # an object with a title.
            tags.append(tag)
        return tags

    def getTimezone(self):
        """Return the timezone for the PDF report."""
        prefs = ViewPreferences(self.request)
        return prefs.timezone

    def dayEvents(self, date):
        """Return a list of events that should be shown.

        All-day events are placed in front.
        """
        allday_events = []
        events = []
        tz = self.getTimezone()
        start = tz.localize(datetime.datetime.combine(date, datetime.time(0)))
        end = start + datetime.timedelta(days=1)

        for calendar in self.getCalendars():
            for event in calendar.expand(start, end):
                if (same(event.__parent__, self.context)
                      and not same(calendar, self.context)):
                    # We may have overlaid resource booking events appearing
                    # twice (once for self.context and another time for the
                    # other calendar).  We can recognize such dupes by
                    # checking that their __parent__ does not match the
                    # calendar they are coming from.
                    continue
                if event.allday:
                    allday_events.append(event)
                else:
                    events.append(event)

        allday_events.sort()
        events.sort()
        return allday_events + events

    def daySubtitle(self, date):
        """Return a readable representation of a date.

        This is used in captions for individual days in views that
        span multiple days.
        """
        # avoid recursive imports
        from schooltool.app.browser.cal import day_of_week_names
        day_of_week_msgid = day_of_week_names[date.weekday()]
        day_of_week = translate(day_of_week_msgid, context=self.request)
        return "%s, %s" % (date.isoformat(), day_of_week)

    def buildEventTables(self, date): # override in subclasses
        """Return the story that draws events in the current time period."""
        raise NotImplementedError()

    def dateTitle(self, date): # override in subclasses
        """Return the title for the current time period.

        Used at the top of the page.
        """
        raise NotImplementedError()


class DailyPDFCalendarView(PDFCalendarViewBase):

    title = _("Daily calendar for %s")

    def buildEventTables(self, date):
        events = self.dayEvents(date)
        if events:
            return [self.buildDayTable(events)]
        else:
            return []

    dateTitle = PDFCalendarViewBase.daySubtitle


class WeeklyPDFCalendarView(PDFCalendarViewBase):

    title = _("Weekly calendar for %s")

    def dateTitle(self, date):
        year, week = date.isocalendar()[:2]
        start = week_start(date, 0) # TODO: first_day_of_week
        end = start + datetime.timedelta(weeks=1)
        template = translate(_("Week %d (%s - %s), %d"), context=self.request)
        return template % (week, start, end, year)

    def buildEventTables(self, date):
        from reportlab.platypus import Paragraph
        story = []
        start = week_start(date, 0) # TODO: first_day_of_week
        for weekday in range(7):
            day = start + datetime.timedelta(days=weekday)
            events = self.dayEvents(day)
            if events:
                story.append(Paragraph(self.daySubtitle(day),
                                       self.subtitle_style))
                story.append(self.buildDayTable(events))
        return story


class MonthlyPDFCalendarView(PDFCalendarViewBase):

    title = _("Monthly calendar for %s")

    def dateTitle(self, date):
        # TODO: take format from user preferences
        # avoid recursive import
        from schooltool.app.browser.cal import month_names
        month_name = translate(month_names[date.month], context=self.request)
        return "%s, %d" % (month_name, date.year)

    def buildEventTables(self, date):
        from reportlab.platypus import Paragraph
        story = []
        day = datetime.date(date.year, date.month, 1)
        while day.month == date.month:
            events = self.dayEvents(day)
            if events:
                # XXX bug: daySubtitle returns a Unicode string, platypus wants
                #          UTF-8 -- http://issues.schooltool.org/issue438
                #          When fixing look for other places like this!
                story.append(Paragraph(self.daySubtitle(day),
                                       self.subtitle_style))
                story.append(self.buildDayTable(events))
            day = day + datetime.timedelta(days=1)
        return story


# ------------------
# Font configuration
# ------------------

def registerTTFont(fontname, filename):
    """Register a TrueType font with ReportLab.

    Clears up the incorrect straight-through mappings that ReportLab 1.19
    unhelpfully gives us.
    """
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    import reportlab.lib.fonts

    pdfmetrics.registerFont(TTFont(fontname, filename))
    # For some reason pdfmetrics.registerFont for TrueType fonts explicitly
    # calls addMapping with incorrect straight-through mappings, at least in
    # reportlab version 1.19.  We thus need to stick our dirty fingers in
    # reportlab's internal data structures and undo those changes so that we
    # can call addMapping with correct values.
    key = fontname.lower()
    del reportlab.lib.fonts._tt2ps_map[key, 0, 0]
    del reportlab.lib.fonts._tt2ps_map[key, 0, 1]
    del reportlab.lib.fonts._tt2ps_map[key, 1, 0]
    del reportlab.lib.fonts._tt2ps_map[key, 1, 1]
    del reportlab.lib.fonts._ps2tt_map[key]


# 'Arial' is predefined in ReportLab, so we use 'Arial_Normal'

font_map = {'Arial_Normal': 'arial.ttf',
            'Arial_Bold': 'arialbd.ttf',
            'Arial_Italic': 'ariali.ttf',
            'Arial_Bold_Italic': 'arialbi.ttf',
            'Times_New_Roman': 'times.ttf',
            'Times_New_Roman_Bold': 'timesbd.ttf',
            'Times_New_Roman_Italic': 'timesi.ttf',
            'Times_New_Roman_Bold_Italic': 'timesbi.ttf'}


def setUpMSTTCoreFonts(directory):
    """Set up ReportGen to use MSTTCoreFonts."""
    import reportlab.rl_config
    from reportlab.lib.fonts import addMapping

    ttfpath = reportlab.rl_config.TTFSearchPath
    ttfpath.append(directory)

    reportlab.rl_config.warnOnMissingFontGlyphs = 0

    for font_name, font_file in font_map.items():
        registerTTFont(font_name, font_file)

    addMapping('Arial_Normal', 0, 0, 'Arial_Normal')
    addMapping('Arial_Normal', 0, 1, 'Arial_Italic')
    addMapping('Arial_Normal', 1, 0, 'Arial_Bold')
    addMapping('Arial_Normal', 1, 1, 'Arial_Bold_Italic')

    addMapping('Times_New_Roman', 0, 0, 'Times_New_Roman')
    addMapping('Times_New_Roman', 0, 1, 'Times_New_Roman_Italic')
    addMapping('Times_New_Roman', 1, 0, 'Times_New_Roman_Bold')
    addMapping('Times_New_Roman', 1, 1, 'Times_New_Roman_Bold_Italic')

    global disabled
    disabled = False
