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
Calendar overlay views for the SchoolBell application.

$Id$
"""

import urllib
from sets import Set

from zope.publisher.browser import BrowserView
from zope.traversing.api import getPath
from zope.traversing.browser.absoluteurl import absoluteURL
from zope.location.interfaces import ILocation
from zope.security.proxy import removeSecurityProxy
from zope.security.checker import canAccess

from schooltool.common import SchoolToolMessage as _
from schooltool.app.app import getSchoolToolApplication
from schooltool.app.interfaces import ISchoolToolCalendar
from schooltool.app.interfaces import IShowTimetables
from schooltool.person.interfaces import IPerson


class CalendarOverlayView(BrowserView):
    """View for the calendar overlay portlet.

    This view can be used with any context, but it gets rendered to an empty
    string unless context is the calendar of the authenticated user.

    Note that this view contains a self-posting form and handles submits that
    contain 'OVERLAY_APPLY' or 'OVERLAY_MORE' in the request.
    """

    def show_overlay(self):
        """Check whether the calendar overlay portlet needs to be rendered.

            >>> from zope.app.testing import setup
            >>> setup.placelessSetUp()
            >>> setup.setUpAnnotations()

            >>> from schooltool.testing import setup as sbsetup
            >>> sbsetup.setUpCalendaring()

        The portlet is only shown when an authenticated user is looking
        at his/her calendar.

        Anonymous user:

            >>> from zope.publisher.browser import TestRequest
            >>> from schooltool.person.person import Person
            >>> request = TestRequest()
            >>> person = Person()
            >>> context = ISchoolToolCalendar(person)
            >>> view = CalendarOverlayView(context, request)
            >>> view.show_overlay()
            False

        Person that we're looking at

            >>> from schooltool.app.security import Principal
            >>> request.setPrincipal(Principal('id', 'title', person))
            >>> view.show_overlay()
            True

        A different person:

            >>> request.setPrincipal(Principal('id', 'title', Person()))
            >>> view.show_overlay()
            False

       Cleanup:

            >>> setup.placelessTearDown()

        """
        if not ILocation.providedBy(self.context):
            return False
        logged_in = removeSecurityProxy(IPerson(self.request.principal, None))
        calendar_owner = removeSecurityProxy(self.context.__parent__)
        return logged_in is calendar_owner

    def items(self):
        """Return items to be shown in the calendar overlay.

        Does not include "my calendar".

        Each item is a dict with the following keys:

            'title' - title of the calendar

            'calendar' - the calendar object

            'color1', 'color2' - colors assigned to this calendar

            'id' - identifier for form controls

            'checked' - was this item checked for display (either "checked" or
            None)?

        """
        person = IPerson(self.request.principal)
        items = [((item.calendar.title, getPath(item.calendar.__parent__)),
                  {'title': item.calendar.title,
                   'id': getPath(item.calendar.__parent__),
                   'calendar': item.calendar,
                   'checked': item.show and "checked" or '',
                   'color1': item.color1,
                   'color2': item.color2})
                 for item in person.overlaid_calendars
                 if canAccess(item.calendar, '__iter__')]
        items.sort()
        return [i[-1] for i in items]

    def update(self):
        """Process form submission."""
        if 'OVERLAY_MORE' in self.request:
            person = IPerson(self.request.principal)
            url = absoluteURL(person, self.request)
            url += '/calendar_selection.html'
            url += '?nexturl=%s' % urllib.quote(str(self.request.URL))
            self.request.response.redirect(url)
        if 'OVERLAY_APPLY' in self.request:
            person = IPerson(self.request.principal)
            selected = Set(self.request.get('overlay', []))
            for item in person.overlaid_calendars:
                item.show = getPath(item.calendar.__parent__) in selected
            url = str(self.request.URL)
            self.request.response.redirect(url)


class CalendarSelectionView(BrowserView):
    """A view for calendar selection.

    This view can be used with any context, but always operates on the
    currently authenticated user's list of overlaid calendars.
    """

    error = None
    message = None

    def getCalendars(self, container):
        """List all calendars from a given container."""
        user = removeSecurityProxy(IPerson(self.request.principal, None))
        if user is None:
            return []
        app = getSchoolToolApplication()

        result = []
        for obj in app[container].values():
            calendar = ISchoolToolCalendar(obj)
            if obj is not user and canAccess(calendar, '__iter__'):
                result.append(
                    {'id': obj.__name__,
                     'title': obj.title,
                     'selected': calendar in user.overlaid_calendars,
                     'calendar': calendar})
        return sorted(result, key=lambda item: (item['title'], item['id']))

    def getApplicationCalendar(self):
        """Return the application calendar.

        Returns None if the user lacks sufficient permissions.
        """
        user = IPerson(self.request.principal, None)
        if user:
            app = getSchoolToolApplication()
            calendar = ISchoolToolCalendar(app)
            if canAccess(calendar, '__iter__'):
                return {'title': app.title,
                        'selected': calendar in user.overlaid_calendars,
                        'calendar': calendar}
        return {}

    application = property(getApplicationCalendar)
    persons = property(lambda self: self.getCalendars('persons'))
    groups = property(lambda self: self.getCalendars('groups'))
    resources = property(lambda self: self.getCalendars('resources'))

    def update(self):
        """Process forms."""
        if 'CANCEL' in self.request:
            nexturl = self.request.form.get('nexturl')
            if nexturl:
                self.request.response.redirect(nexturl)
            return
        user = IPerson(self.request.principal, None)
        if user is None:
            return
        if 'UPDATE_SUBMIT' in self.request:
            self._updateSelection(user)
            self.message = _('Saved changes.')
            nexturl = self.request.form.get('nexturl')
            if nexturl:
                self.request.response.redirect(nexturl)

    def _updateSelection(self, user):
        """Apply calendar selection changes  for `user`."""
        for container in 'persons', 'groups', 'resources':
            selected = Set(self.request.form.get(container, []))
            for item in self.getCalendars(container):
                if item['id'] in selected and not item['selected']:
                    ovl_info = user.overlaid_calendars.add(item['calendar'])
                    if container != 'persons':
                        IShowTimetables(ovl_info).showTimetables = False
                elif item['id'] not in selected and item['selected']:
                    user.overlaid_calendars.remove(item['calendar'])
        appcal = self.getApplicationCalendar().get('calendar')
        if appcal is not None:
            if ('application' in self.request and
                    appcal not in user.overlaid_calendars):
                user.overlaid_calendars.add(appcal)
            elif ('application' not in self.request and
                    appcal in user.overlaid_calendars):
                user.overlaid_calendars.remove(appcal)
