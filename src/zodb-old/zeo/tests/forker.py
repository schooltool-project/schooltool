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
"""Library for forking storage server and connecting client storage"""

import os
import sys
import time
import logging
import errno
import random
import socket
import StringIO
import tempfile

class ZEOConfig:
    """Class to generate ZEO configuration file. """

    def __init__(self, addr):
        self.address = addr
        self.read_only = None
        self.invalidation_queue_size = None
        self.monitor_address = None
        self.transaction_timeout = None
        self.authentication_protocol = None
        self.authentication_database = None
        self.authentication_realm = None

    def dump(self, f):
        print >> f, "<zeo>"
        print >> f, "address %s:%s" % self.address
        if self.read_only is not None:
            print >> f, "read-only", self.read_only and "true" or "false"
        if self.invalidation_queue_size is not None:
            print >> f, "invalidation-queue-size", self.invalidation_queue_size
        if self.monitor_address is not None:
            print >> f, "monitor-address %s:%s" % self.monitor_address
        if self.transaction_timeout is not None:
            print >> f, "transaction-timeout", self.transaction_timeout
        if self.authentication_protocol is not None:
            print >> f, "authentication-protocol", self.authentication_protocol
        if self.authentication_database is not None:
            print >> f, "authentication-database", self.authentication_database
        if self.authentication_realm is not None:
            print >> f, "authentication-realm", self.authentication_realm
        print >> f, "</zeo>"

    def __str__(self):
        f = StringIO.StringIO()
        self.dump(f)
        return f.getvalue()

def start_zeo_server(storage_conf, zeo_conf, port, keep=0):
    """Start a ZEO server in a separate process.

    Takes two positional arguments a string containing the storage conf
    and a ZEOConfig object.

    Returns the ZEO port, the test server port, the pid, and the path
    to the config file.
    """
    
    # Store the config info in a temp file.
    tmpfile = tempfile.mktemp(".conf")
    fp = open(tmpfile, 'w')
    zeo_conf.dump(fp)
    fp.write(storage_conf)
    fp.close()
    
    # Find the zeoserver script
    import zodb.zeo.tests.zeoserver
    script = zodb.zeo.tests.zeoserver.__file__
    if script.endswith('.pyc'):
        script = script[:-1]
        
    logger = logging.getLogger("forker")
    
    # Create a list of arguments, which we'll tuplify below
    qa = _quote_arg
    args = [qa(sys.executable), qa(script), '-C', qa(tmpfile)]
    if keep:
        args.append("-k")
    d = os.environ.copy()
    d["PYTHONPATH"] = os.pathsep.join(sys.path)
    logini = os.getenv("LOGINI")
    if logini:
        d["LOGINI"] = logini
    pid = os.spawnve(os.P_NOWAIT, sys.executable, tuple(args), d)
    logger.debug("spawned %s %s: %s", sys.executable, " ".join(args), pid)
    adminaddr = ('localhost', port + 1)
    # We need to wait until the server starts, but not forever.  It can
    # take a Berkeley storage more than 10 seconds to start.
    for i in range(120):
        time.sleep(0.25)
        logger.debug("connect %s", i)
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect(adminaddr)
            ack = s.recv(1024)
            s.close()
        except socket.error, e:
            if e[0] not in (errno.ECONNREFUSED, errno.ECONNRESET):
                raise
            s.close()
        else:
            logger.debug("acked: %s", ack)
            break
    else:
        logger.debug("boo foo")
        raise
    return ('localhost', port), adminaddr, pid, tmpfile


if sys.platform[:3].lower() == "win":
    def _quote_arg(s):
        return '"%s"' % s
else:
    def _quote_arg(s):
        return s


def shutdown_zeo_server(adminaddr):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect(adminaddr)
    try:
        ack = s.recv(1024)
    except socket.error, e:
        if e[0] <> errno.ECONNRESET: raise
        ack = 'no ack received'
    logging.getLogger("forker").debug("shutdown server acked: %s", ack)
    s.close()
