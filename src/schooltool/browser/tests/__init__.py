#
# SchoolTool - common information systems platform for school administration
# Copyright (c) 2003 Shuttleworth Foundation
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
Unit tests for the schooltool.browser package.
"""

from schooltool.rest.tests import RequestStub              # reexport
from schooltool.rest.tests import LocatableStub, setPath   # reexport


class TraversalTestMixin:

    def assertTraverses(self, view, name, viewclass, context=None,
                        request=None):
        """Assert that traversal returns the appropriate view.

        Checks that view._traverse(name, request) returns an instance of
        viewclass, and that the context attribute of the new view is
        identical to context.
        """
        if request is None:
            request = RequestStub()
        destination = view._traverse(name, request)
        self.assert_(isinstance(destination, viewclass))
        if context is not None:
            self.assert_(destination.context is context)
        return destination


def HTMLDocument(content):
    """Parse an HTML document and return a schooltool.xmlparsing.XMLDocument.

    Knows how to handle the standard HTML named entities (e.g. &nbsp;).
    """
    import re
    import htmlentitydefs
    preambule = """
       <!DOCTYPE html [%s]>
    """ % "".join(['<!ENTITY %s "&#%d;">' % (name, code)
                   for name, code in htmlentitydefs.name2codepoint.items()])
    content = preambule + re.sub(r'<!DOCTYPE[^>]*>', '', content)

    from schooltool.rest.xmlparsing import XMLDocument
    return XMLDocument(content)
