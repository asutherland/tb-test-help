#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright (C) 2008 Ilpo Nyyssönen
# Created: Sun Sep  7 08:04:06 2008 [biny]

# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:

# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND,
# EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
# MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
# NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE
# LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
# WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.


"""
Simple memory IMAP4 server. Intended for testing twited.mail.imap4 and
as a sample server.
"""

__author__ = 'Ilpo Nyyssönen <iny+dev@iki.fi>'

import sys
import re
import os
import cStringIO
import functools
from email import parser, iterators

from zope import interface

from twisted.cred import portal
from twisted.internet import reactor, defer, protocol
from twisted.mail import imap4
from twisted.python import log

RETURN_DEFERREDS = False

def maybeReturnDeferred(result):
    if RETURN_DEFERREDS:
        d = defer.Deferred()
        reactor.callLater(1, d.callback, result)
        return d
    return result

emailparser = parser.Parser()

def trace(func):
    @functools.wraps(func)
    def wrapper(*args, **kw):
        log.msg(func, args, kw)
        try:
            return func(*args, **kw)
        except Exception, exc:
            log.err()
            raise
    return wrapper

class Part(object):
    interface.implements(imap4.IMessagePart)

    def __init__(self, message):
        self.message = message
        self._lines = None

    @property
    def lines(self):
        if self._lines is None:
            self._lines = imap4.getLineCount(self)
        return self._lines

    def getSize(self):
        return len(self.getBodyFile().read())

    def getHeaders(self, negate, *names):
        names = set((name.lower() for name in names))
        if negate:
            headers = set((name.lower() for name in self.message.keys()))
            headers -= set(names)
        else:
            headers = set(names)
        return dict(((name, self.message[name])
                     for name in headers
                     if name in self.message))

    def isMultipart(self):
        return self.message.is_multipart()

    def getSubPart(self, index):
        return Part(self.message.get_payload(index))

    def getBodyFile(self):
        stream = cStringIO.StringIO()
        lines = iterators.body_line_iterator(self.message)
        for line in lines:
            if not line:
                break
        for line in lines:
            stream.write(line)
        stream.seek(0)
        return stream

class Message(Part):
    interface.implements(imap4.IMessage)

    def __init__(self, mailbox, uid, date, stream):
        self.mailbox = mailbox
        self.uid = uid
        Part.__init__(self, emailparser.parse(stream))

        if date is None:
            self.date = self.message['date']
        else:
            self.date = date

    def getUID(self):
        return self.uid

    def getFlags(self):
        return [flag
                for flag, uids in self.mailbox.flags.items()
                if self.uid in uids]

    def getInternalDate(self):
        return self.date

class Mailbox(object):
    interface.implements(imap4.IMailbox)

    def __init__(self, account, name):
        self.account = account
        self.name = name
        self.uidnext = 1

        self.messages = []
        self.uids = {}
        self.flags = {}

        self.listeners = []
        self.addListener = self.listeners.append
        self.removeListener = self.listeners.remove

    def getKeys(self, messages, uid):
        if not messages.last:
            messages.last = self.uidnext - 1 if uid else len(self.messages)
        if uid:
            result = [(self.uids[uid], uid)
                      for uid in messages
                      if uid in self.uids]
        else:
            result = [(seq, self.messages[seq - 1].getUID())
                      for seq in messages
                      if 0 <= seq - 1 < len(self.messages)]
        return result

    def getFlag(self, flag):
        flag = flag.lower()
        if flag not in self.flags:
            self.flags[flag] = set()
        return self.flags[flag]
    
    @property
    def recent(self): return self.getFlag('\Recent')
    @property
    def unseen(self): return self.getFlag('\Unseen')
    @property
    def deleted(self): return self.getFlag('\Deleted')

    def getUID(self, seq):
        return self.message[seq - 1].getUID()

    def getFlags(self):
        return ()

    def getHierarchicalDelimiter(self):
        return '.'

    def getUIDValidity(self):
        return 1

    def getUIDNext(self):
        return self.uidnext

    def isWriteable(self):
        return self.rw

    def getMessageCount(self):
        return len(self.messages)

    def getRecentCount(self):
        return len(self.recent)

    def getUnseenCount(self):
        return len(self.unseen)

    def requestStatus(self, names):
        return imap4.statusRequestHelper(self, names)

    def addMessage(self, stream, flags = (), date = None):
        if not self.rw:
            raise imap4.ReadOnlyMailbox()

        seq = len(self.messages) + 1
        uid = self.uidnext
        self.uidnext += 1
        message = Message(self, uid, date, stream)
        self.messages.append(message)
        self.uids[uid] = seq
        if flags:
            for flag in flags:
                self.getFlag(flag).add(uid)

        return defer.succeed(uid)

    def store(self, messages, flags, mode, uid):
        if not self.rw:
            raise imap4.ReadOnlyMailbox()

        keys = self.getKeys(messages, uid)

        if mode == 0:
            for flag in flags:
                self.getFlag(flag).clear()

        result = {}
        
        for seq, uid in keys:
            for flag in flags:
                stored = self.getFlag(flag)
                if mode < 0:
                    stored.discard(uid)
                else:
                    stored.add(uid)
            result[seq] = self.messages[seq - 1].getFlags()

        return maybeReturnDeferred(result)
                        
    def fetch(self, messages, uid):
        keys = self.getKeys(messages, uid)
        result = [(seq, self.messages[seq - 1]) for seq, uid in keys]
        return maybeReturnDeferred(result)

    def expunge(self):
        if not self.rw:
            raise imap4.ReadOnlyMailbox()

        seq = 1
        messages = self.messages
        self.messages = []
        result = []
        for message in messages:
            uid = message.getUID()
            
            if uid in self.deleted:
                result.append(seq)
                del self.uids[uid]
                for flags in self.flags.values():
                    flags.discard(uid)
            else:
                self.messages.append(message)
                self.uids[uid] = seq
                seq += 1

        return maybeReturnDeferred(result)

