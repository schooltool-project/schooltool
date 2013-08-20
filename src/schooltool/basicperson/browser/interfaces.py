#
# SchoolTool - common information systems platform for school administration
# Copyright (c) 2007 Shuttleworth Foundation
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
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
"""
Interfaces for person views.
"""
from zope.interface import Interface


class IPersonDataExporterPlugin(Interface):
    """A plugin that renders data directly related to the exported person.

    Like his grades, groups, sections etc.
    """

    def render(person):
        """Render the xml snippet that contains relevant information."""


class IExtraDataExporterPlugin(Interface):
    """A plugin that renders the data common to persons being exported.

    Like titles and descriptions of groups.
    """

    def render(persons):
        """Render the xml snippet that contains relevant information."""
