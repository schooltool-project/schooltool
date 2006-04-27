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
Timetabling Term views.

$Id$
"""
import datetime
import itertools

from zope.interface import Interface
from zope.schema import TextLine, Date

from zope.app import zapi
from zope.app.container.interfaces import INameChooser
from zope.lifecycleevent import modified
from zope.app.form.browser.add import AddView
from zope.app.form.browser.submit import Update
from zope.app.form.interfaces import WidgetsError
from zope.app.form.utility import getWidgetsData
from zope.app.form.utility import setUpEditWidgets
from zope.publisher.browser import BrowserView

from schooltool.app.browser.app import ContainerView
from schooltool.app.browser.cal import month_names
from schooltool.calendar.utils import parse_date
from schooltool.calendar.utils import next_month, week_start
from schooltool.term.interfaces import ITermContainer, ITerm
from schooltool.term.term import Term

from schooltool import SchoolToolMessage as _


class TermContainerView(ContainerView):
    """Term container view."""

    __used_for__ = ITermContainer

    index_title = _("Terms")
    add_title = _("Add a new term")
    add_url = "new.html"


class ITermForm(Interface):
    """Form schema for ITerm add/edit views."""

    title = TextLine(title=_("Title"))

    first = Date(title=_("Start date"))

    last = Date(title=_("End date"))


class TermView(BrowserView):
    """Browser view for terms."""

    __used_for__ = ITerm

    def calendar(self):
        """Prepare the calendar for display.

        Returns a structure composed of lists and dicts, see `TermRenderer`
        for more details.
        """
        return TermRenderer(self.context).calendar()


class TermEditViewMixin(object):
    """Mixin for Term add/edit views."""

    def _buildTerm(self):
        """Build a Term object from form values.

        Returns None if the form doesn't contain enough information.
        """
        try:
            data = getWidgetsData(self, ITermForm)
        except WidgetsError:
            return None
        try:
            term = Term(data['title'], data['first'], data['last'])
        except ValueError:
            return None # date range invalid
        term.addWeekdays(0, 1, 2, 3, 4, 5, 6)
        holidays = self.request.form.get('holiday', [])
        if not isinstance(holidays, list):
            holidays = [holidays]
        for holiday in holidays:
            try:
                term.remove(parse_date(holiday))
            except ValueError:
                pass # ignore ill-formed or out-of-range dates
        toggle = [n for n in range(7) if ('TOGGLE_%d' % n) in self.request]
        if toggle:
            term.toggleWeekdays(*toggle)
        return term


class TermEditView(BrowserView, TermEditViewMixin):
    """Edit view for terms."""

    __used_for__ = ITerm

    creating = False

    update_status = None

    def __init__(self, context, request):
        BrowserView.__init__(self, context, request)
        setUpEditWidgets(self, ITermForm)

    def title(self):
        title = _("Change Term: $title",
                  mapping={'title': self.context.title})
        return title

    def update(self):
        if self.update_status is not None:
            return self.update_status # We've been called before.
        self.update_status = ''
        self.term = self._buildTerm()
        if self.term is None:
            self.term = self.context
        elif Update in self.request:
            self.context.reset(self.term.first, self.term.last)
            for day in self.term:
                if self.term.isSchoolday(day):
                    self.context.add(day)
            modified(self.context)
            self.update_status = _("Saved changes.")
        return self.update_status

    def calendar(self):
        """Prepare the calendar for display.

        Returns a structure composed of lists and dicts, see `TermRenderer`
        for more details.
        """
        return TermRenderer(self.term).calendar()


class TermAddView(AddView, TermEditViewMixin):
    """Adding view for terms."""

    __used_for__ = ITermContainer

    creating = True

    title = _("New term")

    # Since this view is registered via <browser:page>, and not via
    # <browser:addform>, we need to set up some attributes for AddView.
    schema = ITermForm
    _arguments = ()
    _keyword_arguments = ()
    _set_before_add = ()
    _set_after_add = ()

    def update(self):
        """Process the form."""
        self.term = self._buildTerm()
        return AddView.update(self)

    def create(self):
        """Create the object to be added.

        We already have it, actually -- unless there was an error in the form.
        """
        if self.term is None:
            raise WidgetsError([])
        return self.term

    def add(self, content):
        """Add the object to the term container."""
        chooser = INameChooser(self.context)
        name = chooser.chooseName(None, content)
        self.context[name] = content

    def nextURL(self):
        """Return the location to visit once the term's been added."""
        return zapi.absoluteURL(self.context, self.request)

    def calendar(self):
        """Prepare the calendar for display.

        Returns None if the form doesn't contain enough information.  Otherwise
        returns a structure composed of lists and dicts (see `TermRenderer`
        for more details).
        """
        if self.term is None:
            return None
        return TermRenderer(self.term).calendar()


