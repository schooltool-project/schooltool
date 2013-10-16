#
# SchoolTool - common information systems platform for school administration
# Copyright (c) 2013 Shuttleworth Foundation
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
Upgrade SchoolTool to generation 42.

Make schedule container and timetable timezones match app settings.
"""
import zope.lifecycleevent
from zope.app.generations.utility import getRootFolder, findObjectsProviding
from zope.annotation.interfaces import IAnnotations
from zope.component.hooks import getSite, setSite

from schooltool.app.interfaces import ISchoolToolApplication

SCHEDULES_KEY = 'schooltool.timetable.schedules'
TIMETABLES_KEY = 'schooltool.timetable.timetables'
APP_PREFERENCES_KEY = 'schooltool.app.ApplicationPreferences'


def evolveScheduleContainers(app):
    annotations = IAnnotations(app)
    prefs = annotations[APP_PREFERENCES_KEY]
    schedule_containers = app[SCHEDULES_KEY]
    for container in schedule_containers.values():
        if container.timezone != prefs.timezone:
            container.timezone = prefs.timezone
            zope.lifecycleevent.modified(container)


def evolveTimetableContainers(app):
    annotations = IAnnotations(app)
    prefs = annotations[APP_PREFERENCES_KEY]
    schedule_containers = app[TIMETABLES_KEY]
    for container in schedule_containers.values():
        for timetable in container.values():
            if timetable.timezone != prefs.timezone:
                timetable.timezone = prefs.timezone
                zope.lifecycleevent.modified(timetable)


def evolve(context):
    root = getRootFolder(context)

    old_site = getSite()
    apps = list(findObjectsProviding(root, ISchoolToolApplication))
    for app in apps:
        setSite(app)
        evolveScheduleContainers(app)
        evolveTimetableContainers(app)

    setSite(old_site)
