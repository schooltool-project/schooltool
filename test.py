#!/usr/bin/env python
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
SchoolTool test script.

$Id$
"""

import sys, os

if sys.version_info < (2, 4):
    print >> sys.stderr, '%s: need Python 2.4 or later.' % sys.argv[0]
    print >> sys.stderr, 'Your python is %s' % sys.version
    sys.exit(1)

here = os.path.dirname(os.path.realpath(__file__))

# Remove this directory from path:
sys.path[:] = [p for p in sys.path if os.path.abspath(p) != here]

src = os.path.join(here, 'src')
# Replace the directory of this wrapper script with SchoolTool and Zope 3
# source directories
sys.path[:1] = [src, os.path.join(here, 'Zope3', 'src')]
import site
site.addsitedir(os.path.join(here, 'Zope3', 'src'))

from zope.testing import testrunner

defaults = ['--tests-pattern', '^f?tests$', '--test-path', src]
defaults += ['-m', 'schooltool']

if __name__ == '__main__':
    exitcode = testrunner.run(defaults)
    sys.exit(exitcode)
