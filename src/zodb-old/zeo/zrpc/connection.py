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
import sys
import errno
import types
import select
import logging
import asyncore
import threading

from zodb.zeo import threadedasync
from zodb.zeo.zrpc import smac
from zodb.zeo.zrpc.interfaces import ZRPCError, DisconnectedError
from zodb.zeo.zrpc import log
from zodb.zeo.zrpc.marshal import Marshaller
from zodb.zeo.zrpc.trigger import trigger

REPLY = ".reply" # message name used for replies
ASYNC = 1

class Delay:
    """Used to delay response to client for synchronous calls

    When a synchronous call is made and the original handler returns
    without handling the call, it returns a Delay object that prevents
    the mainloop from sending a response.
    """

    def set_sender(self, msgid, send_reply, return_error):
        self.msgid = msgid
        self.send_reply = send_reply
        self.return_error = return_error

    def reply(self, obj):
        self.send_reply(self.msgid, obj)

    def error(self, exc_info):
        log.error("Error raised in delayed method", exc_info=True)
        self.return_error(self.msgid, 0, *exc_info[:2])

class MTDelay(Delay):

    def __init__(self):
        self.ready = threading.Event()

    def set_sender(self, msgid, send_reply, return_error):
        Delay.set_sender(self, msgid, send_reply, return_error)
        self.ready.set()

    def reply(self, obj):
        self.ready.wait()
        Delay.reply(self, obj)

    def error(self, exc_info):
        self.ready.wait()
        Delay.error(self, exc_info)

