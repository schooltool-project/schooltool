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
Timetable Schemas

$Id$
"""
from persistent import Persistent
from persistent.dict import PersistentDict
from sets import Set

from zope.interface import implements
from zope.app.annotation.interfaces import IAttributeAnnotatable
from zope.app.container.btree import BTreeContainer
from zope.app.container.contained import Contained

from schooltool.timetable import Timetable, TimetableDay
from schooltool.timetable.interfaces import ITimetableSchema
from schooltool.timetable.interfaces import ITimetableSchemaContained
from schooltool.timetable.interfaces import ITimetableSchemaContainer
from schooltool.timetable.interfaces import ITimetableSchemaDay
from schooltool.timetable.interfaces import ITimetableSchemaWrite


class TimetableSchemaDay(Persistent):

    implements(ITimetableSchemaDay)

    # BBB: default value for ZODB compatibility
    homeroom_period_id = None

    def __init__(self, periods=(), homeroom_period_id=None):
        if homeroom_period_id is not None:
            assert homeroom_period_id in periods
        self.periods = periods
        self.homeroom_period_id = homeroom_period_id

    def keys(self):
        return self.periods

    def items(self):
        return [(period, Set()) for period in self.periods]

    def __getitem__(self, period):
        if period not in self.periods:
            raise KeyError(period)
        return Set()

    def __eq__(self, other):
        if ITimetableSchemaDay.providedBy(other):
            return (self.periods, self.homeroom_period_id) == \
                    (other.periods, other.homeroom_period_id)
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)


class TimetableSchema(Persistent, Contained):

    implements(ITimetableSchemaContained, ITimetableSchemaWrite)

    def __init__(self, day_ids, title=None, model=None, timezone='UTC'):
        """Create a new empty timetable schema.

        day_ids is a sequence of the day ids of this timetable.

        The caller must then assign a TimetableDay for each day ID and
        set the model before trying to use the timetable.
        """
        self.title = title
        if self.title is None:
            self.title = "Schema"
        self.day_ids = day_ids
        self.days = PersistentDict()
        self.model = model
        self.timezone = timezone

    def keys(self):
        return list(self.day_ids)

    def items(self):
        return [(day, self.days[day]) for day in self.day_ids]

    def __getitem__(self, key):
        return self.days[key]

    def __setitem__(self, key, value):
        if not ITimetableSchemaDay.providedBy(value):
            raise TypeError("Timetable schema can only contain"
                            " ITimetableSchemaDay objects (got %r)" % (value,))
        elif key not in self.day_ids:
            raise ValueError("Key %r not in day_ids %r" % (key, self.day_ids))
        self.days[key] = value

    def createTimetable(self):
        new = Timetable(self.day_ids)
        new.model = self.model
        new.timezone = self.timezone
        for day_id in self.day_ids:
            new[day_id] = TimetableDay(self[day_id].periods,
                                       self[day_id].homeroom_period_id)
        return new

    def __eq__(self, other):
        if ITimetableSchema.providedBy(other):
            return (self.items() == other.items()
                    and self.model == other.model)
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)


class TimetableSchemaContainer(BTreeContainer):

    implements(ITimetableSchemaContainer, IAttributeAnnotatable)

    _default_id = None

    def _set_default_id(self, new_id):
        if new_id is not None and new_id not in self:
            raise ValueError("Timetable schema %r does not exist" % new_id)
        self._default_id = new_id

    default_id = property(lambda self: self._default_id, _set_default_id)

    def __setitem__(self, schema_id, ttschema):
        assert ITimetableSchema.providedBy(ttschema)
        if self.has_key(schema_id):
            BTreeContainer.__delitem__(self, schema_id)
        BTreeContainer.__setitem__(self, schema_id, ttschema)
        if self.default_id is None:
            self.default_id = schema_id

    def __delitem__(self, schema_id):
        BTreeContainer.__delitem__(self, schema_id)
        if schema_id == self.default_id:
            self.default_id = None

    def getDefault(self):
        return self[self.default_id]


##############################################################################
# BBB: Make sure the old data object references are still there.
#      Needs to be here to avoid circular imports.
from schooltool import timetable
timetable.TimetableSchemaContainer = TimetableSchemaContainer
timetable.TimetableSchema = TimetableSchema
timetable.TimetableSchemaDay = TimetableSchemaDay
##############################################################################
