# Embedded file name: mud\client\irc.pyo
import traceback
from tgenative import *
from mud.tgepython.console import TGEExport
from twisted.words.protocols import irc
from twisted.internet import reactor, protocol
from mud.world.defines import *
from mud.client.playermind import formatMLString
from mud.gamesettings import *
from gui.tomeGui import TomeGui
receiveGameText = TomeGui.instance.receiveGameText
receiveSpeechText = TomeGui.instance.receiveSpeechText
import re
DISCONNECT = False
IRC = None
USERNAME = ''
MUTETIME = 0
GLOBAL_ON = True
HELP_ON = True
OT_ON = True
MAX_RESPONDERS = 10
CURRENT_RESPONDER_INDEX = 0
RESPONDER_LIST = []
TOME_CMD_CTRL = None
CUSTOM_AWAY_PREFIX = 'Away Message:'
DEFAULT_AWAY_MSG = 'Sorry, I am away right now.'
AWAY_MSG = DEFAULT_AWAY_MSG
PLAYER_IS_AWAY = False
STRIPMULTISPACES = re.compile(' +')

def SetAwayMessage(msg):
    global AWAY_MSG
    global PLAYER_IS_AWAY
    if msg:
        PLAYER_IS_AWAY = True
        msg = STRIPMULTISPACES.sub(' ', msg)
        AWAY_MSG = '%s %s' % (CUSTOM_AWAY_PREFIX, msg)
        receiveSpeechText(RPG_MSG_SPEECH_SYSTEM, 'You are away.\\n')
    else:
        PLAYER_IS_AWAY = not PLAYER_IS_AWAY
        if PLAYER_IS_AWAY:
            AWAY_MSG = DEFAULT_AWAY_MSG
            receiveSpeechText(RPG_MSG_SPEECH_SYSTEM, 'You are away.\\n')
        else:
            receiveSpeechText(RPG_MSG_SPEECH_SYSTEM, 'You are no longer away.\\n')


def AddTeller(lastTeller):
    global CURRENT_RESPONDER_INDEX
    global RESPONDER_LIST
    CURRENT_RESPONDER_INDEX = 0
    for index, responder in enumerate(RESPONDER_LIST):
        if responder == lastTeller:
            if index:
                del RESPONDER_LIST[index]
                RESPONDER_LIST.insert(0, lastTeller)
            break
    else:
        RESPONDER_LIST.insert(0, lastTeller)
        if MAX_RESPONDERS == len(RESPONDER_LIST):
            RESPONDER_LIST.pop()


def CycleReply(args):
    global CURRENT_RESPONDER_INDEX
    global TOME_CMD_CTRL
    if not TOME_CMD_CTRL:
        return
    TGECall('PushChatGui')
    TOME_CMD_CTRL.visible = True
    TOME_CMD_CTRL.makeFirstResponder(True)
    if not RESPONDER_LIST:
        TOME_CMD_CTRL.setValue('/tell ')
        return
    cycleDirection = int(args[1])
    if -1 == cycleDirection:
        if CURRENT_RESPONDER_INDEX:
            CURRENT_RESPONDER_INDEX -= 1
        else:
            CURRENT_RESPONDER_INDEX = len(RESPONDER_LIST) - 1
    elif 1 == cycleDirection:
        if len(RESPONDER_LIST) - 1 != CURRENT_RESPONDER_INDEX:
            CURRENT_RESPONDER_INDEX += 1
        else:
            CURRENT_RESPONDER_INDEX = 0
    TOME_CMD_CTRL.setValue('/tell %s ' % RESPONDER_LIST[CURRENT_RESPONDER_INDEX])


def SetMuteTime(t):
    global MUTETIME
    if MUTETIME and not t:
        receiveSpeechText(RPG_MSG_SPEECH_SYSTEM, 'You are no longer muted.\\n')
    if not MUTETIME and t:
        m = t / 60 + 1
        if m > 59:
            receiveSpeechText(RPG_MSG_SPEECH_ERROR, 'You have been muted.\\n')
        else:
            receiveSpeechText(RPG_MSG_SPEECH_ERROR, 'You have been muted and will be able to speak in %i minutes.\\n' % m)
    MUTETIME = t


def CheckMuted():
    if MUTETIME:
        m = MUTETIME / 60 + 1
        if m > 59:
            receiveSpeechText(RPG_MSG_SPEECH_ERROR, 'You have been muted.\\n')
        else:
            receiveSpeechText(RPG_MSG_SPEECH_ERROR, 'You have been muted and will be able to speak in %i minutes.\\n' % m)
        return True
    return False