class Connection(smac.SizedMessageAsyncConnection):
    """Dispatcher for RPC on object on both sides of socket.

    The connection supports synchronous calls, which expect a return,
    and asynchronous calls, which do not.

    It uses the Marshaller class to handle encoding and decoding of
    method calls and arguments.  Marshaller uses pickle to encode
    arbitrary Python objects.  The code here doesn't ever see the wire
    format.

    A Connection is designed for use in a multithreaded application,
    where a synchronous call must block until a response is ready.

    A socket connection between a client and a server allows either
    side to invoke methods on the other side.  The processes on each
    end of the socket use a Connection object to manage communication.

    The Connection deals with decoded RPC messages.  They are
    represented as four-tuples containing: msgid, flags, method name,
    and a tuple of method arguments.

    The msgid starts at zero and is incremented by one each time a
    method call message is sent.  Each side of the connection has a
    separate msgid state.

    When one side of the connection (the client) calls a method, it
    sends a message with a new msgid.  The other side (the server),
    replies with a message that has the same msgid, the string
    ".reply" (the global variable REPLY) as the method name, and the
    actual return value in the args position.  Note that each side of
    the Connection can initiate a call, in which case it will be the
    client for that particular call.

    The protocol also supports asynchronous calls.  The client does
    not wait for a return value for an asynchronous call.  The only
    defined flag is ASYNC.  If a method call message has the ASYNC
    flag set, the server will raise an exception.

    If a method call raises an Exception, the exception is propagated
    back to the client via the REPLY message.  The client side will
    raise any exception it receives instead of returning the value to
    the caller.
    """

    __super_init = smac.SizedMessageAsyncConnection.__init__
    __super_close = smac.SizedMessageAsyncConnection.close
    __super_setSessionKey = smac.SizedMessageAsyncConnection.setSessionKey

    oldest_protocol_version = "Z400"
    protocol_version = "Z400"

    # Z400 -- the first protocol defined for ZODB4

    def __init__(self, sock, addr, obj=None):
        self.obj = None
        self.marshal = Marshaller()
        self.closed = 0
        self.msgid = 0
        self.peer_protocol_version = None # set in recv_handshake()
        if isinstance(addr, tuple):
            self.log_label = "zrpc-conn:%s:%d" % addr
        else:
            self.log_label = "zrpc-conn:%s" % addr
        self.__super_init(sock, addr)
        # A Connection either uses asyncore directly or relies on an
        # asyncore mainloop running in a separate thread.  If
        # thr_async is true, then the mainloop is running in a
        # separate thread.  If thr_async is true, then the asyncore
        # trigger (self.trigger) is used to notify that thread of
        # activity on the current thread.
        self.thr_async = 0
        self.trigger = None
        self._prepare_async()
        self._map = {self._fileno: self}
        # __msgid_lock guards access to msgid
        self.msgid_lock = threading.Lock()
        # __replies_cond is used to block when a synchronous call is
        # waiting for a response
        self.replies_cond = threading.Condition()
        self.replies = {}
        # waiting_for_reply is used internally to indicate whether
        # a call is in progress.  setting a session key is deferred
        # until after the call returns.
        self.waiting_for_reply = False
        self.delay_sesskey = None
        self.register_object(obj)
        self.handshake()

    def __repr__(self):
        return "<%s %s>" % (self.__class__.__name__, self.addr)

    __str__ = __repr__ # Defeat asyncore's dreaded __getattr__

    def close(self):
        if self.closed:
            return
        self._map.clear()
        self.closed = 1
        self.close_trigger()
        self.__super_close()

    def close_trigger(self):
        # overridden by ManagedConnection
        if self.trigger is not None:
            self.trigger.close()

    def register_object(self, obj):
        """Register obj as the true object to invoke methods on"""
        self.obj = obj

    def handshake(self, protocol=None):
        # When a connection is created the first message sent is a
        # 4-byte protocol version.  This mechanism should allow the
        # protocol to evolve over time, and let servers handle clients
        # using multiple versions of the protocol.

        # The mechanism replaces the message_input() method for the
        # first message received.

        # The client sends the protocol version it is using.
        self._message_input = self.message_input
        self.message_input = self.recv_handshake
        self.message_output(protocol or self.protocol_version)

    def recv_handshake(self, protocol):
         # Extended by ManagedConnection
         del self.message_input
         self.peer_protocol_version = protocol
         if self.oldest_protocol_version <= protocol <= self.protocol_version:
             log.warn("%s: received handshake %r", self.log_label,
                      protocol)
         else:
             log.error("%s: recv_handshake: bad handshake %s", self.log_label,
                       protocol)
             raise ZRPCError("bad handshake %r" % protocol)

    def message_input(self, message):
        """Decoding an incoming message and dispatch it"""
        # If something goes wrong during decoding, the marshaller
        # will raise an exception.  The exception will ultimately
        # result in asycnore calling handle_error(), which will
        # close the connection.
        msgid, flags, name, args = self.marshal.decode(message)

        if __debug__:
            log.debug("%s: recv msg: %s, %s, %s, %s",
                      self.log_label, msgid, flags, name,
                      log.short_repr(args))
        if name == REPLY:
            self.handle_reply(msgid, flags, args)
        else:
            self.handle_request(msgid, flags, name, args)

    def handle_reply(self, msgid, flags, args):
        if __debug__:
            log.debug("%s: recv reply: %s, %s, %s",
                      self.log_label, msgid, flags, log.short_repr(args))
        self.replies_cond.acquire()
        try:
            self.replies[msgid] = flags, args
            self.replies_cond.notifyAll()
        finally:
            self.replies_cond.release()

    def handle_request(self, msgid, flags, name, args):
        if not self.check_method(name):
            msg = "Invalid method name: %s on %s" % (name, repr(self.obj))
            raise ZRPCError(msg)
        if __debug__:
            log.info("%s: calling %s%s", self.log_label, name,
                     log.short_repr(args))

        meth = getattr(self.obj, name)
        try:
            self.waiting_for_reply = True
            try:
                ret = meth(*args)
            finally:
                self.waiting_for_reply = False
        except (SystemExit, KeyboardInterrupt):
            raise
        except Exception, msg:
            error = sys.exc_info()
            log.info("%s: %s() raised exception: %s", self.log_label,
                     name, msg, exc_info=True)
            error = error[:2]
            return self.return_error(msgid, flags, *error)

        if flags & ASYNC:
            if ret is not None:
                raise ZRPCError("async method %s returned value %s" %
                                (name, log.short_repr(ret)))
        else:
            if __debug__:
                log.debug("%s: %s returns %s", self.log_label, name,
                          log.short_repr(ret))
            if isinstance(ret, Delay):
                ret.set_sender(msgid, self.send_reply, self.return_error)
            else:
                self.send_reply(msgid, ret)

        if self.delay_sesskey:
            self.__super_setSessionKey(self.delay_sesskey)
            self.delay_sesskey = None

    def handle_error(self):
        if sys.exc_info()[0] == SystemExit:
            raise sys.exc_info()
        self.log_error("Error caught in asyncore")
        self.close()

    def log_error(self, msg="No error message supplied"):
        log.error("%s: %s", self.log_label, msg, exc_info=True)

    def check_method(self, name):
        # XXX Is this sufficient "security" for now?
        if name.startswith('_'):
            return None
        return hasattr(self.obj, name)

    def send_reply(self, msgid, ret):
        try:
            msg = self.marshal.encode(msgid, 0, REPLY, ret)
        except self.marshal.errors:
            try:
                r = log.short_repr(ret)
            except:
                r = "<unreprable>"
            err = ZRPCError("Couldn't pickle return %.100s" % r)
            msg = self.marshal.encode(msgid, 0, REPLY, (ZRPCError, err))
        self.message_output(msg)
        self.poll()

    def return_error(self, msgid, flags, err_type, err_value):
        if flags & ASYNC:
            self.log_error("Asynchronous call raised exception: %s" % self)
            return
        if not isinstance(err_value, types.InstanceType):
            err_value = err_type, err_value

        try:
            msg = self.marshal.encode(msgid, 0, REPLY, (err_type, err_value))
        except self.marshal.errors:
            try:
                r = log.short_repr(err_value)
            except:
                r = "<unreprable>"
            err = ZRPCError("Couldn't pickle error %.100s" % r)
            msg = self.marshal.encode(msgid, 0, REPLY, (ZRPCError, err))
        self.message_output(msg)
        self.poll()

    def setSessionKey(self, key):
        if self.waiting_for_reply:
            self.delay_sesskey = key
        else:
            self.__super_setSessionKey(key)

    # The next two public methods (call and callAsync) are used by
    # clients to invoke methods on remote objects

    def send_call(self, method, args, flags):
        # send a message and return its msgid
        self.msgid_lock.acquire()
        try:
            msgid = self.msgid
            self.msgid = self.msgid + 1
        finally:
            self.msgid_lock.release()
        if __debug__:
            log.debug("%s: send msg: %d, %d, %s, ...", self.log_label,
                      msgid, flags, method)
        buf = self.marshal.encode(msgid, flags, method, args)
        self.message_output(buf)
        return msgid

    def call(self, method, *args):
        if self.closed:
            raise DisconnectedError()
        msgid = self.send_call(method, args, 0)
        r_flags, r_args = self.wait(msgid)
        if (isinstance(r_args, tuple) and len(r_args) > 1
            and isinstance(r_args[0], types.ClassType)
            and issubclass(r_args[0], Exception)):
            inst = r_args[1]
            raise inst # error raised by server
        else:
            return r_args

    # For testing purposes, it is useful to begin a synchronous call
    # but not block waiting for its response.  Since these methods are
    # used for testing they can assume they are not in async mode and
    # call asyncore.poll() directly to get the message out without
    # also waiting for the reply.
 
    def _deferred_call(self, method, *args):
        if self.closed:
            raise DisconnectedError()
        msgid = self.send_call(method, args, 0)
        asyncore.poll(0.01, self._map)
        return msgid

    def _deferred_wait(self, msgid):
        r_flags, r_args = self.wait(msgid)
        if (isinstance(r_args, tuple)
            and type(r_args[0]) == types.ClassType
            and issubclass(r_args[0], Exception)):
            inst = r_args[1]
            raise inst # error raised by server
        else:
            return r_args

    def callAsync(self, method, *args):
        if self.closed:
            raise DisconnectedError()
        self.send_call(method, args, ASYNC)
        self.poll()

    def callAsyncNoPoll(self, method, *args):
        # Like CallAsync but doesn't poll.  This exists so that we can
        # send invalidations atomically to all clients without
        # allowing any client to sneak in a load request.
        if self.closed:
            raise DisconnectedError()
        self.send_call(method, args, ASYNC)

    # handle IO, possibly in async mode

    def _prepare_async(self):
        self.thr_async = 0
        threadedasync.register_loop_callback(self.set_async)
        # XXX If we are not in async mode, this will cause dead
        # Connections to be leaked.

    def set_async(self, map):
        self.trigger = trigger()
        self.thr_async = 1

    def is_async(self):
        # overridden for ManagedConnection
        if self.thr_async:
            return 1
        else:
            return 0

    def _pull_trigger(self, tryagain=10):
        try:
            self.trigger.pull_trigger()
        except OSError:
            self.trigger.close()
            self.trigger = trigger()
            if tryagain > 0:
                self._pull_trigger(tryagain=tryagain-1)

    def wait(self, msgid):
        """Invoke asyncore mainloop and wait for reply."""
        if __debug__:
            log.debug("%s: wait(%d), async=%d", self.log_label, msgid,
                      self.is_async())
        if self.is_async():
            self._pull_trigger()

        # Delay used when we call asyncore.poll() directly.
        # Start with a 1 msec delay, double until 1 sec.
        delay = 0.001

        self.replies_cond.acquire()
        try:
            while 1:
                if self.closed:
                    raise DisconnectedError()
                reply = self.replies.get(msgid)
                if reply is not None:
                    del self.replies[msgid]
                    if __debug__:
                        log.debug("%s: wait(%d): reply=%s", self.log_label,
                                  msgid, log.short_repr(reply))
                    return reply
                if self.is_async():
                    self.replies_cond.wait(10.0)
                else:
                    self.replies_cond.release()
                    try:
                        try:
                            if __debug__:
                                log.debug("%s: wait(%d): asyncore.poll(%s)",
                                          self.log_label, msgid, delay)
                            asyncore.poll(delay, self._map)
                            if delay < 1.0:
                                delay += delay
                        except select.error, err:
                            log.info("%s: Closing.  "
                                     "asyncore.poll() raised %s.",
                                     self.log_label, err)
                            self.close()
                    finally:
                        self.replies_cond.acquire()
        finally:
            self.replies_cond.release()

    def flush(self):
        """Invoke poll() until the output buffer is empty."""
        if __debug__:
            log.debug("flush")
        while self.writable():
            self.poll()

    def poll(self):
        """Invoke asyncore mainloop to get pending message out."""
        if __debug__:
            log.debug("%s: poll(), async=%d", self.log_label, self.is_async())
        if self.is_async():
            self._pull_trigger()
        else:
            asyncore.poll(0.0, self._map)

    def pending(self, timeout=0):
        """Invoke mainloop until any pending messages are handled."""
        if __debug__:
            log.debug("%s: pending(), async=%d", self.log_label,
                      self.is_async())
        if self.is_async():
            return
        # Inline the asyncore poll() function to know whether any input
        # was actually read.  Repeat until no input is ready.

        # Pending does reads and writes.  In the case of server
        # startup, we may need to write out zeoVerify() messages.
        # Always check for read status, but don't check for write status
        # only there is output to do.  Only continue in this loop as
        # long as there is data to read.
        r = r_in = [self._fileno]
        x_in = []
        while r and not self.closed:
            if self.writable():
                w_in = [self._fileno]
            else:
                w_in = []
            try:
                r, w, x = select.select(r_in, w_in, x_in, timeout)
            except select.error, err:
                if err[0] == errno.EINTR:
                    timeout = 0
                    continue
                else:
                    raise
            else:
                # Make sure any subsequent select does not block.  The
                # loop is only intended to make sure all incoming data is
                # returned.

                # XXX What if the server sends a lot of invalidations,
                # such that pending never finishes?  Seems unlikely, but
                # not impossible.
                timeout = 0
            if r:
                try:
                    self.handle_read_event()
                except asyncore.ExitNow:
                    raise
                except:
                    self.handle_error()
            if w:
                try:
                    self.handle_write_event()
                except asyncore.ExitNow:
                    raise
                except:
                    self.handle_error()

