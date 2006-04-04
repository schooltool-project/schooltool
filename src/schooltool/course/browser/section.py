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
course browser views.

$Id$
"""
from zope.security.proxy import removeSecurityProxy
from zope.security.checker import canWrite
from zope.app import zapi
from zope.app.component.hooks import getSite
from zope.app.form.browser.add import AddView
from zope.app.form.interfaces import WidgetsError
from zope.app.form.utility import getWidgetsData
from zope.app.publisher.browser import BrowserView

from schooltool.batching import Batch
from schooltool.timetable.interfaces import ITimetables
from schooltool.app.browser.app import ContainerView, BaseEditView
from schooltool.group.interfaces import IGroup
from schooltool.person.interfaces import IPerson

from schooltool import SchoolToolMessage as _
from schooltool.app.app import getSchoolToolApplication
from schooltool.course.interfaces import ISection, ISectionContainer


class SectionContainerView(ContainerView):
    """A Course Container view."""

    __used_for__ = ISectionContainer

    index_title = _("Section index")
    add_title = _("Add a new section")
    add_url = "+/addSchoolToolSection.html"

    # XXX: very hacky, but necessary for now. :-(
    def getTimetables(self, obj):
        return ITimetables(obj).timetables


class SectionView(BrowserView):
    """A view for courses providing a list of sections."""

    __used_for__ = ISection

    def getPersons(self):
        return filter(IPerson.providedBy, self.context.members)

    def getGroups(self):
        return filter(IGroup.providedBy, self.context.members)


class SectionAddView(AddView):
    """A view for adding Sections."""

    error = None
    course = None

    def validCourse(self):
        return self.course is not None

    def getCourseFromId(self, cid):
        app = getSite()
        try:
            return app['courses'][cid]
        except KeyError:
            self.error = _("No such course.")

    def __init__(self, context, request):
        super(AddView, self).__init__(context, request)
        self.update_status = None
        self.errors = None

        try:
            course_id = request['field.course_id']
        except KeyError:
            self.error = _("Need a course ID.")
            return

        self.course = self.getCourseFromId(course_id)
        if self.course is not None:
            self.label = _("Add a Section to ${course}",
                           mapping={'course': self.course.title})

    def update(self):
        if self.update_status is not None:
            # We've been called before. Just return the previous result.
            return self.update_status

        if "UPDATE_SUBMIT" in self.request:
            self.update_status = ''
            try:
                data = getWidgetsData(self, self.schema, names=self.fieldNames)
                section = removeSecurityProxy(self.createAndAdd(data))
                self.course.sections.add(section)
            except WidgetsError, errors:
                self.errors = errors
                self.update_status = _("An error occurred.")
                return self.update_status

            self.request.response.redirect(self.nextURL())

        if 'CANCEL' in self.request:
            url = zapi.absoluteURL(self.course, self.request)
            self.request.response.redirect(url)

        return self.update_status

    def nextURL(self):
        return zapi.absoluteURL(self.course, self.request)


class SectionEditView(BaseEditView):
    """View for editing Sections."""

    __used_for__ = ISection


class RelationshipEditingViewBase(BrowserView):

    def getCollection(self):
        raise NotImplementedError()

    def getAvailableItems(self):
        raise NotImplementedError()

    def update(self):
        # This method is rather similar to GroupListView.update().
        context_url = zapi.absoluteURL(self.context, self.request)
        context_items = removeSecurityProxy(self.getCollection())
        if 'ADD_ITEMS' in self.request:
            for item in self.getAvailableItems():
                if 'add_item.' + item.__name__ in self.request:
                    item = removeSecurityProxy(item)
                    context_items.add(item)
        elif 'REMOVE_ITEMS' in self.request:
            for item in self.getCollection():
                if 'remove_item.' + item.__name__ in self.request:
                    item = removeSecurityProxy(item)
                    context_items.remove(item)
        elif 'CANCEL' in self.request:
            self.request.response.redirect(context_url)

        if 'SEARCH' in self.request and 'CLEAR_SEARCH' not in self.request:
            searchstr = self.request['SEARCH'].lower()
            results = [item for item in self.getAvailableItems()
                       if searchstr in item.title.lower()]
        else:
            self.request.form['SEARCH'] = ''
            results = self.getAvailableItems()

        start = int(self.request.get('batch_start', 0))
        size = int(self.request.get('batch_size', 10))
        self.batch = Batch(results, start, size, sort_by='title')


class SectionInstructorView(RelationshipEditingViewBase):
    """View for adding instructors to a Section."""

    __used_for__ = ISection

    title = _("Instructors")
    current_title = _("Current Instructors")
    available_title = _("Available Instructors")

    def getCollection(self):
        """Return a list of all possible members."""
        return self.context.instructors

    def getAvailableItems(self):
        """Return a list of all possible members."""
        container = getSchoolToolApplication()['persons']
        return [p for p in container.values() if p not in
                self.getCollection()]


class SectionLearnerView(BrowserView):
    """View for adding learners to a Section.  """

    __used_for__ = ISection

    def getPotentialLearners(self):
        """Return a list of all possible members."""
        container = getSchoolToolApplication()['persons']
        return container.values()

    def update(self):
        # This method is rather similar to GroupListView.update().
        context_url = zapi.absoluteURL(self.context, self.request)
        if 'UPDATE_SUBMIT' in self.request:
            context_members = removeSecurityProxy(self.context.members)
            for member in self.getPotentialLearners():
                want = bool('member.' + member.__name__ in self.request)
                have = bool(member in context_members)
                # add() and remove() could throw an exception, but at the
                # moment the constraints are never violated, so we ignore
                # the problem.
                if want != have:
                    member = removeSecurityProxy(member)
                    if want:
                        context_members.add(member)
                    else:
                        context_members.remove(member)
            self.request.response.redirect(context_url)
        elif 'CANCEL' in self.request:
            self.request.response.redirect(context_url)


class SectionLearnerGroupView(SectionLearnerView):
    """View for adding groups of students to a Section."""

    def getPotentialLearners(self):
        """Return a list of all possible members."""
        container = getSchoolToolApplication()['groups']
        return container.values()