def FilterChannel(channel, value):
    global OT_ON
    global HELP_ON
    global GLOBAL_ON
    if channel in ('O', 'OFFTOPIC'):
        OT_ON = value
    elif channel in ('H', 'HELP'):
        HELP_ON = value
    elif channel in ('M', 'MOM'):
        GLOBAL_ON = value


class MyIRCClient(irc.IRCClient):

    def connectionMade(self):
        global IRC
        IRC = self
        self.nickname = self.factory.nickname
        irc.IRCClient.connectionMade(self)

    def connectionLost(self, reason):
        global IRC
        IRC = None
        irc.IRCClient.connectionLost(self, reason)
        return

    def irc_ERR_NOSUCHNICK(self, prefix, params):
        mynick, their_nick, error = params
        receiveSpeechText(RPG_MSG_SPEECH_ERROR, '%s is not currently logged in.  If you are messaging a monster, please replace any spaces in their name with underscores.\\n' % their_nick)

    def irc_RPL_NAMREPLY(self, prefix, params):
        pass

    def userJoined(self, user, channel):
        pass

    def userLeft(self, user, channel):
        pass

    def userQuit(self, user, quitMessage):
        pass

    def userKicked(self, kickee, channel, kicker, message):
        pass

    def topicUpdated(self, user, channel, newTopic):
        pass

    def userRenamed(self, oldname, newname):
        pass

    def receivedMOTD(self, motd):
        pass

    def signedOn(self):
        self.join('#prairiegames')
        self.join('#pg_global')
        self.join('#pg_help')

    def joined(self, channel):
        self.live = True
        if channel == '#prairiegames':
            receiveSpeechText(RPG_MSG_SPEECH_HELP, 'You have joined chat.\\n')

    def privmsg(self, user, channel, msg):
        if not self.live:
            return
        if DISCONNECT:
            self.sendLine('QUIT :%s' % 'Errant IRC connection closed')
            return
        if channel == '#prairiegames' and not OT_ON:
            return
        if channel == '#pg_global' and not GLOBAL_ON:
            return
        if channel == '#pg_help' and not HELP_ON:
            return
        user = user.split('!', 1)[0]
        userPretty = user.replace('_', ' ')
        msg = msg.replace('\\', '')
        msg = formatMLString(msg)
        from gui.playerSettings import PLAYERSETTINGS
        if userPretty.upper() in PLAYERSETTINGS.ignored:
            return
        if channel.upper() == self.nickname.upper():
            try:
                if int(TGEGetGlobal('$pref::gameplay::OpenChatOnTells')):
                    TGECall('PushChatGui')
            except:
                TGESetGlobal('$pref::gameplay::OpenChatOnTells', 0)

            receiveSpeechText(RPG_MSG_SPEECH_TELL, '<a:gamelinkcharlink%s>%s</a> tells you, \\"%s\\"\\n' % (user, userPretty, msg))
            if PLAYER_IS_AWAY:
                userUpper = user.upper()
                if 'MOM' != userUpper and channel.upper() != userUpper and not msg.startswith(DEFAULT_AWAY_MSG) and not msg.startswith(CUSTOM_AWAY_PREFIX):
                    receiveSpeechText(RPG_MSG_SPEECH_TOLD, 'You tell <a:gamelinkcharlink%s>%s</a>, \\"%s\\"\\n' % (user, userPretty, formatMLString(AWAY_MSG)))
                    self.msg(user, AWAY_MSG)
            AddTeller(user)
        elif channel == '#pg_global':
            receiveSpeechText(RPG_MSG_SPEECH_GLOBAL, 'MoM: <<a:gamelinkcharlink%s>%s</a>> %s\\n' % (user, userPretty, msg))
        elif channel == '#pg_help':
            receiveSpeechText(RPG_MSG_SPEECH_HELP, 'Help: <<a:gamelinkcharlink%s>%s</a>> %s\\n' % (user, userPretty, msg))
        elif channel == '#prairiegames':
            receiveSpeechText(RPG_MSG_SPEECH_OT, 'OT: <<a:gamelinkcharlink%s>%s</a>> %s\\n' % (user, userPretty, msg))

    def action(self, user, channel, msg):
        suser = user.split('!', 1)[0]
        user = suser.replace('_', ' ')
        from gui.playerSettings import PLAYERSETTINGS
        if user.upper() in PLAYERSETTINGS.ignored:
            return
        try:
            text = str(msg)
            text = text.split(' ')
            cmd = text[0].upper()
            if cmd == 'IMM' and len(text) >= 2:
                args = text[1:]
                from mud.client.playermind import PLAYERMIND
                PLAYERMIND.perspective.callRemote('ImmortalAvatar', 'command', args[0], args[1:])
        except:
            traceback.print_exc()

        if channel == '#prairiegames' and not OT_ON:
            return
        if channel == '#pg_global' and not GLOBAL_ON:
            return
        if channel == '#pg_help' and not HELP_ON:
            return
        msg = msg.replace('\\', '')
        receiveSpeechText(RPG_MSG_SPEECH_EMOTE, '<a:gamelinkcharlink%s>%s</a> %s\\n' % (suser, user, formatMLString(msg)))


