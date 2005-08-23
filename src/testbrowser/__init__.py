##############################################################################
#
# Copyright (c) 2005 Zope Corporation. All Rights Reserved.
#
# This software is subject to the provisions of the Zope Visible Source
# License, Version 1.0 (ZVSL).  A copy of the ZVSL should accompany this
# distribution.
#
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE
#
##############################################################################
"""Browser Simulator for Functional DocTests 

$Id: __init__.py 37997 2005-08-18 22:09:10Z poster $
"""

# TODO this should be removed once John J. Lee releases the new version of
# ClientForm that has the code we rely on here.  At that point we should also
# remove ClientForm.py from this directory.
import sys
from testbrowser import ClientForm

if 'ClientForm' not in sys.modules:
    sys.modules['ClientForm'] = ClientForm
else:
    assert sys.modules['ClientForm'] is ClientForm
# end TODO

from testing import Browser
