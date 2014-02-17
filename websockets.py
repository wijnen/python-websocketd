# Python module for serving WebSockets and web pages.
# vim: set fileencoding=utf-8 foldmethod=marker :

# {{{ Copyright 2013-2014 Bas Wijnen <wijnen@debian.org>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
# }}}

# See the example server for how to use this module.

# imports.  {{{
import network
from network import fgloop, bgloop, endloop, log
import os
import re
import sys
import urlparse
import urllib
import base64
import hashlib
import struct
import json
import traceback
# }}}

DEBUG = 0 if os.getenv ('NODEBUG') else int (os.getenv ('DEBUG', 1))

known_codes = {	# {{{
		100: 'Continue', 101: 'Switching Protocols',
		200: 'OK', 201: 'Created', 202: 'Accepted', 203: 'Non-Authorative Information', 204: 'No Content', 205: 'Reset Content', 206: 'Partial Content',
		300: 'Multiple Choices', 301: 'Moved Permanently', 302: 'Found', 303: 'See Other', 304: 'Not Modified', 305: 'Use Proxy', 307: 'Temporary Redirect',
		400: 'Bad Request', 401: 'Unauthorized', 402: 'Payment Required', 403: 'Forbidden', 404: 'Not Found',
			405: 'Method Not Allowed', 406: 'Not Acceptable', 407: 'Proxy Authentication Required', 408: 'Request Timeout', 409: 'Conflict',
			410: 'Gone', 411: 'Length Required', 412: 'Precondition Failed', 413: 'Request Entity Too Large', 414: 'Request-URI Too Long',
			415: 'Unsupoported Media Type', 416: 'Requested Range Not Satisfiable', 417: 'Expectation Failed',
		500: 'Internal Server Error', 501: 'Not Implemented', 502: 'Bad Gateway', 503: 'Service Unavailable', 504: 'Gateway Timeout'}
# }}}

