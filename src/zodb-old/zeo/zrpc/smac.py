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
"""Sized Message Async Connections.

This class extends the basic asyncore layer with a record-marking
layer.  The message_output() method accepts an arbitrary sized string
as its argument.  It sends over the wire the length of the string
encoded using struct.pack('>i') and the string itself.  The receiver
passes the original string to message_input().

This layer also supports an optional message authentication code
(MAC).  If a session key is present, it uses HMAC-SHA-1 to generate a
20-byte MAC.  If a MAC is present, the high-order bit of the length
is set to 1 and the MAC immediately follows the length.
"""

import asyncore
import errno
import hmac
import sha
import socket
import struct
import threading
import warnings

from zodb.zeo.zrpc.interfaces import DisconnectedError
from zodb.zeo.zrpc import log

# Use the dictionary to make sure we get the minimum number of errno
# entries.   We expect that EWOULDBLOCK == EAGAIN on most systems --
# or that only one is actually used.

tmp_dict = {errno.EWOULDBLOCK: 0,
            errno.EAGAIN: 0,
            errno.EINTR: 0,
            }
expected_socket_read_errors = tuple(tmp_dict.keys())

tmp_dict = {errno.EAGAIN: 0,
            errno.EWOULDBLOCK: 0,
            errno.ENOBUFS: 0,
            errno.EINTR: 0,
            }
expected_socket_write_errors = tuple(tmp_dict.keys())
del tmp_dict

# We chose 60000 as the socket limit by looking at the largest strings
# that we could pass to send() without blocking.
SEND_SIZE = 60000

MAC_BIT = 0x80000000L

class SizedMessageAsyncConnection(asyncore.dispatcher, object):
    __super_init = asyncore.dispatcher.__init__
    __super_close = asyncore.dispatcher.close

    __closed = 1 # Marker indicating that we're closed

    socket = None # to outwit Sam's getattr

    def __init__(self, sock, addr, map=None, debug=None):
        self.addr = addr
        if debug is not None:
            self._debug = debug
        elif not hasattr(self, '_debug'):
            self._debug = __debug__
        # __input_lock protects __inp, __input_len, __state, __msg_size
        self.__input_lock = threading.Lock()
        self.__inp = None # None, a single String, or a list
        self.__input_len = 0
        # Instance variables __state and __msg_size work together:
        #   when __state == 0:
        #     __msg_size == 4, and the next thing read is a message size;
        #   when __state == 1:
        #     __msg_size is variable, and the next thing read is a message.
        # The next thing read is always of length __msg_size.
        # The state alternates between 0 and 1.
        self.__state = 0
        self.__msg_size = 4
        self.__output_lock = threading.Lock() # Protects __output
        self.__output = []
        self.__closed = 0
        self.__hmac = None
        self.__super_init(sock, map)

    def setSessionKey(self, sesskey):
        self.__hmac = hmac.HMAC(sesskey, digestmod=sha)

    def get_addr(self):
        return self.addr

    # XXX avoid expensive getattr calls?  Can't remember exactly what
    # this comment was supposed to mean, but it has something to do
    # with the way asyncore uses getattr and uses if sock:
    def __nonzero__(self):
        return 1

    def handle_read(self):
        self.__input_lock.acquire()
        try:
            # Use a single __inp buffer and integer indexes to make this fast.
            try:
                d = self.recv(8192)
            except socket.error, err:
                if err[0] in expected_socket_read_errors:
                    return
                raise
            if not d:
                return

            input_len = self.__input_len + len(d)
            msg_size = self.__msg_size
            state = self.__state

            inp = self.__inp
            if msg_size > input_len:
                if inp is None:
                    self.__inp = d
                elif isinstance(self.__inp, str):
                    self.__inp = [self.__inp, d]
                else:
                    self.__inp.append(d)
                self.__input_len = input_len
                return # keep waiting for more input

            # load all previous input and d into single string inp
            if isinstance(inp, str):
                inp = inp + d
            elif inp is None:
                inp = d
            else:
                inp.append(d)
                inp = "".join(inp)

            offset = 0
            expect_mac = 0
            while (offset + msg_size) <= input_len:
                msg = inp[offset:offset + msg_size]
                offset = offset + msg_size
                if not state:
                    # waiting for message
                    msg_size = struct.unpack(">I", msg)[0]
                    expect_mac = msg_size & MAC_BIT
                    if expect_mac:
                        msg_size ^= MAC_BIT
                        msg_size += 20
                    state = 1
                else:
                    msg_size = 4
                    state = 0
                    # XXX We call message_input() with __input_lock
                    # held!!!  And message_input() may end up calling
                    # message_output(), which has its own lock.  But
                    # message_output() cannot call message_input(), so
                    # the locking order is always consistent, which
                    # prevents deadlock.  Also, message_input() may
                    # take a long time, because it can cause an
                    # incoming call to be handled.  During all this
                    # time, the __input_lock is held.  That's a good
                    # thing, because it serializes incoming calls.
                    if expect_mac:
                        mac = msg[:20]
                        msg = msg[20:]
                        if self.__hmac:
                            self.__hmac.update(msg)
                            _mac = self.__hmac.digest()
                            if mac != _mac:
                                raise ValueError("MAC failed: %r != %r"
                                                 % (_mac, mac))
                        else:
                            log.warn("Received MAC but no session key set")
                    self.message_input(msg)

            self.__state = state
            self.__msg_size = msg_size
            self.__inp = inp[offset:]
            self.__input_len = input_len - offset
        finally:
            self.__input_lock.release()

    def readable(self):
        return 1

    def writable(self):
        if len(self.__output) == 0:
            return 0
        else:
            return 1

    def handle_write(self):
        self.__output_lock.acquire()
        try:
            output = self.__output
            while output:
                # Accumulate output into a single string so that we avoid
                # multiple send() calls, but avoid accumulating too much
                # data.  If we send a very small string and have more data
                # to send, we will likely incur delays caused by the
                # unfortunate interaction between the Nagle algorithm and
                # delayed acks.  If we send a very large string, only a
                # portion of it will actually be delivered at a time.

                l = 0
                for i in range(len(output)):
                    l += len(output[i])
                    if l > SEND_SIZE:
                        break

                i += 1
                # It is very unlikely that i will be 1.
                v = "".join(output[:i])
                del output[:i]

                try:
                    n = self.send(v)
                except socket.error, err:
                    if err[0] in expected_socket_write_errors:
                        break # we couldn't write anything
                    raise
                if n < len(v):
                    output.insert(0, v[n:])
                    break # we can't write any more
        finally:
            self.__output_lock.release()

    def handle_close(self):
        self.close()

    def message_output(self, message):
        if __debug__:
            if self._debug:
                log.debug('message_output %d bytes: %s',
                          len(message), log.short_repr(message))

        if self.__closed:
            raise DisconnectedError("Action is temporarily unavailable")
        self.__output_lock.acquire()
        try:
            # do separate appends to avoid copying the message string
            if self.__hmac:
                self.__output.append(struct.pack(">I", len(message) | MAC_BIT))
                self.__hmac.update(message)
                self.__output.append(self.__hmac.digest())
            else:
                self.__output.append(struct.pack(">I", len(message)))
            if len(message) <= SEND_SIZE:
                self.__output.append(message)
            else:
                for i in range(0, len(message), SEND_SIZE):
                    self.__output.append(message[i:i+SEND_SIZE])
        finally:
            self.__output_lock.release()

    def close(self):
        if not self.__closed:
            self.__closed = 1
            self.__super_close()
