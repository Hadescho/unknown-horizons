# ###################################################
# Copyright (C) 2012 The Unknown Horizons Team
# team@unknown-horizons.org
# This file is part of Unknown Horizons.
#
# Unknown Horizons is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the
# Free Software Foundation, Inc.,
# 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
# ###################################################

import logging

from horizons.network import packets
from horizons.network.connection import Connection
from horizons import network
from horizons.network.common import *


class ClientMode(object):
	Server = 0
	Game = 1

class Client(object):
	log = logging.getLogger("network")

	def __init__(self, server_address, client_address=None):
		self.connection = Connection(self.process_async_packet, server_address, client_address)

		self.mode          = None
		self.sid           = None
		self.capabilities  = None
		self.game          = None

		self._callback_types = ('lobbygame_chat', 'lobbygame_join', 'lobbygame_leave',
		                        'lobbygame_terminate', 'lobbygame_toggleready',
		                        'lobbygame_changename', 'lobbygame_kick',
		                        'lobbygame_changecolor', 'lobbygame_state',
		                        'lobbygame_starts', 'game_starts', 'game_data')

		self._callbacks = dict((t, []) for t in self._callback_types)

	def subscribe(self, type, callback, prepend=False):
		if type not in self._callback_types:
			raise TypeError("Unsupported type")

		if prepend:
			self._callbacks[type].insert(0, callback)
		else:
			self._callbacks[type].append(callback)

	def broadcast(self, type, *args, **kwargs):
		if not type in self._callback_types:
			return

		for cb in self._callbacks[type]:
			cb(*args, **kwargs)

	#-----------------------------------------------------------------------------

	def connect(self):
		packet = self.connection.connect()
		self.sid = packet[1].sid
		self.capabilities = packet[1].capabilities
		self.mode = ClientMode.Server
		self.log.debug("[CONNECT] done (session=%s)" % (self.sid))

	#-----------------------------------------------------------------------------

	def disconnect(self, **kwargs):
		self.mode = None
		self.connection.disconnect(**kwargs)

	#-----------------------------------------------------------------------------

	def reset(self):
		self.connection.reset()
		self.mode = None
		self.game = None

	#-----------------------------------------------------------------------------

	def send(self, packet, channelid=0):
		if self.mode is ClientMode.Game:
			packet = packets.client.game_data(packet)

		self.connection.send(packet, channelid)

	#-----------------------------------------------------------------------------

	# return True if packet was processed successfully
	# return False if packet should be queue
	def process_async_packet(self, packet):
		if packet is None:
			return True
		if isinstance(packet[1], packets.server.cmd_chatmsg):
			# ignore packet if we are not a game lobby
			if self.game is None:
				return True
			self.broadcast("lobbygame_chat", self.game, packet[1].playername, packet[1].chatmsg)
		elif isinstance(packet[1], packets.server.data_gamestate):
			# ignore packet if we are not a game lobby
			if self.game is None:
				return True
			self.broadcast("lobbygame_state", self.game, packet[1].game)

			oldplayers = list(self.game.players)
			self.game = packet[1].game

			# calculate changeset
			for pnew in self.game.players:
				found = None
				for pold in oldplayers:
					if pnew.sid == pold.sid:
						found = pold
						myself = (pnew.sid == self.sid)
						if pnew.name != pold.name:
							self.broadcast("lobbygame_changename", self.game, pold, pnew, myself)
						if pnew.color != pold.color:
							self.broadcast("lobbygame_changecolor", self.game, pold, pnew, myself)
						if pnew.ready != pold.ready:
							self.broadcast("lobbygame_toggleready", self.game, pold, pnew, myself)
						break
				if found is None:
					self.broadcast("lobbygame_join", self.game, pnew)
				else:
					oldplayers.remove(found)
			for pold in oldplayers:
				self.broadcast("lobbygame_leave", self.game, pold)
			return True
		elif isinstance(packet[1], packets.server.cmd_preparegame):
			# ignore packet if we are not a game lobby
			if self.game is None:
				return True
			self.ongameprepare()
		elif isinstance(packet[1], packets.server.cmd_startgame):
			# ignore packet if we are not a game lobby
			if self.game is None:
				return True
			self.ongamestart()
		elif isinstance(packet[1], packets.client.game_data):
			self.log.debug("[GAMEDATA] from %s" % (packet[0].address))
			self.broadcast("game_data", packet[1].data)
		elif isinstance(packet[1], packets.server.cmd_kickplayer):
			player = packet[1].player
			game = self.game
			myself = (player.sid == self.sid)
			if myself:
				# this will destroy self.game
				self.assert_connection()
				self.assert_lobby()
				self.log.debug("[LEAVE]")
				self.game = None
			self.broadcast("lobbygame_kick", game, player, myself)

		return False

	def assert_connection(self):
		if self.mode is None:
			raise network.NotConnected()
		if self.mode is not ClientMode.Server:
			raise network.NotInServerMode("We are not in server mode")

	def assert_lobby(self):
		if self.game is None:
			raise network.NotInGameLobby("We are not in a game lobby")

	#-----------------------------------------------------------------------------

	def ongameprepare(self):
		self.log.debug("[GAMEPREPARE]")
		self.game.state = Game.State.Prepare
		self.broadcast("lobbygame_starts", self.game)
		self.send(packets.client.cmd_preparedgame())
		return True

	#-----------------------------------------------------------------------------

	def ongamestart(self):
		self.log.debug("[GAMESTART]")
		self.game.state = Game.State.Running
		self.mode = ClientMode.Game
		self.broadcast("game_starts", self.game)
		return True