class Websocket: # {{{
	def __init__ (self, port, url = '/', recv = None, method = 'GET', user = None, password = None, extra = {}, socket = None, mask = (None, True), websockets = None, data = None, *a, **ka): # {{{
		self.recv = recv
		if socket is None:
			socket = network.Socket (port, *a, **ka)
		hdrdata = ''
		if url is not None:
			elist = []
			for e in extra:
				elist.append ('%s: %s\r\n' % (e, extra[e]))
			socket.send ('''\
%s %s HTTP/1.1\r
Connection: Upgrade\r
Upgrade: websocket\r
Sec-WebSocket-Key: 0\r
%s%s\r
''' % (method, url, '' if user is None else base64.b64encode (user + ':' + password) + '\r\n', ''.join (elist)))
			while '\n' not in hdrdata:
				r = socket.recv ()
				if r == '':
					raise EOFError ('EOF while reading reply')
				hdrdata += r
			pos = hdrdata.index ('\n')
			assert int (hdrdata[:pos].split ()[1]) == 101
			hdrdata = hdrdata[pos + 1:]
			data = {}
			while True:
				while '\n' not in hdrdata:
					r = socket.recv ()
					if r == '':
						raise EOFError ('EOF while reading reply')
					hdrdata += r
				pos = hdrdata.index ('\n')
				line = hdrdata[:pos].strip ()
				hdrdata = hdrdata[pos + 1:]
				if line == '':
					break
				key, value = [x.strip () for x in line.split (':', 1)]
				data[key] = value
		self.socket = socket
		self.mask = mask
		self.websockets = websockets
		self.data = data
		self.websocket_buffer = ''
		self.websocket_fragments = ''
		self._is_closed = False
		self._pong = True	# If false, we're waiting for a pong.
		self.socket.read (self._websocket_read)
		def disconnect (data):
			if not self._is_closed:
				self._is_closed = True
				if self.websockets is not None:
					self.websockets.remove (self)
				self.closed ()
			return ''
		if self.websockets is not None:
			self.websockets.add (self)
		self.socket.disconnect_cb (disconnect)
		self.opened ()
		if hdrdata != '':
			self._websocket_read (hdrdata)
	# }}}
	def _websocket_read (self, data, sync = False):	# {{{
		# Websocket data consists of:
		# 1 byte:
		#	bit 7: 1 for last (or only) fragment; 0 for other fragments.
		#	bit 6-4: extension stuff; must be 0.
		#	bit 3-0: opcode.
		# 1 byte:
		#	bit 7: 1 if masked, 0 otherwise.
		#	bit 6-0: length or 126 or 127.
		# If 126:
		# 	2 bytes: length
		# If 127:
		#	8 bytes: length
		# If masked:
		#	4 bytes: mask
		# length bytes: (masked) payload

		#log ('received: ' + repr (data))
		if DEBUG > 2:
			log ('received %d bytes' % len (data))
		if DEBUG > 4:
			log ('data: ' + ' '.join (['%02x' % ord (x) for x in data]) + ''.join ([x if 32 <= ord (x) < 127 else '.' for x in data]))
		self.websocket_buffer += data
		if ord (self.websocket_buffer[0]) & 0x70:
			# Protocol error.
			log ('extension stuff, not supported!')
			self.socket.close ()
			return None
		if len (self.websocket_buffer) < 2:
			# Not enough data for length bytes.
			if DEBUG > 3:
				log ('no length yet')
			return None
		b = ord (self.websocket_buffer[1])
		have_mask = bool (b & 0x80)
		b &= 0x7f
		if have_mask and self.mask[0] is True or not have_mask and self.mask[0] is False:
			# Protocol error.
			log ('mask error')
			self.socket.close ()
			return None
		if b == 127:
			if len (self.websocket_buffer) < 10:
				# Not enough data for length bytes.
				if DEBUG > 3:
					log ('no 4 length yet')
				return None
			l = struct.unpack ('!Q', self.websocket_buffer[2:10])[0]
			pos = 10
		elif b == 126:
			if len (self.websocket_buffer) < 4:
				# Not enough data for length bytes.
				if DEBUG > 3:
					log ('no 2 length yet')
				return None
			l = struct.unpack ('!H', self.websocket_buffer[2:4])[0]
			pos = 4
		else:
			l = b
			pos = 2
		if len (self.websocket_buffer) < pos + (4 if have_mask else 0) + l:
			# Not enough data for packet.
			if DEBUG > 3:
				log ('no packet yet (%d < %d)' % (len (self.websocket_buffer), pos + (4 if have_mask else 0) + l))
			return None
		header = self.websocket_buffer[:pos]
		opcode = ord (header[0]) & 0xf
		if have_mask:
			mask = [ord (x) for x in self.websocket_buffer[pos:pos + 4]]
			pos += 4
			data = self.websocket_buffer[pos:pos + 4 + l]
			self.websocket_buffer = self.websocket_buffer[pos + 4 + l:]
			# The following is slow!
			# Don't do it if the mask is 0; this is always true if talking to another program using this module.
			if mask != [0, 0, 0, 0]:
				data = ''.join ([chr (ord (x) ^ mask[i & 3]) for i, x in enumerate (data)])
		else:
			data = self.websocket_buffer[pos:pos + l]
			self.websocket_buffer = self.websocket_buffer[pos + l:]
		if (ord (header[0]) & 0x80) != 0x80:
			# fragment found; not last.
			if opcode != 0:
				# Protocol error.
				log ('invalid fragment')
				self.socket.close ()
				return None
			self.websocket_fragments += data
			log ('fragment recorded')
			return None
		# Complete frame has been received.
		data = self.websocket_fragments + data
		self.websocket_fragments = ''
		if opcode == 8:
			# Connection close request.
			self.close ()
			return None
		if opcode == 9:
			# Ping.
			self.send (data, 10)	# Pong
			return None
		if opcode == 10:
			# Pong.
			self._pong = True
			return None
		if opcode == 1:
			# Text.
			data = unicode (data, 'utf-8', 'replace')
			if sync:
				return data
			if self.recv:
				self.recv (self, data)
			else:
				log ('warning: ignoring incoming websocket frame')
		if opcode == 2:
			# Binary.
			if sync:
				return data
			if self.recv:
				self.recv (self, data)
			else:
				log ('warning: ignoring incoming websocket frame (binary)')
	# }}}
	def send (self, data, opcode = 1):	# Send a WebSocket frame.  {{{
		#log ('websend:' + repr (data))
		assert opcode in (0, 1, 2, 8, 9, 10)
		if self._is_closed:
			return None
		if isinstance (data, unicode):
			data = data.encode ('utf-8')
		if self.mask[1]:
			maskchar = 0x80
			# Masks are stupid, but the standard requires them.  Don't waste time on encoding (or decoding, if also using this module).
			mask = '\0\0\0\0'
		else:
			maskchar = 0
			mask = ''
		if len (data) < 126:
			l = chr (maskchar | len (data))
		elif len (data) < 1 << 16:
			l = chr (maskchar | 126) + struct.pack ('!H', len (data))
		else:
			l = chr (maskchar | 127) + struct.pack ('!Q', len (data))
		try:
			self.socket.send (chr (0x80 | opcode) + l + mask + data)
		except:
			# Something went wrong; close the socket (in case it wasn't yet).
			if DEBUG > 0:
				traceback.print_exc ()
			log ('closing socket due to problem while sending.')
			self.socket.close ()
		if opcode == 8:
			self.socket.close ()
	# }}}
	def ping (self, data = ''): # Send a ping; return False if no pong was seen for previous ping.  {{{
		if not self._pong:
			return False
		self._pong = False
		self.send (data, opcode = 9)
		return True
	# }}}
	def close (self):	# Close a WebSocket.  (Use self.socket.close for other connections.)  {{{
		self.send ('', 8)
		self.socket.close ()
	# }}}
	def opened (self): # {{{
		pass
	# }}}
	def closed (self): # {{{
		pass
	# }}}
