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
Timetabling Schema views.

$Id$
"""
from zope.i18n import translate
from zope.component import getMultiAdapter
from zope.component import adapts, getUtility, queryUtility
from zope.interface import Interface, implements
from zope.schema import TextLine, Int
from zope.schema.interfaces import RequiredMissing
from zope.intid.interfaces import IIntIds
from zope.app.container.interfaces import INameChooser
from zope.app.form.interfaces import IWidgetInputError
from zope.app.form.interfaces import IInputWidget
from zope.app.form.interfaces import WidgetInputError
from zope.app.form.interfaces import WidgetsError
from zope.app.form.utility import getWidgetsData, setUpWidgets
from zope.app.pagetemplate.viewpagetemplatefile import ViewPageTemplateFile
from zope.publisher.browser import BrowserView
from zope.publisher.interfaces.browser import IBrowserPublisher
from zope.publisher.interfaces.browser import IBrowserRequest
from zope.traversing.browser.interfaces import IAbsoluteURL
from zope.traversing.browser.absoluteurl import absoluteURL

from schooltool.common import SchoolToolMessage as _
from schooltool.skin.containers import ContainerView, ContainerDeleteView
from schooltool.app.interfaces import ISchoolToolApplication
from schooltool.app.interfaces import IApplicationPreferences
from schooltool.timetable import SchooldayTemplate, SchooldaySlot
from schooltool.timetable.interfaces import ITimetableModelFactory
from schooltool.timetable.interfaces import ITimetableSchema
from schooltool.timetable.interfaces import ITimetableSchemaContainer
from schooltool.timetable.schema import TimetableSchema, TimetableSchemaDay
from schooltool.timetable import findRelatedTimetables

from schooltool.timetable.browser import TimetableView, TabindexMixin
from schooltool.timetable.browser import fix_duplicates, parse_time_range
from schooltool.timetable.browser import format_timetable_for_presentation
from schooltool.timetable.browser import format_time_range


class TimetableSchemaContainerAbsoluteURLAdapter(BrowserView):

    adapts(ITimetableSchemaContainer, IBrowserRequest)
    implements(IAbsoluteURL)

    def __str__(self):
        container_id = int(self.context.__name__)
        int_ids = getUtility(IIntIds)
        container = int_ids.getObject(container_id)
        url = str(getMultiAdapter((container, self.request), name='absolute_url'))
        return url + '/school_timetables'

    __call__ = __str__


class TimetableSchemaView(TimetableView):

    __used_for__ = ITimetableSchema

    def homerooms(self):
        """Returns a dictionary of day indexes to homeroom period indexes"""
        result = {}
        for daynr, dayid in enumerate(self.context.keys()):
            day = self.context[dayid]
            result[daynr] = set()
            if day.homeroom_period_ids:
                for periodnr, periodid in enumerate(day.keys()):
                    if periodid in day.homeroom_period_ids:
                        result[daynr].add(periodnr)
        return result

    def title(self):
        msg = _("Timetable schema ${schema}",
                mapping = {'schema': self.context.title})
        return msg

    @property
    def timezone(self):
        """Return a timezone if it is different from app default.

        Return None if it is not.
        """
        app = ISchoolToolApplication(None)
        apptz = IApplicationPreferences(app).timezone
        if self.context.timezone != apptz:
            return self.context.timezone


class SimpleTimetableSchemaAdd(BrowserView):
    """A simple timetable schema definition view"""

    _nrperiods = 9

    day_ids = (_("Monday"),
               _("Tuesday"),
               _("Wednesday"),
               _("Thursday"),
               _("Friday"),
               )

    error = None

    template = ViewPageTemplateFile('templates/simpletts.pt')

    def __init__(self, content, request):
        BrowserView.__init__(self, content, request)
        self._schema = {}
        self._schema['title'] = TextLine(__name__='title', title=_(u"Title"))
        for nr in range(1, self._nrperiods + 1):
            pname = 'period_name_%s' % nr
            pstart = 'period_start_%s' % nr
            pfinish = 'period_finish_%s' % nr
            self._schema[pname] = TextLine(__name__=pname,
                                           title=u"Period title",
                                           required=False)
            self._schema[pstart] = TextLine(__name__=pstart,
                                            title=u"Period start time",
                                            required=False)
            self._schema[pfinish] = TextLine(__name__=pfinish,
                                             title=u"Period finish time",
                                             required=False)
        setUpWidgets(self, self._schema, IInputWidget,
                     initial={'title': 'default'})

    def _setError(self, name, error=RequiredMissing()):
        """Set an error on a widget."""
        # XXX Touching widget._error is bad, see
        #     http://dev.zope.org/Zope3/AccessToWidgetErrors
        # The call to setRenderedValue is necessary because
        # otherwise _getFormValue will call getInputValue and
        # overwrite _error while rendering.
        widget = getattr(self, name + '_widget')
        widget.setRenderedValue(widget._getFormValue())
        if not IWidgetInputError.providedBy(error):
            error = WidgetInputError(name, widget.label, error)
        widget._error = error

    def getPeriods(self):
        try:
            data = getWidgetsData(self, self._schema)
        except WidgetsError:
            return []

        result = []
        for nr in range(1, self._nrperiods + 1):
            pname = 'period_name_%s' % nr
            pstart = 'period_start_%s' % nr
            pfinish = 'period_finish_%s' % nr
            if data.get(pstart) or data.get(pfinish):
                try:
                    start, duration = parse_time_range(
                        "%s-%s" % (data[pstart], data[pfinish]))
                except ValueError:
                    self.error = _('Please use HH:MM format for period '
                                   'start and end times')
                    continue
                name = data[pname]
                if not name:
                    name = data[pstart]
                result.append((name, start, duration))
        return result

    def createSchema(self, periods):
        daytemplate = SchooldayTemplate()
        for title, start, duration in periods:
            daytemplate.add(SchooldaySlot(start, duration))

        factory = getUtility(ITimetableModelFactory, 'WeeklyTimetableModel')
        model = factory(self.day_ids, {None: daytemplate})
        app = ISchoolToolApplication(None)
        tzname = IApplicationPreferences(app).timezone
        schema = TimetableSchema(self.day_ids, timezone=tzname)
        for day_id in self.day_ids:
            schema[day_id] = TimetableSchemaDay(
                [title for title, start, duration in periods])
        schema.model = model
        return schema

    def __call__(self):
        try:
            data = getWidgetsData(self, self._schema)
        except WidgetsError:
            return self.template()

        if 'CANCEL' in self.request:
            self.request.response.redirect(
                absoluteURL(self.context, self.request))
        elif 'CREATE' in self.request:
            periods = self.getPeriods()
            if self.error:
                return self.template()

            if not periods:
                self.error = _('You must specify at least one period.')
                return self.template()

            schema = self.createSchema(periods)
            schema.title = data['title']

            nameChooser = INameChooser(self.context)
            name = nameChooser.chooseName('', schema)

            self.context[name] = schema
            self.request.response.redirect(
                absoluteURL(self.context, self.request))

        return self.template()


class TimetableSchemaContainerView(ContainerView):
    """TimetableSchema Container view."""

    __used_for__ = ITimetableSchemaContainer

    index_title = _("School Timetables")

    def update(self):
        if 'UPDATE_SUBMIT' in self.request:
            self.context.default_id = self.request['ttschema'] or None
        return ''


class TimetableDependentDeleteView(ContainerDeleteView):
    """The delete view for school timetables and schemas.

    Finds all timetables that use the object to be deleted and deletes
    them too.
    """

    adapts((ITimetableSchemaContainer, IBrowserRequest))
    implements(IBrowserPublisher)

    def timetables(self, obj):
        return findRelatedTimetables(obj)

    def update(self):
        if 'CONFIRM' in self.request:
            for key in self.listIdsForDeletion():
                del self.context[key]
            self.request.response.redirect(self.nextURL())
        elif 'CANCEL' in self.request:
            self.request.response.redirect(self.nextURL())


class IAdvancedTimetableSchemaAddSchema(Interface):

    title = TextLine(title=_(u"Title"), required=False)
    duration = Int(title=_(u"Duration"), description=_(u"Duration in minutes"),
                   required=False)


class AdvancedTimetableSchemaAdd(BrowserView, TabindexMixin):
    """View for defining a new timetable schema.

    Can be accessed at /ttschemas/complexadd.html.
    """

    __used_for__ = ITimetableSchemaContainer

    template = ViewPageTemplateFile("templates/advancedtts.pt")

    # Used in the page template
    days_of_week = (_("Monday"),
                    _("Tuesday"),
                    _("Wednesday"),
                    _("Thursday"),
                    _("Friday"),
                    _("Saturday"),
                    _("Sunday"),
                   )

    _schema = IAdvancedTimetableSchemaAddSchema

    def __init__(self, context, request):
        BrowserView.__init__(self, context, request)
        TabindexMixin.__init__(self)
        setUpWidgets(self, self._schema, IInputWidget,
                     initial={'title': 'default'})

    def __call__(self):

        # We could build a custom widget for the model radio buttons, but I do
        # not think it is worth the trouble.
        self.model_error = None
        self.model_name = self.request.get('model')

        self.ttschema = self._buildSchema()
        self.day_templates = self._buildDayTemplates()

        if 'CREATE' in self.request:
            data = getWidgetsData(self, self._schema)
            factory = queryUtility(ITimetableModelFactory,
                                   name=self.model_name)
            if factory is None:
                self.model_error = _("Please select a value")
            if not self.title_widget.error() and not self.model_error:
                model = factory(self.ttschema.day_ids, self.day_templates)
                self.ttschema.model = model
                self.ttschema.title = data['title']
                nameChooser = INameChooser(self.context)
                key = nameChooser.chooseName('', self.ttschema)
                self.context[key] = self.ttschema
                #Note: if you uncomment this, fix the i18n bug inside too.
                #self.request.appLog(_("Timetable schema %s created") %
                #               getPath(self.context[key]))
                return self.request.response.redirect(
                    absoluteURL(self.context, self.request))
        return self.template()

    def rows(self):
        return format_timetable_for_presentation(self.ttschema)

    def _buildSchema(self):
        """Build a timetable schema from data in the request."""
        n = 1
        day_ids = []
        day_idxs = []
        while 'day%d' % n in self.request:
            if 'DELETE_DAY_%d' % n not in self.request:
                day_id = self.request['day%d' % n].strip()
                if not day_id:
                    day_id_msgid = _('Day ${number}',
                                     mapping={'number': len(day_ids) + 1})
                    day_id = translate(day_id_msgid, context=self.request)
                day_ids.append(day_id)
                day_idxs.append(n)
            n += 1
        if 'ADD_DAY' in self.request or not day_ids:
            day_id_msgid = _('Day ${number}',
                             mapping={'number': len(day_ids) + 1})
            day_id = translate(day_id_msgid, context=self.request)
            day_ids.append(day_id)
            day_idxs.append(-1)
        day_ids = fix_duplicates(day_ids)

        periods_for_day = []
        longest_day = None
        previous_day = None
        for idx, day in zip(day_idxs, day_ids):
            n = 1
            if ('COPY_DAY_%d' % (idx - 1) in self.request
                and previous_day is not None):
                periods = list(previous_day)
            else:
                periods = []
                while 'day%d.period%d' % (idx, n) in self.request:
                    per_id = self.request['day%d.period%d' % (idx, n)].strip()
                    periods.append(per_id)
                    n += 1
                periods = filter(None, periods)
                if not periods:
                    period1 = translate(_("Period 1"), context=self.request)
                    periods = [period1]
                else:
                    periods = fix_duplicates(periods)
            periods_for_day.append(periods)
            if longest_day is None or len(periods) > len(longest_day):
                longest_day = periods
            previous_day = periods

        if 'ADD_PERIOD' in self.request:
            period_name_msgid = _('Period ${number}',
                                  mapping={'number': len(longest_day) + 1})
            period_name = translate(period_name_msgid, context=self.request)
            longest_day.append(period_name)

        app = ISchoolToolApplication(None)
        tzname = IApplicationPreferences(app).timezone
        ttschema = TimetableSchema(day_ids, timezone=tzname)
        for day, periods in zip(day_ids, periods_for_day):
            ttschema[day] = TimetableSchemaDay(periods)

        return ttschema

    def _buildDayTemplates(self):
        """Built a dict of day templates from data contained in the request.

        The dict is suitable to be passed as the second argument to the
        timetable model factory.
        """
        data = getWidgetsData(self, self._schema)
        default_duration = data.get('duration')
        result = {None: SchooldayTemplate()}
        n = 1
        self.discarded_some_periods = False
        while 'time%d.day0' % n in self.request:
            raw_value = [0]
            for day in range(7):
                value = self.request.form.get('time%d.day%d' % (n, day), '')
                if not value:
                    continue
                try:
                    start, duration = parse_time_range(value, default_duration)
                except ValueError:
                    # ignore invalid values for now, but tell the user
                    self.discarded_some_periods = True
                    continue
                if day not in result:
                    result[day] = SchooldayTemplate()
                result[day].add(SchooldaySlot(start, duration))
            n += 1
        for day in range(1, 7):
            if 'COPY_PERIODS_%d' % day in self.request:
                if (day - 1) in result:
                    result[day] = result[day - 1]
                elif day in result:
                    del result[day]
        return result

    def all_periods(self):
        """Return a list of all period names in order of occurrence."""
        periods = []
        for day_id in self.ttschema.day_ids:
            for period in self.ttschema[day_id].periods:
                if period not in periods:
                    periods.append(period)
        return periods

    def slot_times(self):
        """Return a list of lists of time periods for each day for each slot.

                      |  mo tu we thu fri sa su
             ---------+-------------------------
             1st slot |
             2nd slot |
             ...      |
        """
        nr_rows = max([len(day.keys())
                       for day_id, day in self.ttschema.items()])
        result =  [[None] * 7 for i in range(nr_rows)]
        for day, template in self.day_templates.items():
            for idx, slot in enumerate(template):
                slotfmt = format_time_range(slot.tstart, slot.duration)
                result[idx][day] = slotfmt
        return result


class TimetableSchemaXMLView(BrowserView):
    """View for ITimetableSchema"""

    dows = ['Monday', 'Tuesday', 'Wednesday', 'Thursday',
            'Friday', 'Saturday', 'Sunday']

    template = ViewPageTemplateFile("templates/schema_export.pt",
                                    content_type="text/xml; charset=UTF-8")

    __call__ = template

    def exceptiondayids(self):
        result = []

        for date, id in self.context.model.exceptionDayIds.items():
            result.append({'when': str(date), 'id': id})

        result.sort(lambda a, b: cmp((a['when'], a['id']),
                                     (b['when'], b['id'])))
        return result

    def daytemplates(self):
        items = self.context.items()
        id = items[0][0]
        result = []
        for id, day in self.context.model.dayTemplates.items():
            if id is None:
                used = "default"
            elif id in self.context.keys():
                used = id
            else:
                used = self.dows[id]
            periods = []
            for period in day:
                periods.append(
                    {'id': None,
                     'tstart': period.tstart.strftime("%H:%M"),
                     'duration': period.duration.seconds / 60})
            periods.sort()
            for template in result:
                if template['periods'] == periods:
                    days = template['used'].split()
                    days.append(used)
                    days.sort()
                    template['used'] = " ".join(days)
                    break
            else:
                result.append({'used': used, 'periods': periods})

        for date, day in self.context.model.exceptionDays.items():
            periods = []
            for period, slot in day:
                periods.append(
                    {'id': period,
                     'tstart': slot.tstart.strftime("%H:%M"),
                     'duration': slot.duration.seconds / 60})
            periods.sort()
            result.append({'used': str(date), 'periods': periods})

        result.sort(lambda a, b: cmp((a['used'], a['periods']),
                                     (b['used'], b['periods'])))

        return result
