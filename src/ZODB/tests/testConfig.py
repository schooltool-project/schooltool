##############################################################################
#
# Copyright (c) 2003 Zope Corporation and Contributors.
# All Rights Reserved.
#
# This software is subject to the provisions of the Zope Public License,
# Version 2.0 (ZPL).  A copy of the ZPL should accompany this distribution.
# THIS SOFTWARE IS PROVIDED "AS IS" AND ANY AND ALL EXPRESS OR IMPLIED
# WARRANTIES ARE DISCLAIMED, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
# WARRANTIES OF TITLE, MERCHANTABILITY, AGAINST INFRINGEMENT, AND FITNESS
# FOR A PARTICULAR PURPOSE.
#
##############################################################################

import os
import errno
import shutil
import tempfile
import unittest

import ZODB.config
import ZODB.tests
from ZODB.POSException import ReadOnlyError


class ConfigTestBase(unittest.TestCase):
    def _opendb(self, s):
        return ZODB.config.databaseFromString(s)

    def tearDown(self):
        if getattr(self, "storage", None) is not None:
            self.storage.cleanup()

    def _test(self, s):
        db = self._opendb(s)
        self.storage = db._storage
        # Do something with the database to make sure it works
        cn = db.open()
        rt = cn.root()
        rt["test"] = 1
        get_transaction().commit()
        db.close()


class ZODBConfigTest(ConfigTestBase):
    def test_map_config1(self):
        self._test(
            """
            <zodb>
              <mappingstorage/>
            </zodb>
            """)

    def test_map_config2(self):
        self._test(
            """
            <zodb>
              <mappingstorage/>
              cache-size 1000
            </zodb>
            """)

    def test_file_config1(self):
        path = tempfile.mktemp()
        self._test(
            """
            <zodb>
              <filestorage>
                path %s
              </filestorage>
            </zodb>
            """ % path)

    def test_file_config2(self):
        path = tempfile.mktemp()
        cfg = """
        <zodb>
          <filestorage>
            path %s
            create false
            read-only true
          </filestorage>
        </zodb>
        """ % path
        self.assertRaises(ReadOnlyError, self._test, cfg)

    def test_demo_config(self):
        cfg = """
        <zodb unused-name>
          <demostorage>
            name foo
            <mappingstorage/>
          </demostorage>
        </zodb>
        """
        self._test(cfg)


class ZEOConfigTest(ConfigTestBase):
    def test_zeo_config(self):
        # We're looking for a port that doesn't exist so a
        # connection attempt will fail.  Instead of elaborate
        # logic to loop over a port calculation, we'll just pick a
        # simple "random", likely to not-exist port number and add
        # an elaborate comment explaining this instead.  Go ahead,
        # grep for 9.
        from ZEO.ClientStorage import ClientDisconnected
        cfg = """
        <zodb>
          <zeoclient>
            server localhost:56897
            wait false
          </zeoclient>
        </zodb>
        """
        self.assertRaises(ClientDisconnected, self._test, cfg)


class BDBConfigTest(ConfigTestBase):
    def setUp(self):
        self._path = tempfile.mktemp()
        try:
            os.mkdir(self._path)
        except OSError, e:
            if e.errno <> errno.EEXIST:
                raise

    def test_bdbfull_simple(self):
        cfg = """
        <zodb>
          <fullstorage>
             envdir %s
          </fullstorage>
        </zodb>
        """ % self._path
        self._test(cfg)

    def test_bdbminimal_simple(self):
        cfg = """
        <zodb>
          <minimalstorage>
            envdir %s
          </minimalstorage>
        </zodb>
        """ % self._path
        self._test(cfg)


def test_suite():
    suite = unittest.TestSuite()
    suite.addTest(unittest.makeSuite(ZODBConfigTest))
    # Only run the ZEO test if ZEO is available
    try:
        import ZEO
    except ImportError:
        pass
    else:
        suite.addTest(unittest.makeSuite(ZEOConfigTest))
    # Only run the Berkeley tests if bsddb is available
    try:
        import BDBStorage
    except ImportError:
        pass
    else:
        if BDBStorage.is_available:
            suite.addTest(unittest.makeSuite(BDBConfigTest))
    return suite


if __name__ == '__main__':
    unittest.main(defaultTest='test_suite')
