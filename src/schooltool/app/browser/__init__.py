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
Browser views for the SchoolTool application.

$Id$
"""
import calendar
import itertools

from zope.interface import implements
from zope.component import adapts
from zope.publisher.browser import BrowserView
from zope.size.interfaces import ISized
from zope.traversing.interfaces import IPathAdapter, ITraversable
from zope.app.security.interfaces import IPrincipal
from zope.app.security.interfaces import IUnauthenticatedPrincipal
from zope.app.dependable.interfaces import IDependable
from zope.tales.interfaces import ITALESFunctionNamespace
from zope.security.proxy import removeSecurityProxy
from zope.security.checker import canAccess

from pytz import timezone

from schooltool import SchoolToolMessage as _
from schooltool.app.interfaces import IApplicationPreferences
from schooltool.app.app import getSchoolToolApplication
from schooltool.person.interfaces import IPerson
from schooltool.person.interfaces import IPersonPreferences


class SchoolToolAPI(object):
    """TALES function namespace for SchoolTool specific actions.

    In a page template you can use it as follows:

        tal:define="app context/schooltool:app"

    """

    implements(IPathAdapter, ITALESFunctionNamespace)

    def __init__(self, context):
        self.context = context

    def setEngine(self, engine):
        """See ITALESFunctionNamespace."""
        pass

    def app(self):
        """Return the ISchoolToolApplication.

        Sample usage in a page template:

            <a tal:attributes="href context/schooltool:app/@@absolute_url">
               Front page
            </a>

        """
        return getSchoolToolApplication()
    app = property(app)

    def person(self):
        """Adapt context to IPerson, default to None.

        Sample usage in a page template:

            <a tal:define="person request/principal/schooltool:person"
               tal:condition="person"
               tal:attributes="person/calendar/@@absolute_url">
               My calendar
            </a>

        """
        return IPerson(self.context, None)
    person = property(person)

    def authenticated(self):
        """Check whether context is an authenticated principal.

        Sample usage in a page template:

            <tal:span tal:define="user request/principal"
                      tal:condition="user/schooltool:authenticated"
                      tal:replace="user/title">
              User title
            </tal:span>
            <tal:span tal:define="user request/principal"
                      tal:condition="not:user/schooltool:authenticated">
              Anonymous
            </tal:span>

        """
        if self.context is None: # no one is logged in
            return False
        if not IPrincipal.providedBy(self.context):
            raise TypeError("schooltool:authenticated can only be applied"
                            " to a principal but was applied on %r" % self.context)
        return not IUnauthenticatedPrincipal.providedBy(self.context)
    authenticated = property(authenticated)

    def preferences(self):
        """Return ApplicationPreferences for the SchoolToolApplication.

        Sample usage in a page template:

          <div tal:define="preferences context/schooltool:preferences">
            <b tal:content="preferences/title"></b>
          </div>

        """
        return IApplicationPreferences(self.app)
    preferences = property(preferences)

    def has_dependents(self):
        """Check whether an object has dependents (via IDependable).

        Objects that have dependents cannot be removed from the system.

        Sample usage in a page template:

          <input type="checkbox" name="delete"
                 tal:attributes="disabled obj/schooltool:has_dependents" />

        """
        # We cannot adapt security-proxied objects to IDependable.  Unwrapping
        # is safe since we do not modify anything, and the information whether
        # an object can be deleted or not is not classified.
        unwrapped_context = removeSecurityProxy(self.context)
        dependable = IDependable(unwrapped_context, None)
        if dependable is None:
            return False
        else:
            return bool(dependable.dependents())
    has_dependents = property(has_dependents)


class PathAdapterUtil(object):

    adapts(None)
    implements(IPathAdapter, ITraversable)

    def __init__(self, context):
        self.context = context


class SortBy(PathAdapterUtil):
    """TALES path adapter for sorting lists.

    In a page template you can use it as follows:

        tal:repeat="something some_iterable/sortby:attribute_name"

    In Python code you can write

        >>> l = [{'name': 'banana'}, {'name': 'apple'}]
        >>> SortBy(l).traverse('name')
        [{'name': 'apple'}, {'name': 'banana'}]

    You can sort arbitrary iterables, not just lists.  The sort key
    can refer to a dictionary key, or an object attribute.
    """

    def traverse(self, name, furtherPath=()):
        """Return self.context sorted by a given key."""
        # We need to get the first item without losing it forever
        iterable = iter(self.context)
        try:
            first = iterable.next()
        except StopIteration:
            return [] # We got an empty list
        iterable = itertools.chain([first], iterable)
        # removeSecurityProxy is safe here because subsequent getattr() will
        # raise Unauthorized or ForbiddenAttribute as appropriate.  It is
        # necessary here to fix http://issues.schooltool.org/issue174
        if hasattr(removeSecurityProxy(first), name):
            items = [(getattr(item, name), item) for item in iterable]
        else:
            items = [(item[name], item) for item in iterable]
        items.sort()
        return [row[-1] for row in items]


class CanAccess(PathAdapterUtil):
    """TALES path adapter for checking access rights.

    In a page template this adapter can be used like this:

        <p tal:condition="context/can_access:title"
           tal:content="context/title" />

    """

    def traverse(self, name, furtherPath=()):
        """Returns True if self.context.(name) can be accessed."""
        return canAccess(self.context, name)


class FilterAccessible(PathAdapterUtil):
    """TALES path adapter for XXX

    In a page template this adapter can be used like this:

        <p tal:repeat="group context/groups/filter_accessible:title"
           tal:content="group/title" />

    """

    def traverse(self, name, furtherPath=()):
        """XXX"""
        return [item for item in self.context
                if canAccess(item, name)]


class SortedFilterAccessible(PathAdapterUtil):
    """TALES path adapter for XXX

    In a page template this adapter can be used like this:

        <p tal:repeat="group context/groups/sorted_filter_accessible:title"
           tal:content="group/title" />

    """

    def traverse(self, name, furtherPath=()):
        """XXX"""
        filtered = FilterAccessible(self.context).traverse(name)
        return SortBy(filtered).traverse(name)


class SchoolToolSized(object):
    """An adapter to provide number of persons in a SchoolTool instance."""

    implements(ISized)

    def __init__(self, app):
        self._app = app

    def sizeForSorting(self):
        return (_("Persons"), len(self._app['persons']))

    def sizeForDisplay(self):
        num = self.sizeForSorting()[1]
        if num == 1:
            msgid = _("1 person")
        else:
            msgid = _("${number} persons", mapping={'number': num})
        return msgid


class ViewPreferences(object):
    """Preference class to attach to views."""

    def __init__(self, request):
        person = IPerson(request.principal, None)
        if person is not None:
            prefs = IPersonPreferences(person)
        else:
            try:
                app = getSchoolToolApplication()
                prefs = IApplicationPreferences(app)
            except (ValueError, TypeError):
                prefs = None

        if prefs is not None:
            self.dateformat = prefs.dateformat
            self.timeformat = prefs.timeformat
            self.first_day_of_week = prefs.weekstart
            self.timezone = timezone(prefs.timezone)
        else:
            # no user, no application - test environment
            self.dateformat = '%Y-%m-%d'
            self.timeformat = '%H:%M'
            self.first_day_of_week = calendar.MONDAY
            self.timezone = timezone('UTC')

    def renderDatetime(self, dt):
        dt = dt.astimezone(self.timezone)
        return dt.strftime('%s %s' % (self.dateformat, self.timeformat))


def same(obj1, obj2):
    """Return True if the references obj1 and obj2 point to the same object.

    The references may be security-proxied.
    """
    return removeSecurityProxy(obj1) is removeSecurityProxy(obj2)
