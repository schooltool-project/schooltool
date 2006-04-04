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
Section implementation

$Id$
"""
from persistent import Persistent
import zope.interface

from zope.app.annotation.interfaces import IAttributeAnnotatable
from zope.app.container import btree, contained

from schooltool.relationship import RelationshipProperty
from schooltool.app import membership
from schooltool.app.cal import Calendar
from schooltool.group.interfaces import IGroup
from schooltool.person.interfaces import IPerson
from schooltool.resource.interfaces import IResource

from schooltool import SchoolToolMessage as _
from schooltool.app import relationships
from schooltool.course import interfaces, booking


class Section(Persistent, contained.Contained):

    zope.interface.implements(interfaces.ISectionContained,
                              IAttributeAnnotatable)

    _location = None

    def __init__(self, title="Section", description=None, schedule=None,
                 location=None):
        self.title = title
        self.description = description
        self.calendar = Calendar(self)
        self.location = location

    @property
    def label(self):
        instructors = " ".join([i.title for i in self.instructors])
        courses = " ".join([c.title for c in self.courses])
        msg = _('${instructors} -- ${courses}',
                mapping={'instructors': instructors, 'courses': courses})
        return msg

    @property
    def size(self):
        size = 0
        for member in self.members:
            if IPerson.providedBy(member):
                size = size + 1
            if IGroup.providedBy(member):
                size = size + len(member.members)

        return size

    @apply
    def location():

        def get(self):
            return self._location

        def set(self, location):
            if location is not None:
                if (not IResource.providedBy(location) or
                    not location.isLocation):
                    raise TypeError("Locations must be location resources.")
            self._location = location

        return property(get, set)

    instructors = RelationshipProperty(relationships.URIInstruction,
                                       relationships.URISection,
                                       relationships.URIInstructor)

    courses = RelationshipProperty(relationships.URICourseSections,
                                   relationships.URISectionOfCourse,
                                   relationships.URICourse)

    members = RelationshipProperty(membership.URIMembership,
                                   membership.URIGroup,
                                   membership.URIMember)

    resources = RelationshipProperty(booking.URISectionBooking,
                                     booking.URISection,
                                     booking.URIResource)


class SectionContainer(btree.BTreeContainer):
    """Container of Sections."""

    zope.interface.implements(interfaces.ISectionContainer,
                              IAttributeAnnotatable)


def addSectionContainerToApplication(event):
    event.object['sections'] = SectionContainer()
