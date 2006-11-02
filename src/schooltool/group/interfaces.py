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
Group interfaces

$Id$
"""

import zope.interface
import zope.schema
from zope.app import container
from zope.app.container.interfaces import IContainer, IContained
from zope.app.container import constraints

from schooltool import SchoolToolMessage as _

class IGroupMember(zope.interface.Interface):
    """An object that knows the groups it is a member of."""

    groups = zope.interface.Attribute("""Groups (see IRelationshipProperty)""")


class IBaseGroup(zope.interface.Interface):
    """Group."""

    title = zope.schema.TextLine(
        title=_("Title"),
        description=_("Title of the group."))

    description = zope.schema.Text(
        title=_("Description"),
        required=False,
        description=_("Description of the group."))

    members = zope.interface.Attribute(
        """Members of the group (see IRelationshipProperty)""")


class IGroup(IBaseGroup):
    """Group."""


class IGroupContainer(IContainer):
    """Container of groups."""

    container.constraints.contains(IGroup)


class IGroupContained(IGroup, IContained):
    """Group contained in an IGroupContainer."""

    container.constraints.containers(IGroupContainer)
