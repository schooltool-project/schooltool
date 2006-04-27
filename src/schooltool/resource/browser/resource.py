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
group views.

$Id$
"""

from zope.publisher.browser import BrowserView

from schooltool import SchoolToolMessage as _
from schooltool.app.browser.app import ContainerView, BaseAddView, BaseEditView

from schooltool.resource.interfaces import IResourceContainer
from schooltool.resource.interfaces import IResourceContained


class ResourceContainerView(ContainerView):
    """A Resource Container view."""

    __used_for__ = IResourceContainer

    index_title = _("Resource index")
    add_title = _("Add a new resource")
    add_url = "+/addSchoolToolResource.html"


class ResourceView(BrowserView):
    """A Resource info view."""

    __used_for__ = IResourceContained


class ResourceAddView(BaseAddView):
    """A view for adding a resource."""


class ResourceEditView(BaseEditView):
    """A view for editing resource info."""

    __used_for__ = IResourceContained