# }}}

# Sentinel object to signify that generator is not done.
class WAIT:
	pass

# Call a generator function from a generator function. {{{
# The caller should start with:
# resumeinfo = [(yield), None]
# To make the call, it should say:
# c = websockets.call (resumeinfo, target, args...)
# while c (): c.args = (yield websockets.WAIT)
# resumeinfo[1] will contain the returned value.
# When calling from a regular context (not in a generator), use None for
# resumeinfo and call the result, like so:
# websockets.call (None, target, args...) ()
class call:
	def __init__ (self, resumeinfo, target, *a, **ka):
		if resumeinfo is None:
			self.resumeinfo = [self, None]
		else:
			self.resumeinfo = resumeinfo
		self.target = target (*a, **ka)
		if type (self.target) is not RPC._generatortype:
			# Not a generator; just return the value.
			self.resumeinfo[1] = self.target
			self.target = None
			return
		self.target.send (None)
		self.args = self.resumeinfo[0]
	def __call__ (self, arg = None):
		if self.target is None:
			return False
		try:
			a = self.args if arg is None else arg
			self.args = None
			r = self.target.send (a)
		except StopIteration:
			r = None
		if r is WAIT:
			return True
		self.resumeinfo[1] = r
		self.target = None
		return False
	def ret (self):
		return self.resumeinfo[1]
# }}}

