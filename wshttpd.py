# Python module for serving WebSockets and web pages.
# vim: set fileencoding=utf-8 foldmethod=marker :

# {{{ Copyright 2013 Bas Wijnen <wijnen@debian.org>
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
import os
import re
import sys
import urlparse
import urllib
import base64
import hashlib
import struct
# }}}

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

class Wshttpd:	# {{{
	# Internal functions.  {{{
	def __init__ (self, socket):	# {{{
		self._is_closed = False
		self._pong = True	# If false, we're waiting for a pong.
		self.socket = socket
		self.headers = {}
		self.address = None
		socket.disconnect_cb (lambda data: '')	# Ignore disconnect until it is a WebSocket.
		socket.readlines (self._line)
		#sys.stderr.write ('Debug: new connection from %s\n' % repr (self.socket.remote))
	# }}}
	def _line (self, l):	# {{{
		#sys.stderr.write ('Debug: Received line: %s\n' % l)
		if self.address is not None:
			if not l.strip ():
				self._handle_headers ()
				return
			key, value = l.split (':', 1)
			self.headers[key] = value.strip ()
			return
		else:
			self.method, url, self.standard = l.split ()
			self.address = urlparse.urlparse (url)
			self.query = urlparse.parse_qs (self.address.query)
			return
	# }}}
	def _handle_headers (self):	# {{{
		is_websocket = 'Connection' in self.headers and 'Upgrade' in self.headers and 'Upgrade' in self.headers['Connection'] and 'websocket' in self.headers['Upgrade']
		msg = self.auth_message (is_websocket) if callable (self.auth_message) else self.auth_message
		if msg:
			if 'Authorization' not in self.headers:
				self.reply (401, headers = {'WWW-Authenticate': 'Basic realm="%s"' % msg.replace ('\n', ' ').replace ('\r', ' ').replace ('"', "'")})
				if 'Content-Length' not in self.headers or self.headers['Content-Length'].strip () != '0':
					self.socket.close ()
				return
			else:
				auth = self.headers['Authorization'].split (None, 1)
				if auth[0] != 'Basic':
					self.reply (400)
					self.socket.close ()
					return
				data = base64.b64decode (auth[1]).split (':', 1)
				if len (data) != 2:
					self.reply (400)
					self.socket.close ()
					return
				if not self.authenticate (data[0], data[1]):
					self.reply (401, headers = {'WWW-Authenticate': 'Basic realm="%s"' % msg.replace ('\n', ' ').replace ('\r', ' ').replace ('"', "'")})
					if 'Content-Length' not in self.headers or self.headers['Content-Length'].strip () != '0':
						self.socket.close ()
					return
		if not is_websocket:
			self.body = self.socket.unread ()
			try:
				self.page ()
			except:
				sys.stderr.write ('exception: %s\n' % repr (sys.exc_value))
				self.reply (500)
			self.socket.close ()
			return
		# Websocket.
		if self.method != 'GET' or 'Sec-WebSocket-Key' not in self.headers:
			self.reply (400)
			self.close ()
			return
		newkey = base64.b64encode (hashlib.sha1 (self.headers['Sec-WebSocket-Key'].strip () + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest ())
		headers = {'Sec-WebSocket-Accept': newkey, 'Connection': 'Upgrade', 'Upgrade': 'websocket', 'Sec-WebSocket-Version': '13'}
		self.reply (101, None, None, headers)
		self.websocket_buffer = ''
		self.websocket_fragments = ''
		def disconnect (data):
			if not self._is_closed:
				self._is_closed = True
				self.closed ()
			return ''
		self.socket.disconnect_cb (disconnect)
		self.socket.read (self._websocket_read)
		self.opened ()
	# }}}
	def _websocket_read (self, data):	# {{{
		self.websocket_buffer += data
		if ord (self.websocket_buffer[0]) & 0x70:
			# Protocol error.
			print 'extension stuff, not supported!'
			self.socket.close ()
			return
		if len (self.websocket_buffer) < 2:
			# Not enough data for length bytes.
			#print 'no length yet'
			return
		b = ord (self.websocket_buffer[1]) ^ 0x80
		if b & 0x80:
			# Protocol error.
			print 'no mask'
			self.socket.close ()
			return
		if b == 126 and len (self.websocket_buffer) < 4:
			# Not enough data for length bytes.
			#print 'no 2 length yet'
			return
		if b == 127 and len (self.websocket_buffer) < 10:
			# Not enough data for length bytes.
			#print 'no 4 length yet'
			return
		if b == 127:
			l = struct.unpack ('!Q', self.websocket_buffer[2:10])[0]
			pos = 10
		elif b == 126:
			l = struct.unpack ('!H', self.websocket_buffer[2:4])[0]
			pos = 4
		else:
			l = b
			pos = 2
		if len (self.websocket_buffer) < pos + 4 + l:
			# Not enough data for packet.
			#print 'no packet yet'
			return
		opcode = ord (self.websocket_buffer[0]) & 0xf
		mask = [ord (x) for x in self.websocket_buffer[pos:pos + 4]]
		data = self.websocket_buffer[pos + 4:]
		# The following is slow!
		data = ''.join ([chr (ord (x) ^ mask[i & 3]) for i, x in enumerate (data)])
		if (ord (self.websocket_buffer[0]) & 0x80) != 0x80:
			# fragment found; not last.
			if opcode != 0:
				# Protocol error.
				print 'invalid fragment'
				self.socket.close ()
				return
			self.websocket_fragments += data
			#print 'fragment recorded'
			return
		# Complete frame has been received.
		self.websocket_buffer = ''
		data = self.websocket_fragments + data
		self.websocket_fragments = ''
		if opcode == 8:
			# Connection close request.
			self.send ('', 8)
			return
		if opcode == 9:
			# Ping.
			if not self._is_closed:
				self.send (data, 10)	# Pong
			return
		if opcode == 10:
			# Pong.
			self._pong = True
			return
		if opcode == 1:
			# Text.
			self.recv (unicode (data, 'utf-8'))
			return
		if opcode == 2:
			# Binary.
			self.recv (data)
			return
	# }}}
	def _reply_websocket (self, message, websocket, content_type):	# {{{
		m = ''
		e = 0
		protocol = 'wss://' if hasattr (self.socket.socket, 'ssl_version') else 'ws://'
		host = self.headers['Host']
		for match in re.finditer (websocket, message):
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
		self.reply (200, m, content_type)
	# }}}
	# }}}
	# The following functions can be called by the program.
	def reply_html (self, message, websocket = r'#WEBSOCKET(?:\+(.*?))?#'):	# {{{
		self._reply_websocket (message, websocket, 'text/html;charset=utf8')
	# }}}
	def reply_js (self, message, websocket = r'#WEBSOCKET(?:\+(.*?))#'):	# {{{
		self._reply_websocket (message, websocket, 'application/javascript;charset=utf8')
	# }}}
	def reply_css (self, message):	# {{{
		self.reply (200, message, 'text/css;charset=utf8')
	# }}}
	def reply (self, code, message = None, content_type = None, headers = None):	# Send HTTP status code and headers, and optionally a message.  {{{
		assert code in known_codes
		#sys.stderr.write ('Debug: sending reply %d %s for %s\n' % (code, known_codes[code], self.address.path))
		if self._is_closed:
			return
		self.socket.send ('HTTP/1.1 %d %s\r\n' % (code, known_codes[code]))
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
		self.socket.send (''.join (['%s: %s\r\n' % (x, headers[x]) for x in headers]) + '\r\n' + message)
	# }}}
	def send (self, data, opcode = 1):	# Send a WebSocket frame.  {{{
		assert opcode in (0, 1, 2, 8, 9, 10)
		if self._is_closed:
			return
		if isinstance (data, unicode):
			data = data.encode ('utf-8')
		if len (data) < 126:
			l = chr (len (data))
		elif len (data) < 1 << 16:
			l = chr (126) + struct.pack ('!H', len (data))
		else:
			l = chr (127) + struct.pack ('!Q', len (data))
		try:
			self.socket.send (chr (0x80 | opcode) + l + data)
		except:
			# Something went wrong; close the socket (in case it wasn't yet).
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
	# The following functions should be overridden by the program if they should do something useful.
	def opened (self):	# A new WebSocket was opened.  {{{
		pass
	# }}}
	def closed (self):	# A WebSocket was closed.  {{{
		pass
	# }}}
	def recv (self, data):	# A WebSocket frame was received.  {{{
		pass
	# }}}
	def page (self):	# A non-WebSocket page was requested.  Use self.address, self.method, self.query, self.headers and self.body (which may be incomplete) to find out more.  {{{
		self.reply (404)
	# }}}
	# Set this to a string to require authentication; you will want to use TLS if you do.  If it is a callable, the return value will be used.
	# The function is called with one argument, bool is_websocket.
	auth_message = None
	def authenticate (self, user, password): # If authentication is required, this is called to authenticate the user.  {{{
		return True
	# }}}
# }}}
