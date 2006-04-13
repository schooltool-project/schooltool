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
SchoolTool application views.

$Id$
"""

import itertools

from zope.interface import implements
from zope.security.checker import canAccess
from zope.security.interfaces import IParticipation
from zope.security.management import getSecurityPolicy
from zope.security.proxy import removeSecurityProxy
from zope.app import zapi
from zope.app.form.utility import getWidgetsData, setUpWidgets
from zope.app.form.browser.add import AddView
from zope.app.form.browser.editview import EditView
from zope.app.form.interfaces import IInputWidget
from zope.app.form.interfaces import WidgetsError
from zope.app.publisher.browser import BrowserView
from zope.app.security.interfaces import IAuthentication
from zope.app.security.interfaces import IAuthenticatedGroup
from zope.app.security.interfaces import IUnauthenticatedGroup
from zope.app.securitypolicy.interfaces import IPrincipalPermissionManager

from schooltool import SchoolToolMessage as _
from schooltool.app.app import getSchoolToolApplication
from schooltool.app.interfaces import IApplicationPreferences
from schooltool.app.interfaces import ISchoolToolCalendar
from schooltool.batching import Batch
from schooltool.batching.browser import MultiBatchViewMixin
from schooltool.person.interfaces import IPerson


class ApplicationView(BrowserView):
    """A view for the main application."""

    def update(self):
        prefs = IApplicationPreferences(getSchoolToolApplication())
        if prefs.frontPageCalendar:
            url = zapi.absoluteURL(ISchoolToolCalendar(self.context),
                                   self.request)
            self.request.response.redirect(url)


class ContainerView(BrowserView):
    """A base view for all containers.

    Subclasses must provide the following attributes that are used in the
    page template:

        `index_title` -- Title of the index page.
        `add_title` -- Title for the adding link.
        `add_url` -- URL of the adding link.

    """

    def update(self):
        if 'SEARCH' in self.request and 'CLEAR_SEARCH' not in self.request:
            searchstr = self.request['SEARCH'].lower()
            results = [item for item in self.context.values()
                       if searchstr in item.title.lower()]
        else:
            self.request.form['SEARCH'] = ''
            results = self.context.values()

        start = int(self.request.get('batch_start', 0))
        size = int(self.request.get('batch_size', 10))
        self.batch = Batch(results, start, size, sort_by='title')

    def canModify(self):
        return canAccess(self.context, '__delitem__')
    canModify = property(canModify)


class ContainerDeleteView(BrowserView):
    """A view for deleting items from container."""

    def listIdsForDeletion(self):
        return [key for key in self.context
                if "delete.%s" % key in self.request]

    def _listItemsForDeletion(self):
        return [self.context[key] for key in self.listIdsForDeletion()]

    itemsToDelete = property(_listItemsForDeletion)

    def update(self):
        if 'UPDATE_SUBMIT' in self.request:
            for key in self.listIdsForDeletion():
                del self.context[key]
            self.request.response.redirect(self.nextURL())
        elif 'CANCEL' in self.request:
            self.request.response.redirect(self.nextURL())

    def nextURL(self):
        return zapi.absoluteURL(self.context, self.request)


class BaseAddView(AddView):
    """Common functionality for adding groups and resources"""

    def nextURL(self):
        return zapi.absoluteURL(self.context.context, self.request)

    def update(self):
        if 'CANCEL' in self.request:
            self.request.response.redirect(self.nextURL())
        else:
            return AddView.update(self)


class BaseEditView(EditView):
    """An edit view for resources and groups"""

    def update(self):
        if 'CANCEL' in self.request:
            url = zapi.absoluteURL(self.context, self.request)
            self.request.response.redirect(url)
        else:
            status = EditView.update(self)
            if 'UPDATE_SUBMIT' in self.request and not self.errors:
                url = zapi.absoluteURL(self.context, self.request)
                self.request.response.redirect(url)
            return status


class LoginView(BrowserView):
    """A login view"""

    error = None

    def __call__(self):
        self.update()
        return self.index()

    def update(self):
        if ('LOGIN' in self.request and 'username' in self.request and
            'password' in self.request):
            auth = zapi.getUtility(IAuthentication)
            try:
                auth.setCredentials(self.request, self.request['username'],
                                    self.request['password'])
            except ValueError:
                self.error = _("Username or password is incorrect")
            else:
                principal = auth.authenticate(self.request)
                person = IPerson(principal, None)
                if 'nexturl' in self.request:
                    nexturl = self.request['nexturl']
                elif person is not None:
                    nexturl = zapi.absoluteURL(
                        ISchoolToolCalendar(person), self.request)
                else:
                    nexturl = zapi.absoluteURL(self.context, self.request)
                self.request.response.redirect(nexturl)


class LogoutView(BrowserView):
    """Clears the authentication creds from the session"""

    def __call__(self):
        auth = zapi.getUtility(IAuthentication)
        auth.clearCredentials(self.request)
        url = zapi.absoluteURL(self.context, self.request)
        self.request.response.redirect(url)


class ACLViewBase(object):
    """A base view for both browser and restive access control views."""

    permissions = [
        ('schooltool.view', _('View')),
        ('schooltool.edit', _('Edit')),
        ('schooltool.create', _('Create new objects')),
        ('schooltool.viewCalendar', _('View calendar')),
        ('schooltool.addEvent', _('Add events')),
        ('schooltool.modifyEvent', _('Modify/delete events')),
        ('schooltool.controlAccess', _('Control access')),
        ('schooltool.manageMembership', _('Manage membership')),
        ]
    permission_ids = [permission for permission, title in permissions]
    del permission, title # list comprehensions clutter local scope

    def getPersons(self):
        app = getSchoolToolApplication()
        map = IPrincipalPermissionManager(self.context)
        auth = zapi.getUtility(IAuthentication)
        result = []
        for person in app['persons'].values():
            pid = auth.person_prefix + person.__name__
            result.append({'title': person.title, 'id': pid})
        return result
    persons = property(getPersons)

    def permsForPrincipal(self, principalid):
        """Return a list of permissions allowed for principal."""
        permission_bits = hasPermissions(self.permission_ids, self.context,
                                         principalid)
        return [perm for perm, has in zip(self.permission_ids, permission_bits)
                if has]

    def getGroups(self):
        app = getSchoolToolApplication()
        auth = zapi.getUtility(IAuthentication)
        map = IPrincipalPermissionManager(self.context)
        result = []
        all = zapi.queryUtility(IAuthenticatedGroup)
        if all is not None:
            result.append({'title': _('Authenticated users'),
                           'id': all.id})
        unauth = zapi.queryUtility(IUnauthenticatedGroup)
        if unauth is not None:
            result.append({'title': _('Unauthenticated users'),
                           'id': unauth.id})
        for group in app['groups'].values():
            pid = auth.group_prefix + group.__name__
            result.append({'title': group.title,
                           'id': pid})
        return result
    groups = property(getGroups)

    def applyPermissionChanges(self, principalid, permissions):
        """Apply new permission settings for a single principal.

        Make it so `principal` has exactly the permissions specified
        in `permissions` (and not more) on self.context.

        If the requested permission grant on self.context matches the
        one on self.context.__parent__, this method removes any
        specific local grants from self.context.  Otherwise, it adds a
        local grant that either grants or denies the permission
        directly on self.context.
        """
        parent = self.context.__parent__
        manager = IPrincipalPermissionManager(self.context)
        # ACL views are protected by schoolbell.controlAccess, so
        # removeSecurityProxy does not lead to privilege escalation
        # problems.
        manager = removeSecurityProxy(manager)
        permission_bits = hasPermissions(self.permission_ids, parent,
                                         principalid)
        for permission, in_parent in zip(self.permission_ids, permission_bits):
            requested = permission in permissions
            if requested and not in_parent:
                manager.grantPermissionToPrincipal(permission, principalid)
            elif not requested and in_parent:
                manager.denyPermissionToPrincipal(permission, principalid)
            else:
                manager.unsetPermissionForPrincipal(permission, principalid)


class ACLView(BrowserView, ACLViewBase, MultiBatchViewMixin):
    """A view for editing SchoolBell-relevant local grants"""

    def __init__(self, context, request):
        BrowserView.__init__(self, context, request)
        MultiBatchViewMixin.__init__(self, ['groups', 'persons'])

    def update(self):
        if 'UPDATE_SUBMIT' in self.request or 'CANCEL' in self.request:
            url = zapi.absoluteURL(self.context, self.request)
            self.request.response.redirect(url)

        if 'UPDATE_SUBMIT' in self.request:
            for info in self.persons + self.groups:
                principalid = info['id']
                if 'marker-' + principalid not in self.request:
                    continue # skip this principal
                permissions = self.request.get(principalid, [])
                if isinstance(permissions, basestring):
                    permissions = [permissions]
                self.applyPermissionChanges(principalid, permissions)

        MultiBatchViewMixin.update(self)

        self.updateBatch('persons', self.persons)
        self.updateBatch('groups', self.groups)

        for infodict in itertools.chain(self.batches['persons'],
                                        self.batches['groups']):
            infodict['perms'] = self.permsForPrincipal(infodict['id'])

    def __call__(self):
        self.update()
        return self.index()


class ApplicationPreferencesView(BrowserView):
    """View used for editing application preferences."""

    __used_for__ = IApplicationPreferences

    error = None
    message = None

    schema = IApplicationPreferences

    def __init__(self, context, request):
        BrowserView.__init__(self, context, request)

        app = getSchoolToolApplication()
        prefs = self.schema(app)
        initial = {}
        for field in self.schema:
            initial[field] = getattr(prefs, field)

        setUpWidgets(self, self.schema, IInputWidget, initial=initial)

    def update(self):
        if 'CANCEL' in self.request:
            url = zapi.absoluteURL(self.context, self.request)
            self.request.response.redirect(url)
        elif 'UPDATE_SUBMIT' in self.request:
            try:
                data = getWidgetsData(self, self.schema)
            except WidgetsError:
                return # Errors will be displayed next to widgets

            app = getSchoolToolApplication()
            prefs = self.schema(app)
            for field in self.schema:
                if field in data: # skip non-fields
                    setattr(prefs, field, data[field])


class ProbeParticipation:
    """A stub participation for use in hasPermissions."""
    implements(IParticipation)
    def __init__(self, principal):
        self.principal = principal
        self.interaction = None


def hasPermissions(permissions, object, principalid):
    """Test if the principal has access according to the security policy."""
    principal = zapi.getUtility(IAuthentication).getPrincipal(principalid)
    participation = ProbeParticipation(principal)
    interaction = getSecurityPolicy()(participation)
    return [interaction.checkPermission(permission, object)
            for permission in permissions]
