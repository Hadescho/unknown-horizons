# ###################################################
# Copyright (C) 2009 The Unknown Horizons Team
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

import horizons.main
import shutil
import os.path
import ext.simplejson as simplejson
import user

class Setting(object):
	""" Class to store settings
	@param name:
	"""
	def __init__(self, name = ''):
		self._name = name
		self._categorys = []
		self._listener = []
		try:
			import config
			for option in config.__dict__:
				if option.startswith(name) and '.' not in option[len(name):]:
					self.__dict__[option[len(name):]] = getattr(config, option)
		except ImportError:
			pass
		for (option, value) in horizons.main.db("select substr(name, ?, length(name)), value from config.config where substr(name, 1, ?) = ? and substr(name, ?, length(name)) NOT LIKE '%.%'", len(name) + 1, len(name), name, len(name) + 1):
			if not option in self.__dict__:
				self.__dict__[option] = simplejson.loads(value)
				if isinstance(self.__dict__[option], unicode):
					self.__dict__[option] = str(self.__dict__[option])

	def __getattr__(self, name):
		"""
		@param name:
		"""
		assert(not name.startswith('_'))
		return None

	def __setattr__(self, name, value):
		"""
		@param name:
		@param value:
		"""
		self.__dict__[name] = value
		if not name.startswith('_'):
			assert(name not in self._categorys)
			horizons.main.db("replace into config.config (name, value) values (?, ?)", self._name + name, simplejson.dumps(value))
			for listener in self._listener:
				listener(self, name, value)

	def addChangeListener(self, listener):
		"""
		@param listener:
		"""
		for name in self._categorys:
			self.__dict__[name].addChangeListener(listener)
		self._listener.append(listener)
		for name in self.__dict__:
			if not name.startswith('_'):
				listener(self, name, getattr(self, name))

	def delChangeListener(self, listener):
		"""
		@param listener:
		"""
		for name in self._categorys:
			self.__dict__[name].delChangeListener(listener)
		self._listener.remove(listener)

	def setDefaults(self, **defaults):
		"""
		@param **defaults:
		"""
		for name in defaults:
			assert(not name.startswith('_'))
			assert(name not in self._categorys)
			if not name in self.__dict__:
				self.__dict__[name] = defaults[name]
				for listener in self._listener:
					listener(self, name, defaults[name])

	def addCategorys(self, *categorys):
		"""Adds one or more setting categories

		The new categories can be accessed via
		settingsObj.NEWCATEGORY
		@param *categorys:
		"""
		for category in categorys:
			self._categorys.append(category)
			inst = Setting(self._name + category + '.')
			self.__dict__[category] = inst
			for listener in self._listener:
				inst.addChangeListener(listener)

class Settings(Setting):
	VERSION = 2
	"""
	@param config:
	"""
	def __init__(self, config = '%s/.unknown-horizons/config.sqlite' % user.home):
		if not os.path.exists(config):
			if not os.path.exists(os.path.dirname(config)):
				os.makedirs(os.path.dirname(config))
			shutil.copyfile('content/config.sqlite', config)
		horizons.main.db("ATTACH ? AS config", config)
		version = horizons.main.db("PRAGMA config.user_version")[0][0]
		if version > Settings.VERSION:
			print _("Error: Config version not supported, creating empty config which wont be saved.")
			horizons.main.db("DETACH config")
			horizons.main.db("ATTACH ':memory:' AS config")
			horizons.main.db("CREATE TABLE config.config (name TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)")
		elif version < Settings.VERSION:
			print _("Upgrading Config from Version %d to Version %d ...") % (version, Settings.VERSION)
			if version == 1:
				horizons.main.db("UPDATE config.config SET name = REPLACE(name, '_', '.') WHERE name != 'client_id'")
				version = 2
			horizons.main.db("PRAGMA config.user_version = " + str(Settings.VERSION))
		super(Settings, self).__init__()
