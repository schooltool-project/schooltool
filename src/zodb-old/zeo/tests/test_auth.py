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
# FOR A PARTICULAR PURPOSE
#
##############################################################################
"""Test suite for AuthZEO."""

import os
import tempfile
import time
import unittest

from zodb.zeo.client import ClientStorage
from zodb.zeo.server import StorageServer
from zodb.zeo.tests.connection import CommonSetupTearDown

from zodb.storage.file import FileStorage

class AuthTest(CommonSetupTearDown):
    __super_getServerConfig = CommonSetupTearDown.getServerConfig
    __super_setUp = CommonSetupTearDown.setUp
    __super_tearDown = CommonSetupTearDown.tearDown
    
    realm = None

    def setUp(self):
        self.pwfile = tempfile.mktemp()
        if self.realm:
            self.pwdb = self.dbclass(self.pwfile, self.realm)
        else:
            self.pwdb = self.dbclass(self.pwfile)
        self.pwdb.add_user("foo", "bar")
        self.pwdb.save()
        self.__super_setUp()

    def tearDown(self):
        self.__super_tearDown()
        os.remove(self.pwfile)

    def getConfig(self, path, create, read_only):
        return "<mappingstorage 1/>"

    def getServerConfig(self, addr, ro_svr):
        zconf = self.__super_getServerConfig(addr, ro_svr)
        zconf.authentication_protocol = self.protocol
        zconf.authentication_database = self.pwfile
        zconf.authentication_realm = self.realm
        return zconf

    def wait(self):
        for i in range(25):
            if self._storage.test_connection:
                return
            time.sleep(0.1)
        self.fail("Timed out waiting for client to authenticate")

    def testOK(self):
        # Sleep for 0.2 seconds to give the server some time to start up
        # seems to be needed before and after creating the storage
        self._storage = self.openClientStorage(wait=0, username="foo",
                                              password="bar", realm=self.realm)
        self.wait()

        self.assert_(self._storage._connection)
        self._storage._connection.poll()
        self.assert_(self._storage.is_connected())
    
    def testNOK(self):
        self._storage = self.openClientStorage(wait=0, username="foo",
                                              password="noogie",
                                              realm=self.realm)
        self.wait()
        # If the test established a connection, then it failed.
        self.failIf(self._storage._connection)

class PlainTextAuth(AuthTest):
    import zodb.zeo.tests.auth_plaintext
    protocol = "plaintext"
    database = "authdb.sha"
    dbclass = zodb.zeo.tests.auth_plaintext.Database
    realm = "Plaintext Realm"

class DigestAuth(AuthTest):
    import zodb.zeo.auth.auth_digest
    protocol = "digest"
    database = "authdb.digest"
    dbclass = zodb.zeo.auth.auth_digest.DigestDatabase
    realm = "Digest Realm"

test_classes = [PlainTextAuth, DigestAuth]

def test_suite():
    suite = unittest.TestSuite()
    for klass in test_classes:
        sub = unittest.makeSuite(klass)
        suite.addTest(sub)
    return suite

if __name__ == "__main__":
    unittest.main(defaultTest='test_suite')