class TermRenderer(object):
    """Helper for rendering ITerms."""

    first_day_of_week = 0 # Monday  TODO: get from IPersonPreferences

    def __init__(self, term):
        self.term = term

    def calendar(self):
        """Prepare the calendar for display.

        Returns a list of month dicts (see `month`).
        """
        calendar = []
        date = self.term.first
        counter = itertools.count(1)
        while date <= self.term.last:
            start_of_next_month = next_month(date)
            end_of_this_month = start_of_next_month - datetime.date.resolution
            maxdate = min(self.term.last, end_of_this_month)
            calendar.append(self.month(date, maxdate, counter))
            date = start_of_next_month
        return calendar

    def month(self, mindate, maxdate, counter):
        """Prepare one month for display.

        Returns a dict with these keys:

            month   -- title of the month
            year    -- the year number
            weeks   -- a list of week dicts in this month (see `week`)

        """
        assert (mindate.year, mindate.month) == (maxdate.year, maxdate.month)
        weeks = []
        date = week_start(mindate, self.first_day_of_week)
        while date <= maxdate:
            weeks.append(self.week(date, mindate, maxdate, counter))
            date += datetime.timedelta(days=7)
        return {'month': month_names[mindate.month],
                'year': mindate.year,
                'weeks': weeks}

    def week(self, start_of_week, mindate, maxdate, counter):
        """Prepare one week of a Term for display.

        `start_of_week` is the date when the week starts.

        `mindate` and `maxdate` are used to indicate which month (or part of
        the month) interests us -- days in this week that fall outside
        [mindate, maxdate] result in a dict containing None values for all
        keys.

        `counter` is an iterator that returns indexes for days
        (itertools.count(1) is handy for this purpose).

        `term` is an ITerm that indicates which days are schooldays,
        and which are holidays.

        Returns a dict with these keys:

            number  -- week number
            days    -- a list of exactly seven dicts

        Each day dict has the following keys

            date    -- date as a string (YYYY-MM-DD)
            number  -- day of month
                       (None when date is outside [mindate, maxdate])
            index   -- serial number of this day (used in Javascript)
            class   -- CSS class ('holiday' or 'schoolday')
            checked -- True for holidays, False for schooldays
            onclick -- onclick event handler that calls toggle(index)

        """
        # start_of_week will be a Sunday or a Monday.  If it is a Sunday,
        # we want to take the ISO week number of the following Monday.  If
        # it is a Monday, we won't break anything by taking the week number
        # of the following Tuesday.
        week_no = (start_of_week + datetime.date.resolution).isocalendar()[1]
        date = start_of_week
        days = []
        for day in range(7):
            if mindate <= date <= maxdate:
                index = counter.next()
                checked = not self.term.isSchoolday(date)
                css_class = checked and 'holiday' or 'schoolday'
                days.append({'number': date.day, 'class': css_class,
                             'date': date.strftime('%Y-%m-%d'),
                             'index': index, 'checked': checked,
                             'onclick': 'javascript:toggle(%d)' % index})
            else:
                days.append({'number': None, 'class': None, 'index': None,
                             'onclick': None, 'checked': None, 'date': None})
            date += datetime.date.resolution
        return {'number': week_no,
                'days': days}
