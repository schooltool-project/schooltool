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
Restive XML views for the SchoolTool application.

$Id$
"""

from zope.interface import implements
from zope.publisher.http import HTTPRequest
from zope.server.http.commonaccesslogger import CommonAccessLogger
from zope.server.http.wsgihttpserver import WSGIHTTPServer
from zope.app.publication.interfaces import IPublicationRequestFactory
from zope.app.publication.http import HTTPPublication
from zope.app.server.wsgi import ServerType
from zope.app.wsgi import WSGIPublisherApplication
from zope.app.pagetemplate.viewpagetemplatefile import ViewPageTemplateFile \
                                                as Template # reexport


class RestPublicationRequestFactory(object):
    """Request factory for the RESTive server.

    This request factory always creates HTTPRequests, regardless of
    the method or content type of the incoming request.
    """

    implements(IPublicationRequestFactory)

    def __init__(self, db):
        """See `zope.app.publication.interfaces.IPublicationRequestFactory`"""
        self.db = db

    def __call__(self, input_stream, env):
        """See `zope.app.publication.interfaces.IPublicationRequestFactory`"""
        request = HTTPRequest(input_stream, env)
        request.setPublication(HTTPPublication(self.db))

        return request


restServerType = ServerType(WSGIHTTPServer,
                            WSGIPublisherApplication,
                            CommonAccessLogger,
                            7001, True,
                            requestFactory=RestPublicationRequestFactory)


class View(object):
    """A base class for RESTive views."""

    def __init__(self, context, request):
        self.context = context
        self.request = request

    def GET(self):
        return self.template(self.request, view=self, context=self.context)

    def HEAD(self):
        body = self.GET()
        request.setHeader('Content-Length', len(body))
        return ""