class Account(object):
    interface.implements(imap4.IAccount, imap4.INamespacePresenter)

    def __init__(self, factory, username):
        self.factory = factory
        self.username = username
        self.mailboxes = {'INBOX': Mailbox(self, 'INBOX')}
        self.subscribed = set()

    def close(self):
        pass

    def listMailboxes(self, ref, wildcard):
        wildcard = (ref + wildcard).replace('.', '\.')
        wildcard = wildcard.replace('*', '(?:.*?)')
        wildcard = wildcard.replace('%', '(?:(?:[^.])*?)')
        wildcard = re.compile(wildcard + '$', re.I)

        names = self.mailboxes.keys()

        hierarchies = set()
        for name in names:
            parts = name.split('.')
            for i in xrange(1, len(parts)):
                hierarchies.add('.'.join(parts[:i]))

        result = [(name, hierarchy)
                  for name in sorted(hierarchies)
                  if wildcard.match(name)]

        for name in names:
            if wildcard.match(name):
                result.append((name, self.mailboxes[name]))

        return result
        
    def select(self, name, rw = True):
        mbox = self.mailboxes.get(name)
        if mbox is not None:
            mbox.rw = rw
        return mbox

    def create(self, pathspec):
        self.mailboxes[pathspec] = Mailbox(self, pathspec)
        return True

    def delete(self, name):
        if name in self.mailboxes:
            del self.mailboxes[name]
            return True

    def isSubscribed(self, name):
        return name in self.subscribed

    def subscribe(self, name):
        self.subscribed.add(name)

    def unsubscribe(self, name):
        self.subscribed.discard(name)

    def getPersonalNamespaces(self):
        return "", '.'

    def getSharedNamespaces(self):
        return None

    def getOtherNamespaces(self):
        return None

class ServerFactory(protocol.ServerFactory):
    interface.implements(portal.IRealm)

    def __init__(self):
        self.portal = portal.Portal(self)
        self.accounts = {}

    def requestAvatar(self, avatarId, mind, *interfaces):
        assert imap4.IAccount in interfaces, repr(interfaces)
        if avatarId in self.accounts:
            account = self.accounts[avatarId]
        else:
            account = Account(self, avatarId)
            self.accounts[avatarId] = account
        return imap4.IAccount, account, account.close

    def buildProtocol(self, addr):
        p = imap4.IMAP4Server()
        p.portal = self.portal
        return p

def main():
    from twisted.cred import checkers

    log.startLogging(sys.stdout)

    factory = ServerFactory()

    checker = checkers.InMemoryUsernamePasswordDatabaseDontUse()
    checker.addUser(os.environ['USER'], 'pass')
    factory.portal.registerChecker(checker)

    reactor.listenTCP(8143, factory)
    reactor.run()

if __name__ == '__main__': main()
