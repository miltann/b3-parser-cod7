# -*- coding: utf-8 -*-

# ################################################################### #
#                                                                     #
#  BigBrotherBot(B3) (www.bigbrotherbot.net)                          #
#  Copyright (C) 2005 Michael "ThorN" Thornton                        #
#                                                                     #
#  This program is free software; you can redistribute it and/or      #
#  modify it under the terms of the GNU General Public License        #
#  as published by the Free Software Foundation; either version 2     #
#  of the License, or (at your option) any later version.             #
#                                                                     #
#  This program is distributed in the hope that it will be useful,    #
#  but WITHOUT ANY WARRANTY; without even the implied warranty of     #
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the       #
#  GNU General Public License for more details.                       #
#                                                                     #
#  You should have received a copy of the GNU General Public License  #
#  along with this program; if not, write to the Free Software        #
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA      #
#  02110-1301, USA.                                                   #
#                                                                     #
# ################################################################### #
#
# CHANGELOG
#
# 01.11.2019 - v1.3.3 - WatchMiltan
#   - modified regex format to work with teknoops (allows negative guids)
# 01.11.2019 - v1.3.4 - WatchMiltan
#   - removed cod7http deps
# 03.04.2019 - v1.4 - WatchMiltan
#   - fixed rcon commands and added maprotate
#   - ignores bots
#

__author__ = 'Freelander, Courgette, Just a baka, Bravo17, WatchMiltan'
__version__ = '1.4M'

import os
import b3
import re
import string
import b3.parsers.cod5
import b3.parsers.q3a.rcon

from threading import Timer


class Cod7Rcon(b3.parsers.q3a.rcon.Rcon):
    rconsendstring = '\xff\xff\xff\xff\x00%s %s\00'
    rconreplystring = '\xff\xff\xff\xff\x01print\n'