class RPC (Websocket): # {{{
	_generatortype = type ((lambda: (yield))())
	index = 0
	calls = {}
	@classmethod
	def get_index (cls): # {{{
		while cls.index in cls.calls:
			cls.index += 1
		if type (cls.index) is long:
			cls.index = 0
			while cls.index in cls.calls:
				cls.index += 1
		return cls.index
	# }}}
	def __init__ (self, port, recv = None, *a, **ka): # {{{
		Websocket.__init__ (self, port, recv = RPC._recv, *a, **ka)
		self._target = recv (self) if recv is not None else None
		#log ('init:' + repr (recv) + ',' + repr (self._target))
	# }}}
	class wrapper: # {{{
		def __init__ (self, base, attr): # {{{
			self.base = base
			self.attr = attr
		# }}}
		def __call__ (self, *a, **ka): # {{{
			my_id = RPC.get_index ()
			self.base._send ('call', (my_id, self.attr, a, ka))
			my_call = [None]
			RPC.calls[my_id] = lambda x: my_call.__setitem__ (0, (x,))	# Make it a tuple so it cannot be None.
			while my_call[0] is None:
				while True:
					data = self.base._websocket_read (self.base.socket.recv (), True)
					if data is not None:
						break
				self.base._recv (data)
			del RPC.calls[my_id]
			return my_call[0][0]
		# }}}
		def __getitem__ (self, *a, **ka): # {{{
			self.base._send ('call', (None, self.attr, a, ka))
		# }}}
		def bg (self, reply, *a, **ka): # {{{
			my_id = RPC.get_index ()
			self.base._send ('call', (my_id, self.attr, a, ka))
			RPC.calls[my_id] = lambda x: self.do_reply (reply, my_id, x)
		# }}}
		def do_reply (self, reply, my_id, ret): # {{{
			del RPC.calls[my_id]
			reply (ret)
		# }}}
		# alternate names. {{{
		def call (self, *a, **ka):
			self.__call__ (*a, **ka)
		def event (self, *a, **ka):
			self.__getitem__ (*a, **ka)
		# }}}
	# }}}
	def _send (self, type, object): # {{{
		#log ('sending:' + repr (type) + repr (object))
		Websocket.send (self, json.dumps ((type, object)))
	# }}}
	def _parse_frame (self, frame): # {{{
		try:
			# Don't choke on Chrome's junk at the end of packets.
			data = json.JSONDecoder ().raw_decode (frame)[0]
		except ValueError:
			log ('non-json frame: %s' % repr (frame))
			return (None, 'non-json frame')
		if type (data) is not list or len (data) != 2 or type (data[0]) is not unicode:
			log ('invalid frame %s' % repr (data))
			return (None, 'invalid frame')
		if data[0] == u'call':
			if not hasattr (self._target, data[1][1]) or not callable (getattr (self._target, data[1][1])):
				log ('invalid call frame %s' % repr (data))
				return (None, 'invalid frame')
		elif data[0] not in (u'error', u'return'):
			log ('invalid frame type %s' % repr (data))
			return (None, 'invalid frame')
		return data
	# }}}
	def _recv (self, frame): # {{{
		data = self._parse_frame (frame)
		if DEBUG > 1:
			log ('packet received: %s' % repr (data))
		if data[0] is None:
			self._send ('error', data[1])
			return
		elif data[0] == 'error':
			if DEBUG > 0:
				traceback.print_exc ()
			raise ValueError (data[1])
		elif data[0] == 'return':
			assert data[1][0] in RPC.calls
			RPC.calls[data[1][0]] (data[1][1])
			return
		try:
			if data[0] == 'call':
				self._call (data[1][0], data[1][1], data[1][2], data[1][3])
			else:
				raise ValueError ('invalid RPC command')
		except AssertionError, e:
			self._send ('error', traceback.format_exc ())
		except:
			log ('error: %s' % str (sys.exc_value))
			self._send ('error', traceback.format_exc ())
			#raise
	# }}}
	def _call (self, reply, member, a, ka): # {{{
		ret = getattr (self._target, member) (*a, **ka)
		if type (ret) is not RPC._generatortype:
			if reply is not None:
				self._send ('return', (reply, ret))
			return
		ret.send (None)
		def safesend (target, arg):
			try:
				return target.send (arg)
			except StopIteration:
				return None
		self._handle_next (reply, safesend (ret, lambda arg = None: self._handle_next (reply, safesend (ret, arg))))
	# }}}
	def _handle_next (self, reply, result): # {{{
		if result is WAIT:
			return
		if reply is not None:
			self._send ('return', (reply, result))
	# }}}
	def __getattr__ (self, attr): # {{{
		if attr.startswith ('_'):
			raise AttributeError ('invalid RPC function name')
		return RPC.wrapper (self, attr)
	# }}}
# }}}