class IRCFactory(protocol.ClientFactory):

    def __init__(self, nickname, channel):
        self.nickname = nickname
        self.channel = channel
        self.protocol = MyIRCClient

    def buildProtocol(self, addr):
        print 'IRCFactory %s' % addr.host
        p = protocol.ClientFactory.buildProtocol(self, addr)
        p.live = False
        p.nickname = self.nickname
        return p


def ChangeNick(name):
    name = name.replace(' ', '_')
    try:
        IRC.setNick(name)
    except:
        pass


def IRCConnect(name):
    global IRC
    global PLAYER_IS_AWAY
    global TOME_CMD_CTRL
    if IRC:
        try:
            IRCDisconnect()
        except:
            pass

        IRC = None
    if LOCALTEST:
        return
    else:
        PLAYER_IS_AWAY = False
        TOME_CMD_CTRL = TomeGui.instance.tomeCommandCtrl
        name = name.replace(' ', '_')
        factory = IRCFactory(name, '#pg_global')
        reactor.connectTCP(IRC_IP, IRC_PORT, factory, timeout=DEF_TIMEOUT)
        receiveSpeechText(RPG_MSG_SPEECH_HELP, 'Connecting to Prairie Games, Inc chat services.\\n')
        return


def IRCDisconnect():
    global IRC
    if IRC:
        i = IRC
        IRC = None
        i.transport.loseConnection()
    return


def GlobalMsg(msg):
    if not IRC or not len(msg) or CheckMuted():
        return
    name = IRC.nickname
    sname = name.replace('_', ' ')
    receiveSpeechText(RPG_MSG_SPEECH_GLOBAL, 'MoM: <<a:gamelinkcharlink%s>%s</a>> %s\\n' % (name, sname, formatMLString(msg)))
    IRC.msg('#pg_global', msg)


def OTMsg(msg):
    if not IRC or not len(msg) or CheckMuted():
        return
    name = IRC.nickname
    sname = name.replace('_', ' ')
    receiveSpeechText(RPG_MSG_SPEECH_OT, 'OT: <<a:gamelinkcharlink%s>%s</a>> %s\\n' % (name, sname, formatMLString(msg)))
    IRC.msg('#prairiegames', msg)


def HelpMsg(msg):
    if not IRC or not len(msg) or CheckMuted():
        return
    name = IRC.nickname
    sname = name.replace('_', ' ')
    receiveSpeechText(RPG_MSG_SPEECH_HELP, 'Help: <<a:gamelinkcharlink%s>%s</a>> %s\\n' % (name, sname, formatMLString(msg)))
    IRC.msg('#pg_help', msg)


def SendIRCMsg(channel, msg):
    if CheckMuted():
        return
    msg = msg.replace('\\', '')
    if channel in ('O', 'OFFTOPIC'):
        OTMsg(msg)
    if channel in ('H', 'HELP'):
        HelpMsg(msg)
    if channel in ('M', 'MOM'):
        GlobalMsg(msg)


def IRCTell(nick, msg):
    global CURRENT_RESPONDER_INDEX
    if CheckMuted():
        return
    receiveSpeechText(RPG_MSG_SPEECH_TOLD, 'You tell <a:gamelinkcharlink%s>%s</a>, \\"%s\\"\\n' % (nick.replace(' ', '_'), nick, formatMLString(msg).replace('\\', '\\\\')))
    IRC.msg(nick, msg)
    CURRENT_RESPONDER_INDEX = 0


def IRCEmote(lastchannel, emote):
    if CheckMuted():
        return
    channel = '#prairiegames'
    if lastchannel in ('M', 'MOM'):
        channel = '#pg_global'
    elif lastchannel in ('H', 'HELP'):
        channel = '#pg_help'
    name = IRC.nickname
    sname = name.replace('_', ' ')
    receiveSpeechText(RPG_MSG_SPEECH_EMOTE, '<a:gamelinkcharlink%s>%s</a> %s.\\n' % (name, sname, formatMLString(emote)))
    IRC.ctcpMakeQuery(channel, [('ACTION', emote)])