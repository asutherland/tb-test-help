from zope.interface import implements, Interface

from twisted.internet.protocol import Factory
from twisted.protocols import basic
from twisted.internet import reactor

from twisted.internet import defer

from twisted.mail.pop3 import POP3, IMailbox, Mailbox
from twisted.cred.checkers import InMemoryUsernamePasswordDatabaseDontUse
from twisted.cred.portal import IRealm, Portal

from StringIO import StringIO

import datetime
import email.message, email.utils
import random

CredChecker = InMemoryUsernamePasswordDatabaseDontUse

PEOPLE = [
    'Alice <alice@example.com>',
    'Bob <bob@example.com>',
    'Cecelia <cecilia@example.com>',
    'Darren <darren@example.com>',
    ]

TOPIC_PARTS = [
    'Purple', 'Green', 'Yellow',
    'Monkey', 'Horse', 'Cow',
    'Laser', 'Death-Ray', 'Rainbow',
    'Soup', 'Crackers', 'Spoon',
    ]

class DeletedMessage(object):
    def __call__(self):
        return self
    def __str__(self):
        return ''
    def as_string(self, blah=False):
        return ''

DeletedMessage = DeletedMessage()

MESSAGES_PER_FETCH = 100

class DummyBox:
    implements(IMailbox)

    def __init__(self):
        self.messages = [self._createMessage() for x in range(MESSAGES_PER_FETCH)]
        self.committed = self.messages[:]

    def _createMessage(self):
        msg = email.message.Message()
        msg['From'] = random.choice(PEOPLE)
        msg['To'] = random.choice(PEOPLE)
        msg['Subject'] = (random.choice(TOPIC_PARTS) + ' ' +
                          random.choice(TOPIC_PARTS))
        msg['Date'] = email.utils.formatdate()
        msg['Message-ID'] = email.utils.make_msgid()
        msg.set_payload('Party down!')

        return msg

    def listMessages(self, index=None):
        if index is None:
            return [len(m.as_string(True)) for m in self.messages]
        return len(self.messages[index].as_string(True))

    def getMessage(self, index):
        return StringIO(self.messages[index].as_string(True))

    def getUidl(self, index):
        return self.messages[index]['Message-ID']

    def deleteMessage(self, index):
        self.messages[index] = DeletedMessage

    def undeleteMessages(self):
        self.messages = self.committed[:]

    def sync(self):
        self.committed = self.messages[:]

def nop():
    pass

class DummyRealm:
    implements(IRealm)

    def requestAvatar(self, avatarId, mind, *interfaces):
        print 'Requesting Avatar', avatarId, mind, interfaces
        return (IMailbox, DummyBox(), nop)

import twisted.python.failure as tpf

def main():
    credChecker = CredChecker()
    credChecker.addUser('foo', 'bar')

    print 'Defined Users:', credChecker.users

    realm = DummyRealm()

    f = Factory()
    f.protocol = POP3
    f.portal = Portal(realm, (credChecker,))
    f.protocol.portal = f.portal

    print 'Portal Credential Interfaces', f.portal.listCredentialsInterfaces()

    PORT = 2110
    print 'PORT', PORT

    tpf.startDebugMode()

    reactor.listenTCP(PORT, f)
    reactor.run()

if __name__ == '__main__':
    main()
