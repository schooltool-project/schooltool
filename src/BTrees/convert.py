##############################################################################
#
# Copyright (c) 2001, 2002 Zope Corporation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.0 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE
#
##############################################################################

def convert(old, new, threshold=200, f=None):
    "Utility for converting old btree to new"
    n=0
    for k, v in old.items():
        if f is not None: v=f(v)
        new[k]=v
        n=n+1
        if n > threshold:
            transaction.commit(1)
            old._p_jar.cacheMinimize()
            n=0

    transaction.commit(1)
    old._p_jar.cacheMinimize()
