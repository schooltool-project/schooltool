##############################################################################
#
# Copyright (c) 2002 Zope Corporation and Contributors.
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
"""Open database and storage from a configuration.

$Id: config.py,v 1.5 2003/06/25 15:14:37 fdrake Exp $"""

import os
import StringIO

import ZConfig

import zodb.db

db_schema_path = os.path.join(zodb.__path__[0], "config.xml")
_db_schema = None

s_schema_path = os.path.join(zodb.__path__[0], "storage.xml")
_s_schema = None

def getDbSchema():
    global _db_schema
    if _db_schema is None:
        _db_schema = ZConfig.loadSchema(db_schema_path)
    return _db_schema

def getStorageSchema():
    global _s_schema
    if _s_schema is None:
        _s_schema = ZConfig.loadSchema(s_schema_path)
    return _s_schema

def databaseFromString(s):
    return databaseFromFile(StringIO.StringIO(s))

def databaseFromFile(f):
    config, handle = ZConfig.loadConfigFile(getDbSchema(), f)
    return databaseFromConfig(config.database)

def databaseFromURL(url):
    config, handler = ZConfig.loadConfig(getDbSchema(), url)
    return databaseFromConfig(config.database)

def databaseFromConfig(section):
    return section.open()

def storageFromString(s):
    return storageFromFile(StringIO.StringIO(s))

def storageFromFile(f):
    config, handle = ZConfig.loadConfigFile(getStorageSchema(), f)
    return storageFromConfig(config.storage)

def storageFromURL(url):
    config, handler = ZConfig.loadConfig(getStorageSchema(), url)
    return storageFromConfig(config.storage)

def storageFromConfig(section):
    return section.open()


class BaseConfig:
    """Object representing a configured storage or database.

    Methods:

    open() -- open and return the configured object

    Attributes:

    name   -- name of the storage

    """

    def __init__(self, config):
        self.config = config
        self.name = config.getSectionName()

    def open(self):
        """Open and return the storage object."""
        raise NotImplementedError

class ZODBDatabase(BaseConfig):

    def open(self):
        section = self.config
        return zodb.db.DB(section.storage.open(),
                          pool_size=section.pool_size,
                          cache_size=section.cache_size)

class MappingStorage(BaseConfig):

    def open(self):
        from zodb.storage.mapping import MappingStorage
        return MappingStorage(self.config.name)

class DemoStorage(BaseConfig):

    def open(self):
        from zodb.storage.demo import DemoStorage
        if self.config.base:
            base = self.config.base.open()
        else:
            base = None
        return DemoStorage(self.config.name,
                           base=base,
                           quota=self.config.quota)

class FileStorage(BaseConfig):

    def open(self):
        from zodb.storage.file import FileStorage
        return FileStorage(self.config.path,
                           create=self.config.create,
                           read_only=self.config.read_only,
                           quota=self.config.quota)

class ZEOClient(BaseConfig):

    def open(self):
        from zodb.zeo.client import ClientStorage
        # config.server is a multikey of socket-address values
        # where the value is a socket family, address tuple.
        L = [server.address for server in self.config.server]
        return ClientStorage(
            L,
            storage=self.config.storage,
            cache_size=self.config.cache_size,
            name=self.config.name,
            client=self.config.client,
            var=self.config.var,
            min_disconnect_poll=self.config.min_disconnect_poll,
            max_disconnect_poll=self.config.max_disconnect_poll,
            wait=self.config.wait,
            read_only=self.config.read_only,
            read_only_fallback=self.config.read_only_fallback)

class BDBStorage(BaseConfig):

    def open(self):
        from zodb.storage.base import BerkeleyConfig
        storageclass = self.get_storageclass()
        bconf = BerkeleyConfig()
        for name in dir(BerkeleyConfig):
            if name.startswith('_'):
                continue
            setattr(bconf, name, getattr(self.config, name))
        return storageclass(self.config.name, config=bconf)

class BDBMinimalStorage(BDBStorage):

    def get_storageclass(self):
        from zodb.storage.bdbminimal import BDBMinimalStorage
        return BDBMinimalStorage

class BDBFullStorage(BDBStorage):

    def get_storageclass(self):
        from zodb.storage.bdbfull import BDBFullStorage
        return BDBFullStorage