if network.have_glib: # {{{
	class Httpd_connection:	# {{{
		# Internal functions.  {{{
		def __init__ (self, server, socket, httpdirs, websocket = Websocket): # {{{
			self.server = server
			self.socket = socket
			self.httpdirs = httpdirs
			self.websocket = websocket
			self.headers = {}
			self.address = None
			self.socket.disconnect_cb (lambda data: '')	# Ignore disconnect until it is a WebSocket.
			self.socket.readlines (self._line)
			#log ('Debug: new connection from %s\n' % repr (self.socket.remote))
		# }}}
		def _line (self, l):	# {{{
			#log ('Debug: Received line: %s\n' % l)
			if self.address is not None:
				if not l.strip ():
					self._handle_headers ()
					return
				key, value = l.split (':', 1)
				self.headers[key] = value.strip ()
				return
			else:
				try:
					self.method, url, self.standard = l.split ()
					self.address = urlparse.urlparse (url)
					self.query = urlparse.parse_qs (self.address.query)
				except:
					self.server.reply (self, 400)
					self.socket.close ()
				return
		# }}}
		def _handle_headers (self):	# {{{
			is_websocket = 'Connection' in self.headers and 'Upgrade' in self.headers and 'Upgrade' in self.headers['Connection'] and 'websocket' in self.headers['Upgrade']
			self.data = {}
			msg = self.server.auth_message (self, is_websocket) if callable (self.server.auth_message) else self.server.auth_message
			if msg:
				if 'Authorization' not in self.headers:
					self.server.reply (self, 401, headers = {'WWW-Authenticate': 'Basic realm="%s"' % msg.replace ('\n', ' ').replace ('\r', ' ').replace ('"', "'")})
					if 'Content-Length' not in self.headers or self.headers['Content-Length'].strip () != '0':
						self.socket.close ()
					return
				else:
					auth = self.headers['Authorization'].split (None, 1)
					if auth[0] != 'Basic':
						self.server.reply (self, 400)
						self.socket.close ()
						return
					pwdata = base64.b64decode (auth[1]).split (':', 1)
					if len (pwdata) != 2:
						self.server.reply (self, 400)
						self.socket.close ()
						return
					self.data['user'] = pwdata[0]
					self.data['password'] = pwdata[1]
					if not self.server.authenticate (self):
						self.server.reply (self, 401, headers = {'WWW-Authenticate': 'Basic realm="%s"' % msg.replace ('\n', ' ').replace ('\r', ' ').replace ('"', "'")})
						if 'Content-Length' not in self.headers or self.headers['Content-Length'].strip () != '0':
							self.socket.close ()
						return
			if not is_websocket:
				self.body = self.socket.unread ()
				try:
					self.server.page (self)
				except:
					if DEBUG > 0:
						traceback.print_exc ()
					log ('exception: %s\n' % repr (sys.exc_value))
					self.server.reply (self, 500)
				self.socket.close ()
				return
			# Websocket.
			if self.method != 'GET' or 'Sec-WebSocket-Key' not in self.headers:
				self.server.reply (self, 400)
				self.socket.close ()
				return
			newkey = base64.b64encode (hashlib.sha1 (self.headers['Sec-WebSocket-Key'].strip () + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest ())
			headers = {'Sec-WebSocket-Accept': newkey, 'Connection': 'Upgrade', 'Upgrade': 'websocket', 'Sec-WebSocket-Version': '13'}
			self.server.reply (self, 101, None, None, headers)
			self.websocket (None, recv = self.server.recv, url = None, socket = self.socket, mask = (None, False), websockets = self.server.websockets, data = self.data)
		# }}}
		def _reply_websocket (self, message, content_type):	# {{{
			m = ''
			e = 0
			protocol = 'wss://' if hasattr (self.socket.socket, 'ssl_version') else 'ws://'
			host = self.headers['Host']
			for match in re.finditer (self.server.websocket_re, message):
				g = match.groups ()
				if len (g) > 0 and g[0]:
					extra = ' + ' + g[0]
				else:
					extra = ''
				m += message[e:match.start ()] + '''function () {
			if (window.hasOwnProperty ('MozWebSocket'))
				return new MozWebSocket ('%s%s'%s);
			else
				return new WebSocket ('%s%s'%s);
		} ()''' % (protocol, host, extra, protocol, host, extra)
				e = match.end ()
			m += message[e:]
			self.server.reply (self, 200, m, content_type)
		# }}}
		# }}}
	# }}}
	class Httpd: # {{{
		def __init__ (self, port, recv = None, http_connection = Httpd_connection, httpdirs = None, server = None, *a, **ka): # {{{
			self.recv = recv
			self.http_connection = http_connection
			self.httpdirs = httpdirs
			self.websocket_re = r'#WEBSOCKET(?:\+(.*?))?#'
			# Initial extensions which are handled from httpdirs; others can be added by the user.
			self.exts = {
					'html': self.reply_html,
					'js': self.reply_js,
					'css': self.reply_css
			}
			self.websockets = set ()
			if server is None:
				self.server = network.Server (port, self, *a, **ka)
			else:
				self.server = server
		# }}}
		def __call__ (self, socket): # {{{
			return self.http_connection (self, socket, self.httpdirs)
		# }}}
		def handle_ext (ext, mime): # {{{
			self.exts[ext] = lambda socket, message: self.reply (socket, 200, message, mime)
		# }}}
		# Authentication. {{{
		# To use authentication, set auth_message to a static message
		# or define it as a method which returns a message.  The method
		# is called with two arguments, http_connection and is_websocket.
		# If it is or returns something non-False, authenticate will be
		# called, which should return a bool.  If it returns False, the
		# connection will be rejected without notifying the program.
		#
		# http_connection.data is a dict which contains the items 'user' and
		# 'password', set to their given values.  This dict may be
		# changed by authenticate and is passed to the websocket.
		# Apart from filling the initial contents, this module does not
		# touch it.  Note that http_connection.data is empty when
		# auth_message is called.  'user' and 'password' will be
		# overwritten before authenticate is called, but other items
		# can be added at will.
		#
		# ***********************
		# NOTE REGARDING SECURITY
		# ***********************
		# The module uses plain text authentication.  Anyone capable of
		# seeing the data can read the usernames and passwords.
		# Therefore, if you want authentication, you will also want to
		# use TLS to encrypt the connection.
		auth_message = None
		def authenticate (self, connection): # {{{
			return True
		# }}}
		# }}}
		# The following functions can be called by the overloaded page function. {{{
		def reply_html (self, connection, message):	# {{{
			connection._reply_websocket (message, 'text/html;charset=utf8')
		# }}}
		def reply_js (self, connection, message):	# {{{
			connection._reply_websocket (message, 'application/javascript;charset=utf8')
		# }}}
		def reply_css (self, connection, message):	# {{{
			self.reply (connection, 200, message, 'text/css;charset=utf8')
		# }}}
		def reply (self, connection, code, message = None, content_type = None, headers = None):	# Send HTTP status code and headers, and optionally a message.  {{{
			assert code in known_codes
			#log ('Debug: sending reply %d %s for %s\n' % (code, known_codes[code], connection.address.path))
			connection.socket.send ('HTTP/1.1 %d %s\r\n' % (code, known_codes[code]))
			if headers is None:
				headers = {}
			if message is None and code != 101:
				assert content_type is None
				content_type = 'text/html;charset=utf-8'
				message = '<!DOCTYPE html><html><head><title>%s: %s</title></head><body><h1>%s: %s</h1></body></html>' % (code, known_codes[code], code, known_codes[code])
			if content_type is not None:
				headers['Content-Type'] = content_type
				headers['Content-Length'] = len (message)
			else:
				assert code == 101
				message = ''
			connection.socket.send (''.join (['%s: %s\r\n' % (x, headers[x]) for x in headers]) + '\r\n' + message)
		# }}}
		# }}}
		# If httpdirs is not given, or special handling is desired, this can be overloaded.
		def page (self, connection):	# A non-WebSocket page was requested.  Use connection.address, connection.method, connection.query, connection.headers and connection.body (which may be incomplete) to find out more.  {{{
			if self.httpdirs is None:
				self.reply (connection, 501)
				return
			if connection.address.path == '/':
				address = 'index'
			else:
				address = '/' + connection.address.path + '/'
				while '/../' in address:
					# Don't handle this; just ignore it.
					pos = address.index ('/../')
					address = address[:pos] + address[pos + 3:]
				address = address[1:-1]
			if '.' in address:
				base, ext = address.rsplit ('.', 1)
				base = base.strip ('/')
				if ext not in self.exts:
					log ('not serving unknown extension %s' % ext)
					self.reply (connection, 404)
					return
				for d in self.httpdirs:
					filename = os.path.join (d, base + os.extsep + ext)
					if os.path.exists (filename):
						break
				else:
					log ('file %s not found in %s' % (base + os.extsep + ext, ', '.join (self.httpdirs)))
					self.reply (connection, 404)
					return
			else:
				base = address.strip ('/')
				for ext in self.exts:
					for d in self.httpdirs:
						filename = os.path.join (d, base + os.extsep + ext)
						if os.path.exists (filename):
							break
					else:
						continue
					break
				else:
					log ('no file %s (with supported extension) found in %s' % (base, ', '.join (self.httpdirs)))
					self.reply (connection, 404)
					return
			return self.exts[ext] (connection, open (filename).read ())
		# }}}
	# }}}
	class RPChttpd (Httpd): # {{{
		class RPCconnection (Httpd_connection):
			def __init__ (self, *a, **ka):
				Httpd_connection.__init__ (self, websocket = RPC, *a, **ka)
		def __init__ (self, port, target, *a, **ka): # {{{
			Httpd.__init__ (self, port, target, RPChttpd.RPCconnection, *a, **ka)
		# }}}
	# }}}
# }}}
