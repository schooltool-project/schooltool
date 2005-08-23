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
"""Test Browser Tests

$Id: testdoc.py 37513 2005-07-27 23:27:15Z srichter $
"""
import unittest
import doctest
from zope.app.testing.functional import FunctionalDocFileSuite


def test_suite():
    return FunctionalDocFileSuite(
        '../README.txt',
        optionflags=doctest.NORMALIZE_WHITESPACE|doctest.ELLIPSIS)

if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