class ManagedServerConnection(Connection):
    """Server-side Connection subclass."""
    __super_init = Connection.__init__
    __super_close = Connection.close

    def __init__(self, sock, addr, obj, mgr):
        self.mgr = mgr
        self.__super_init(sock, addr, obj)
        self.obj.notifyConnected(self)

    def close(self):
        self.obj.notifyDisconnected()
        self.mgr.close_conn(self)
        self.__super_close()

class ManagedConnection(Connection):
    """Client-side Connection subclass."""
    __super_init = Connection.__init__
    __super_close = Connection.close

    def __init__(self, sock, addr, obj, mgr):
        self.mgr = mgr
        self.__super_init(sock, addr, obj)
        self.check_mgr_async()

    # PROTOCOL NEGOTIATION:
    #
    # The code implementing protocol version 2.0.0 (which is deployed
    # in the field and cannot be changed) *only* talks to peers that
    # send a handshake indicating protocol version 2.0.0.  In that
    # version, both the client and the server immediately send out
    # their protocol handshake when a connection is established,
    # without waiting for their peer, and disconnect when a different
    # handshake is receive.
    #
    # The new protocol uses this to enable new clients to talk to
    # 2.0.0 servers: in the new protocol, the client waits until it
    # receives the server's protocol handshake before sending its own
    # handshake.  The client sends the lower of its own protocol
    # version and the server protocol version, allowing it to talk to
    # servers using later protocol versions (2.0.2 and higher) as
    # well: the effective protocol used will be the lower of the
    # client and server protocol.
    #
    # The ZEO modules ClientStorage and ServerStub have backwards
    # compatibility code for dealing with the previous version of the
    # protocol.  The client accept the old version of some messages,
    # and will not send new messages when talking to an old server.
    #
    # As long as the client hasn't sent its handshake, it can't send
    # anything else; output messages are queued during this time.
    # (Output can happen because the connection testing machinery can
    # start sending requests before the handshake is received.)

    def handshake(self):
        self.message_input = self.recv_handshake
        self.message_output = self.queue_output
        self.output_queue = []
        # The handshake is sent by recv_handshake() below

    def queue_output(self, message):
        self.output_queue.append(message)

    def recv_handshake(self, proto):
        del self.message_output
        proto = min(proto, self.protocol_version)
        Connection.recv_handshake(self, proto) # Raise error if wrong proto
        self.message_output(proto)
        queue = self.output_queue
        del self.output_queue
        for message in queue:
            self.message_output(message)

    # Defer the ThreadedAsync work to the manager.

    def close_trigger(self):
        # the manager should actually close the trigger
        del self.trigger

    def set_async(self, map):
        pass

    def _prepare_async(self):
        # Don't do the register_loop_callback that the superclass does
        pass

    def check_mgr_async(self):
        if not self.thr_async and self.mgr.thr_async:
            assert self.mgr.trigger is not None, \
                   "manager (%s) has no trigger" % self.mgr
            self.thr_async = 1
            self.trigger = self.mgr.trigger
            return 1
        return 0

    def is_async(self):
        # XXX could the check_mgr_async() be avoided on each test?
        if self.thr_async:
            return 1
        return self.check_mgr_async()

    def close(self):
        self.mgr.close_conn(self)
        self.__super_close()