class Cod7Parser(b3.parsers.cod5.Cod5Parser):

    gameName = 'cod7'
    IpsOnly = False
    OutputClass = Cod7Rcon

    _guidLength = 5
    _usePreMatchLogic = True
    _preMatch = False
    _elFound = True
    _igBlockFound = False
    _sgFound = False
    _logTimer = 0
    _logTimerOld = 0

    _commands = {
        'message': 'tell %(cid)s %(message)s',
        'say': 'say %(message)s',
        'set': 'setadmindvar %(name)s "%(value)s"',
        'kick': 'clientkick %(cid)s "%(reason)s"',
        'ban': 'banclient %(cid)s',
        'unban': 'unbanuser "%(name)s"',
        'tempban': 'clientkick %(cid)s "%(reason)s"'
    }

    # Next actions need translation to the EVT_CLIENT_ACTION (Treyarch has a
    # different approach on actions). While IW put all EVT_CLIENT_ACTION in the A;
    # action, Treyarch creates a different action for each EVT_CLIENT_ACTION.
    _actionMap = (
        'AD', # Actor Damage (dogs)
        'VD'  # Vehicle Damage
    )

    # num score ping guid                             name            lastmsg address               qport rate
    # --- ----- ---- -------------------------------- --------------- ------- --------------------- ----- -----
    #   4     0   23 blablablabfa218d4be29e7168c637be ^1XLR^78^9or[^7       0 135.94.165.296:63564  25313 25000
    _regPlayer = re.compile(r'^(?P<slot>[0-9]+)\s+'
                            r'(?P<score>[0-9-]+)\s+'
                            r'(?P<ping>[0-9]+)\s+'
                            r'(?P<guid>[0-9-]+)\s+'
                            r'(?P<name>.*?)\s+'
                            r'(?P<last>[0-9]+)\s+'
                            r'(?P<ip>[0-9.]+):'
                            r'(?P<port>[0-9-]+)'
                            r'(?P<qportsep>[-\s]+)'
                            r'(?P<qport>[0-9-]+)\s+'
                            r'(?P<rate>[0-9]+)$', re.IGNORECASE)

    _regPlayerWithDemoclient = re.compile(r'^(?P<slot>[0-9]+)\s+'
                                             r'(?P<score>[0-9-]+)\s+'
                                             r'(?P<ping>[0-9]+)\s+'
                                             r'(?P<guid>[0-9-]+)\s+'
                                             r'(?P<name>.*?)\s+'
                                             r'(?P<last>[0-9]+)\s+'
                                             r'(?P<ip>[0-9.]+|unknown):?'
                                             r'(?P<port>[0-9-]+)?'
                                             r'(?P<qportsep>[-\s]+)'
                                             r'(?P<qport>[0-9-]+)\s+'
                                             r'(?P<rate>[0-9]+)$', re.IGNORECASE)

    ####################################################################################################################
    #                                                                                                                  #
    #   PARSER INITIALIZATION                                                                                          #
    #                                                                                                                  #
    ####################################################################################################################

    def startup(self):
        """
        Called after the parser is created before run().
        """
        # add the world client
        client = self.clients.newClient('-1', guid='WORLD', name='World', hide=True, pbid='WORLD')

        # get map from the status rcon command
        mapname = self.getMap()
        if mapname:
            self.game.mapName = mapname
            self.info('map is: %s'%self.game.mapName)

        if self.config.has_option('server', 'use_prematch_logic'):
            self._usePreMatchLogic = self.config.getboolean('server', 'use_prematch_logic')

        # Pre-Match Logic part 1
        if self._usePreMatchLogic:
            self._regPlayer, self._regPlayerWithDemoclient = self._regPlayerWithDemoclient, self._regPlayer
            playerList = self.getPlayerList()
            self._regPlayer, self._regPlayerWithDemoclient = self._regPlayerWithDemoclient, self._regPlayer
        
            if len(playerList) >= 4:
                self.verbose('PREMATCH OFF: PlayerCount >=4: not a Pre-Match')
                self._preMatch = False
            elif '0' in playerList and playerList['0']['guid'] == '0':
                self.verbose('PREMATCH OFF: Got a democlient presence: not a Pre-Match')
                self._preMatch = False
            else:
                self.verbose('PREMATCH ON: PlayerCount < 4, got no democlient presence: defaulting to a pre-match.')
                self._preMatch = True
        else:
            self._preMatch = False

        # Force g_logsync
        self.debug('Forcing server cvar g_logsync to %s and turning UNIX timestamp log timers off' % self._logSync)
        self.write('g_logsync %s' % self._logSync)
        self.write('g_logTimeStampInSeconds 0')
        self.setVersionExceptions()
        self.debug('parser started')

    def plugins_started(self):
        """
        Called after the parser loaded and started all plugins.
        """
        self.debug('Admin plugin not patched')

    ####################################################################################################################
    #                                                                                                                  #
    #   PARSING                                                                                                        #
    #                                                                                                                  #
    ####################################################################################################################

    def parse_line(self, line):
        """
        Parse a log line creating necessary events.
        :param line: The log line to be parsed
        """
        m = self.getLineParts(line)
        if not m:
            return False

        match, action, data, client, target = m
        func = 'On%s' % string.capwords(action).replace(' ','')
        # Timer (in seconds) that always reflects the current event's timestamp
        t = re.match(self._lineTime, line)
        if t:
            self._logTimerOld = self._logTimer
            self._logTimer = int(t.group('minutes')) * 60 + int(t.group('seconds'))

        # Pre-Match Logic part 2
        # Ignore Pre-Match K/D-events
        if self._preMatch and (func == 'OnD' or func == 'OnK' or func == 'OnAd' or func == 'OnVd'):
            self.verbose('PRE-MATCH: ignoring kill/damage')
            return False

        # Prevent OnInitgame from being called twice due to server-side initGame doubling
        elif func == 'OnInitgame':
            if not self._igBlockFound:
                self._igBlockFound = True
                self.verbose('found 1st InitGame from block')
            elif self._logTimerOld <= self._logTimer:
                self.verbose('found 2nd InitGame from block: ignoring')
                return False

        # ExitLevel means there will be Pre-Match right after the mapload
        elif self._usePreMatchLogic and func == 'OnExitlevel':
            self._preMatch = True
            self.debug('PRE-MATCH ON: found ExitLevel')
            self._elFound = True
            self._igBlockFound = False

        # If we track ShutdownGame events, we could detect sudden server restarts and re-matches
        elif func == 'OnShutdowngame':
            self._sgFound = True
            self._igBlockFound = False

        # Round switch (InitGame after ShutdownGame, but there was no ExitLevel):
        if self._preMatch and not self._elFound and self._igBlockFound and self._sgFound and self._logTimerOld <= self._logTimer:
            self._preMatch = False
            self.debug('PRE-MATCH OFF: found a round change')
            self._igBlockFound = False
            self._sgFound = False

        # Timer reset
        elif self._logTimerOld > self._logTimer:
            self.debug('Old timer: %s / New timer: %s' % (self._logTimerOld, self._logTimer))
            if self._usePreMatchLogic:
                self._preMatch = True
                self.debug('PRE-MATCH ON: Server crash/restart detected')
            else:
                self.debug('Server crash/restart detected')
            self._elFound = False
            self._igBlockFound = False
            self._sgFound = False

            # Payload
            self.write('setadmindvar g_logsync %s' % self._logSync)
            self.write('setadmindvar g_logTimeStampInSeconds 0')

        else:
            # Initgame after ExitLevel
            self._elFound = False
            self._sgFound = False

        #self.debug("-==== FUNC!!: " + func)

        if hasattr(self, func):
            func = getattr(self, func)
            event = func(action, data, match)

            if event:
                self.queueEvent(event)
        elif action in self._eventMap:
            self.queueEvent(self.getEvent(self._eventMap[action], data=data, client=client, target=target))
        elif action in self._actionMap:
            # Addition for cod7 actionMapping
            self.translateAction(action, data, match)
        else:
            self.queueEvent(self.getEvent('EVT_UNKNOWN', str(action) + ': ' + str(data), client, target))

    def read(self):
        """
        Read from game server log file.
        """
        # Getting the stats of the game log (we are looking for the size)
        filestats = os.fstat(self.input.fileno())

        # Compare the current cursor position against the current file size,
        # if the cursor is at a number higher than the game log size, then
        # there's a problem

        if self.input.tell() > filestats.st_size:
            self.debug('Parser: game log is suddenly smaller than it was before (%s bytes, now %s), '
                       'the log was probably either rotated or emptied. B3 will now re-adjust to the '
                       'new size of the log.' % (str(self.input.tell()), str(filestats.st_size)) )
            self.input.seek(0, os.SEEK_END)
        return self.input.readlines()

    ####################################################################################################################
    #                                                                                                                  #
    #   EVENT HANDLERS                                                                                                 #
    #                                                                                                                  #
    ####################################################################################################################

    def OnJ(self, action, data, match=None):
        codguid = match.group('guid')
        cid = match.group('cid')
        name = match.group('name')
        if codguid == '0' and '[3arc]' in name:
            self.verbose('Authentication not required, aborting join...')
            self._preMatch = 0
            return None
        
        if len(codguid) < self._guidLength:
            # invalid guid
            self.verbose2('Invalid GUID: %s' %codguid)
            codguid = None

        client = self.getClient(match)
        if client:
            self.verbose2('Client object already exists')
            # lets see if the name/guids match for this client, prevent player mixups after mapchange (not with PunkBuster enabled)
            if not self.PunkBuster:
                if self.IpsOnly:
                    # this needs testing since the name cleanup code may interfere with this next condition
                    if name != client.name:
                        self.debug('This is not the correct client (%s <> %s): disconnecting' %(name, client.name))
                        client.disconnect()
                        return None
                    else:
                        self.verbose2('client.name in sync: %s == %s' %(name, client.name))
                else:
                    if codguid != client.guid:
                        self.debug('This is not the correct client (%s <> %s): disconnecting' %(codguid, client.guid))
                        client.disconnect()
                        return None
                    else:
                        self.verbose2('client.guid in sync: %s == %s' %(codguid, client.guid))

            # update existing client
            client.state = b3.STATE_ALIVE
            # possible name changed
            client.name = name
            # Join-event for mapcount reasons and so forth
            return self.getEvent('EVT_CLIENT_JOIN', client=client)
        else:
            if self._counter.get(cid) and self._counter.get(cid) != 'Disconnected':
                self.verbose('cid: %s already in authentication queue: aborting join...' %cid)
                return None

            self._counter[cid] = 1
            t = Timer(2, self.newPlayer, (cid, codguid, name))
            t.start()
            self.debug('%s connected: waiting for authentication...' %name)
            self.debug('Our authentication queue: %s' % self._counter.__str__())

    def OnK(self, action, data, match=None):
        victim = self.clients.getByGUID(match.group('guid'))
        if not victim:
            self.debug('No victim %s' % match.groupdict())
            self.OnJ(action, data, match)
            return None

        attacker = self.clients.getByGUID(match.group('aguid'))
        if not attacker:
            if match.group('acid') == '-1' or match.group('aname') == 'world':
                self.verbose('World kill')
                attacker = self.getClient(attacker=match)
            else:
                self.debug('No attacker %s' % match.groupdict())
                return None

        # COD5 first version doesn't report the team on kill, only use it if it's set
        # Hopefully the team has been set on another event
        if match.group('ateam'):
            attacker.team = self.getTeam(match.group('ateam'))

        if match.group('team'):
            victim.team = self.getTeam(match.group('team'))

        eventkey = 'EVT_CLIENT_KILL'
        if attacker == victim or attacker.cid == '-1':
            self.verbose('Suicide detected: attacker.cid: %s, victim.cid: %s' % (attacker.cid, victim.cid))
            eventkey = 'EVT_CLIENT_SUICIDE'
        elif attacker.team != b3.TEAM_UNKNOWN and attacker.team and victim.team and attacker.team == victim.team:
            self.verbose('Team kill detected: %s team killed %s' % (attacker.name, victim.name))
            eventkey = 'EVT_CLIENT_KILL_TEAM'

        victim.state = b3.STATE_DEAD
        data = (float(match.group('damage')), match.group('aweap'), match.group('dlocation'), match.group('dtype'))
        return self.getEvent(eventkey, data=data, client=attacker, target=victim)
        
    def maprotate(self):
        """
        Changes the map.
        """
        self.output.write('map_rotate')
