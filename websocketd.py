# Python module for serving WebSockets and web pages.
# vim: set fileencoding=utf-8 foldmethod=marker :

# {{{ Copyright 2013-2014 Bas Wijnen <wijnen@debian.org>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or(at your option) any later version.
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
from network import endloop, log, set_log_output
import os
import re
import sys
import base64
import hashlib
import struct
import json
import collections
import tempfile
import time
import traceback
# }}}

#def tracer(a, b, c):
#	print('trace: %s:%d:\t%s' % (a.f_code.co_filename, a.f_code.co_firstlineno, a.f_code.co_name))
#
#sys.settrace(tracer)

# Debug levels:
# 0: No debugging.
# 1: Tracebacks on errors.
# 2: Incoming and outgoing RPC packets.
# 3: Incomplete packet information.
# 4: All incoming and outgoing data.
# 5: Non-websocket data.
DEBUG = 0 if os.getenv('NODEBUG') else int(os.getenv('DEBUG', 1))

# Some workarounds to make this file work in both python2 and python3. {{{
if sys.version >= '3':
	long = int
	makebytes = lambda x: bytes(x, 'utf8') if isinstance(x, str) else x
	makestr = lambda x: str(x, 'utf8', 'replace') if isinstance(x, bytes) else x
	from urllib.parse import urlparse, parse_qs
	isstr = lambda x: isinstance(x, str)
	byte = lambda x: bytes((x,))
	bytelist = lambda x: bytes(x)
	bord = lambda x: x
	from http.client import responses as httpcodes
else:
	makebytes = lambda x: x
	makestr = lambda x: x
	from urlparse import urlparse, parse_qs
	isstr = lambda x: isinstance(x, unicode)
	byte = chr
	bytelist = lambda x: ''.join([chr(c) for c in x])
	bord = ord
	from httplib import responses as httpcodes
# }}}

class Websocket: # {{{
	def __init__(self, port, url = '/', recv = None, method = 'GET', user = None, password = None, extra = {}, socket = None, mask = (None, True), websockets = None, data = None, real_remote = None, *a, **ka): # {{{
		self.recv = recv
		self.mask = mask
		self.websockets = websockets
		self.websocket_buffer = b''
		self.websocket_fragments = b''
		self._is_closed = False
		self._pong = True	# If false, we're waiting for a pong.
		if socket is None:
			socket = network.Socket(port, *a, **ka)
		self.socket = socket
		self.remote = [real_remote or socket.remote[0], socket.remote[1]]
		hdrdata = b''
		if url is not None:
			elist = []
			for e in extra:
				elist.append('%s: %s\r\n' % (e, extra[e]))
			socket.send(makebytes('''\
%s %s HTTP/1.1\r
Connection: Upgrade\r
Upgrade: websocket\r
Sec-WebSocket-Key: 0\r
%s%s\r
''' % (method, url, '' if user is None else makestr(base64.b64encode(makebytes(user) + b':' + makebytes(password))) + '\r\n', ''.join(elist))))
			while b'\n' not in hdrdata:
				r = socket.recv()
				if r == b'':
					raise EOFError('EOF while reading reply')
				hdrdata += r
			pos = hdrdata.index(b'\n')
			assert int(hdrdata[:pos].split()[1]) == 101
			hdrdata = hdrdata[pos + 1:]
			data = {}
			while True:
				while b'\n' not in hdrdata:
					r = socket.recv()
					if len(r) == 0:
						raise EOFError('EOF while reading reply')
					hdrdata += r
				pos = hdrdata.index(b'\n')
				line = hdrdata[:pos].strip()
				hdrdata = hdrdata[pos + 1:]
				if len(line) == 0:
					break
				key, value = [x.strip() for x in makestr(line).split(':', 1)]
				data[key] = value
		self.data = data
		self.socket.read(self._websocket_read)
		def disconnect(socket, data):
			if not self._is_closed:
				self._is_closed = True
				if self.websockets is not None:
					self.websockets.remove(self)
				self.closed()
			return b''
		if self.websockets is not None:
			self.websockets.add(self)
		self.socket.disconnect_cb(disconnect)
		self.opened()
		if len(hdrdata) > 0:
			self._websocket_read(hdrdata)
		if DEBUG > 2:
			log('opened websocket')
	# }}}
	def _websocket_read(self, data, sync = False):	# {{{
		# Websocket data consists of:
		# 1 byte:
		#	bit 7: 1 for last(or only) fragment; 0 for other fragments.
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

		#log('received: ' + repr(data))
		if DEBUG > 2:
			log('received %d bytes' % len(data))
		if DEBUG > 3:
			log('waiting: ' + ' '.join(['%02x' % bord(x) for x in self.websocket_buffer]) + ''.join([chr(bord(x)) if 32 <= bord(x) < 127 else '.' for x in self.websocket_buffer]))
			log('data: ' + ' '.join(['%02x' % bord(x) for x in data]) + ''.join([chr(bord(x)) if 32 <= bord(x) < 127 else '.' for x in data]))
		self.websocket_buffer += data
		while len(self.websocket_buffer) > 0:
			if bord(self.websocket_buffer[0]) & 0x70:
				# Protocol error.
				log('extension stuff %x, not supported!' % bord(self.websocket_buffer[0]))
				self.socket.close()
				return None
			if len(self.websocket_buffer) < 2:
				# Not enough data for length bytes.
				if DEBUG > 2:
					log('no length yet')
				return None
			b = bord(self.websocket_buffer[1])
			have_mask = bool(b & 0x80)
			b &= 0x7f
			if have_mask and self.mask[0] is True or not have_mask and self.mask[0] is False:
				# Protocol error.
				log('mask error')
				self.socket.close()
				return None
			if b == 127:
				if len(self.websocket_buffer) < 10:
					# Not enough data for length bytes.
					if DEBUG > 2:
						log('no 4 length yet')
					return None
				l = struct.unpack('!Q', self.websocket_buffer[2:10])[0]
				pos = 10
			elif b == 126:
				if len(self.websocket_buffer) < 4:
					# Not enough data for length bytes.
					if DEBUG > 2:
						log('no 2 length yet')
					return None
				l = struct.unpack('!H', self.websocket_buffer[2:4])[0]
				pos = 4
			else:
				l = b
				pos = 2
			if len(self.websocket_buffer) < pos + (4 if have_mask else 0) + l:
				# Not enough data for packet.
				if DEBUG > 2:
					log('no packet yet(%d < %d)' % (len(self.websocket_buffer), pos + (4 if have_mask else 0) + l))
				return None
			header = self.websocket_buffer[:pos]
			opcode = bord(header[0]) & 0xf
			if have_mask:
				mask = [bord(x) for x in self.websocket_buffer[pos:pos + 4]]
				pos += 4
				data = self.websocket_buffer[pos:pos + l]
				# The following is slow!
				# Don't do it if the mask is 0; this is always true if talking to another program using this module.
				if mask != [0, 0, 0, 0]:
					data = bytelist([bord(x) ^ mask[i & 3] for i, x in enumerate(data)])
			else:
				data = self.websocket_buffer[pos:pos + l]
			self.websocket_buffer = self.websocket_buffer[pos + l:]
			if(bord(header[0]) & 0x80) != 0x80:
				# fragment found; not last.
				if opcode != 0:
					# Protocol error.
					log('invalid fragment')
					self.socket.close()
					return None
				self.websocket_fragments += data
				if DEBUG > 2:
					log('fragment recorded')
				return None
			# Complete frame has been received.
			data = self.websocket_fragments + data
			self.websocket_fragments = b''
			if opcode == 8:
				# Connection close request.
				self.close()
				return None
			if opcode == 9:
				# Ping.
				self.send(data, 10)	# Pong
				return None
			if opcode == 10:
				# Pong.
				self._pong = True
				return None
			if opcode == 1:
				# Text.
				data = makestr(data)
				if sync:
					return data
				if self.recv:
					self.recv(self, data)
				else:
					log('warning: ignoring incoming websocket frame')
			if opcode == 2:
				# Binary.
				if sync:
					return data
				if self.recv:
					self.recv(self, data)
				else:
					log('warning: ignoring incoming websocket frame (binary)')
	# }}}
	def send(self, data, opcode = 1):	# Send a WebSocket frame.  {{{
		if DEBUG > 3:
			log('websend:' + repr(data))
		assert opcode in(0, 1, 2, 8, 9, 10)
		if self._is_closed:
			return None
		data = makebytes(data)
		if self.mask[1]:
			maskchar = 0x80
			# Masks are stupid, but the standard requires them.  Don't waste time on encoding (or decoding, if also using this module).
			mask = b'\0\0\0\0'
		else:
			maskchar = 0
			mask = b''
		if len(data) < 126:
			l = byte(maskchar | len(data))
		elif len(data) < 1 << 16:
			l = byte(maskchar | 126) + struct.pack('!H', len(data))
		else:
			l = byte(maskchar | 127) + struct.pack('!Q', len(data))
		try:
			self.socket.send(byte(0x80 | opcode) + l + mask + data)
		except:
			# Something went wrong; close the socket(in case it wasn't yet).
			if DEBUG > 0:
				traceback.print_exc()
			log('closing socket due to problem while sending.')
			self.socket.close()
		if opcode == 8:
			self.socket.close()
	# }}}
	def ping(self, data = b''): # Send a ping; return False if no pong was seen for previous ping.  {{{
		if not self._pong:
			return False
		self._pong = False
		self.send(data, opcode = 9)
		return True
	# }}}
	def close(self):	# Close a WebSocket.  (Use self.socket.close for other connections.)  {{{
		self.send(b'', 8)
		self.socket.close()
	# }}}
	def opened(self): # {{{
		pass
	# }}}
	def closed(self): # {{{
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
# c = websockets.call(resumeinfo, target, args...)
# while c(): c.args = (yield websockets.WAIT)
# resumeinfo[1] will contain the returned value.
# When calling from a regular context (not in a generator), use None for
# resumeinfo and call the result, like so:
# websockets.call(None, target, args...)()
class call:
	def __init__(self, resumeinfo, target, *a, **ka):
		if resumeinfo is None:
			self.resumeinfo = [self, None]
		else:
			self.resumeinfo = resumeinfo
		self.target = target(*a, **ka)
		if type(self.target) is not RPC._generatortype:
			# Not a generator; just return the value.
			self.resumeinfo[1] = self.target
			self.target = None
			return
		self.target.send(None)
		self.args = self.resumeinfo[0]
	def __call__(self, arg = None):
		if self.target is None:
			return False
		try:
			a = self.args if arg is None else arg
			self.args = None
			r = self.target.send(a)
		except StopIteration:
			r = None
		if r is WAIT:
			return True
		self.resumeinfo[1] = r
		self.target = None
		return False
	def ret(self):
		return self.resumeinfo[1]
# }}}

activation = [set(), None]

class RPC(Websocket): # {{{
	_generatortype = type((lambda: (yield))())
	index = 0
	calls = {}
	@classmethod
	def get_index(cls): # {{{
		while cls.index in cls.calls:
			cls.index += 1
		# Put a limit on the index values.
		if cls.index >= 1 << 31:
			cls.index = 0
			while cls.index in cls.calls:
				cls.index += 1
		return cls.index
	# }}}
	def __init__(self, port, recv = None, *a, **ka): # {{{
		activation[0].add(self)
		if network.have_glib and activation[1] is None:
			activation[1] = network.GLib.idle_add(activate_all)
		self._delayed_calls = []
		Websocket.__init__(self, port, recv = RPC._recv, *a, **ka)
		self._target = recv(self) if recv is not None else None
	# }}}
	def __call__(self): # {{{
		'''Activate the websocket; send initial frames.'''
		if self._delayed_calls is None:
			return
		calls = self._delayed_calls
		self._delayed_calls = None
		for call in calls:
			if not hasattr(self._target, call[1]) or not isinstance(getattr(self._target, call[1]), collections.Callable):
				self._send('error', 'invalid delayed call frame %s' % repr(call))
			else:
				self._call(call[0], call[1], call[2], call[3])
	# }}}
	class wrapper: # {{{
		def __init__(self, base, attr): # {{{
			self.base = base
			self.attr = attr
		# }}}
		def __call__(self, *a, **ka): # {{{
			my_id = RPC.get_index()
			self.base._send('call', (my_id, self.attr, a, ka))
			my_call = [None]
			RPC.calls[my_id] = lambda x: my_call.__setitem__(0, (x,))	# Make it a tuple so it cannot be None.
			while my_call[0] is None:
				data = self.base._websocket_read(self.base.socket.recv(), True)
				while data is not None:
					self.base._recv(data)
					data = self.base._websocket_read(b'')
			del RPC.calls[my_id]
			return my_call[0][0]
		# }}}
		def __getitem__(self, *a, **ka): # {{{
			self.base._send('call', (None, self.attr, a, ka))
		# }}}
		def bg(self, reply, *a, **ka): # {{{
			my_id = RPC.get_index()
			self.base._send('call', (my_id, self.attr, a, ka))
			RPC.calls[my_id] = lambda x: self.do_reply(reply, my_id, x)
		# }}}
		def do_reply(self, reply, my_id, ret): # {{{
			del RPC.calls[my_id]
			reply(ret)
		# }}}
		# alternate names. {{{
		def call(self, *a, **ka):
			self.__call__(*a, **ka)
		def event(self, *a, **ka):
			self.__getitem__(*a, **ka)
		# }}}
	# }}}
	def _send(self, type, object): # {{{
		if DEBUG > 1:
			log('sending:' + repr(type) + repr(object))
		Websocket.send(self, makebytes(json.dumps((type, object))))
	# }}}
	def _parse_frame(self, frame): # {{{
		try:
			# Don't choke on Chrome's junk at the end of packets.
			data = json.JSONDecoder().raw_decode(frame)[0]
		except ValueError:
			log('non-json frame: %s' % repr(frame))
			return(None, 'non-json frame')
		if type(data) is not list or len(data) != 2 or not isstr(data[0]):
			log('invalid frame %s' % repr(data))
			return(None, 'invalid frame')
		if data[0] == 'call':
			if self._delayed_calls is None and (not hasattr(self._target, data[1][1]) or not isinstance(getattr(self._target, data[1][1]), collections.Callable)):
				log('invalid call frame %s' % repr(data))
				return(None, 'invalid frame')
		elif data[0] not in ('error', 'return'):
			log('invalid frame type %s' % repr(data))
			return(None, 'invalid frame')
		return data
	# }}}
	def _recv(self, frame): # {{{
		data = self._parse_frame(frame)
		if DEBUG > 1:
			log('packet received: %s' % repr(data))
		if data[0] is None:
			self._send('error', data[1])
			return
		elif data[0] == 'error':
			if DEBUG > 0:
				traceback.print_stack()
			raise ValueError(data[1])
		elif data[0] == 'event':
			# Do nothing with this; the packet is already logged if DEBUG > 1.
			return
		elif data[0] == 'return':
			assert data[1][0] in RPC.calls
			RPC.calls[data[1][0]] (data[1][1])
			return
		try:
			if data[0] == 'call':
				if self._delayed_calls is not None:
					self._delayed_calls.append(data[1])
				else:
					self._call(data[1][0], data[1][1], data[1][2], data[1][3])
			else:
				raise ValueError('invalid RPC command %s' % data[0])
		except AssertionError as e:
			self._send('error', traceback.format_exc())
		except:
			traceback.print_exc()
			log('error: %s' % str(sys.exc_info()[1]))
			self._send('error', traceback.format_exc())
			#raise
	# }}}
	def _call(self, reply, member, a, ka): # {{{
		ret = getattr(self._target, member) (*a, **ka)
		if type(ret) is not RPC._generatortype:
			if reply is not None:
				self._send('return', (reply, ret))
			return
		ret.send(None)
		def safesend(target, arg):
			try:
				return target.send(arg)
			except StopIteration:
				return None
		self._handle_next(reply, safesend(ret, lambda arg = None: self._handle_next(reply, safesend(ret, arg))))
	# }}}
	def _handle_next(self, reply, result): # {{{
		if result is WAIT:
			return
		if reply is not None:
			self._send('return', (reply, result))
	# }}}
	def __getattr__(self, attr): # {{{
		if attr.startswith('_'):
			raise AttributeError('invalid RPC function name %s' % attr)
		return RPC.wrapper(self, attr)
	# }}}
# }}}

def activate_all(): # {{{
	if activation[0] is not None:
		for s in activation[0]:
			s()
	activation[0].clear()
	activation[1] = None
	return False
# }}}

if network.have_glib:
	class Httpd_connection:	# {{{
		def __init__(self, server, socket, httpdirs, websocket = Websocket, proxy = ()): # {{{
			self.server = server
			self.socket = socket
			self.httpdirs = httpdirs
			self.websocket = websocket
			self.proxy = (proxy,) if isinstance(proxy, str) else proxy
			self.headers = {}
			self.address = None
			self.socket.disconnect_cb(lambda socket, data: b'')	# Ignore disconnect until it is a WebSocket.
			self.socket.readlines(self._line)
			#log('Debug: new connection from %s\n' % repr(self.socket.remote))
		# }}}
		def _line(self, l):	# {{{
			if DEBUG > 4:
				log('Debug: Received line: %s' % l)
			if self.address is not None:
				if not l.strip():
					self._handle_headers()
					return
				key, value = makestr(l).split(':', 1)
				self.headers[key.lower()] = value.strip()
				return
			else:
				try:
					self.method, url, self.standard = makestr(l).split()
					for prefix in self.proxy:
						if url.startswith('/' + prefix + '/') or url == '/' + prefix:
							self.prefix = '/' + prefix
							break
					else:
						self.prefix = ''
					address = urlparse(url)
					path = address.path[len(self.prefix):] or '/'
					self.url = path + url[len(address.path):]
					self.address = urlparse(self.url)
					self.query = parse_qs(self.address.query)
				except:
					traceback.print_exc()
					self.server.reply(self, 400)
					self.socket.close()
				return
		# }}}
		def _handle_headers(self):	# {{{
			if DEBUG > 4:
				log('Debug: handling headers')
			is_websocket = 'connection' in self.headers and 'upgrade' in self.headers and 'upgrade' in self.headers['connection'].lower() and 'websocket' in self.headers['upgrade'].lower()
			self.data = {}
			msg = self.server.auth_message(self, is_websocket) if callable(self.server.auth_message) else self.server.auth_message
			if msg:
				if 'authorization' not in self.headers:
					self.server.reply(self, 401, headers = {'WWW-Authenticate': 'Basic realm="%s"' % msg.replace('\n', ' ').replace('\r', ' ').replace('"', "'")})
					if 'content-length' not in self.headers or self.headers['content-length'].strip() != '0':
						self.socket.close()
					return
				else:
					auth = self.headers['authorization'].split(None, 1)
					if auth[0].lower() != 'basic':
						self.server.reply(self, 400)
						self.socket.close()
						return
					pwdata = base64.b64decode(makebytes(auth[1])).split(':', 1)
					if len(pwdata) != 2:
						self.server.reply(self, 400)
						self.socket.close()
						return
					self.data['user'] = pwdata[0]
					self.data['password'] = pwdata[1]
					if not self.server.authenticate(self):
						self.server.reply(self, 401, headers = {'WWW-Authenticate': 'Basic realm="%s"' % msg.replace('\n', ' ').replace('\r', ' ').replace('"', "'")})
						if 'content-length' not in self.headers or self.headers['content-length'].strip() != '0':
							self.socket.close()
						return
			if not is_websocket:
				if DEBUG > 4:
					log('Debug: not a websocket')
				self.body = self.socket.unread()
				if self.method.upper() == 'POST':
					if 'content-type' not in self.headers or self.headers['content-type'].lower().split(';')[0].strip() != 'multipart/form-data':
						log('Invalid Content-Type for POST; must be multipart/form-data (not %s)\n' % (self.headers['content-type'] if 'content-type' in self.headers else 'undefined'))
						self.server.reply(self, 500)
						self.socket.close()
						return
					args = self._parse_args(self.headers['content-type'])[1]
					if 'boundary' not in args:
						log('Invalid Content-Type for POST: missing boundary in %s\n' % (self.headers['content-type'] if 'content-type' in self.headers else 'undefined'))
						self.server.reply(self, 500)
						self.socket.close()
						return
					self.boundary = makebytes('\r\n' + '--' + args['boundary'] + '\r\n')
					self.endboundary = makebytes('\r\n' + '--' + args['boundary'] + '--\r\n')
					self.post_state = None
					self.post = [{}, {}]
					self.socket.read(self._post)
					self._post(b'')
				else:
					try:
						if not self.server.page(self):
							self.socket.close()
					except:
						if DEBUG > 0:
							traceback.print_exc()
						log('exception: %s\n' % repr(sys.exc_info()[1]))
						self.server.reply(self, 500)
						self.socket.close()
				return
			# Websocket.
			if self.method.upper() != 'GET' or 'sec-websocket-key' not in self.headers:
				if DEBUG > 2:
					log('Debug: invalid websocket')
				self.server.reply(self, 400)
				self.socket.close()
				return
			newkey = makestr(base64.b64encode(hashlib.sha1(makebytes(self.headers['sec-websocket-key'].strip()) + b'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').digest()))
			headers = {'Sec-WebSocket-Accept': newkey, 'Connection': 'Upgrade', 'Upgrade': 'websocket', 'Sec-WebSocket-Version': '13'}
			self.server.reply(self, 101, None, None, headers)
			self.websocket(None, recv = self.server.recv, url = None, socket = self.socket, mask = (None, False), websockets = self.server.websockets, data = self.data, real_remote = self.headers.get('x-forwarded-for'))
		# }}}
		def _parse_headers(self, message): # {{{
			lines = []
			pos = 0
			while True:
				p = message.index(b'\r\n', pos)
				ln = makestr(message[pos:p])
				pos = p + 2
				if ln == '':
					break
				if ln[0] in ' \t':
					if len(lines) == 0:
						log('header starts with continuation')
					else:
						lines[-1] += ln
				else:
					lines.append(ln)
			ret = {}
			for ln in lines:
				if ':' not in ln:
					log('ignoring header line without ":": %s' % ln)
					continue
				key, value = [x.strip() for x in ln.split(':', 1)]
				if key.lower() in ret:
					log('duplicate key in header: %s' % key)
				ret[key.lower()] = value
			return ret, message[pos:]
		# }}}
		def _parse_args(self, header): # {{{
			if ';' not in header:
				return (header.strip(), {})
			pos = header.index(';') + 1
			main = header[:pos].strip()
			ret = {}
			while pos < len(header):
				if '=' not in header[pos:]:
					if header[pos:].strip() != '':
						log('header argument %s does not have a value' % header[pos:].strip())
					return main, ret
				p = header.index('=', pos)
				key = header[pos:p].strip().lower()
				pos = p + 1
				value = ''
				quoted = False
				while True:
					first = (len(header), None)
					if not quoted and ';' in header[pos:]:
						s = header.index(';', pos)
						if s < first[0]:
							first = (s, ';')
					if '"' in header[pos:]:
						q = header.index('"', pos)
						if q < first[0]:
							first = (q, '"')
					if '\\' in header[pos:]:
						b = header.index('\\', pos)
						if b < first[0]:
							first = (b, '\\')
					value += header[pos:first[0]]
					pos = first[0] + 1
					if first[1] == ';' or first[1] is None:
						break
					if first[1] == '\\':
						value += header[pos]
						pos += 1
						continue
					quoted = not quoted
				ret[key] = value
			return main, ret
		# }}}
		def _post(self, data):	# {{{
			self.body += data
			if self.post_state is None:
				# Waiting for first boundary.
				if self.boundary not in b'\r\n' + self.body:
					if self.endboundary in b'\r\n' + self.body:
						self._finish_post()
					return
				self.body = b'\r\n' + self.body
				self.body = self.body[self.body.index(self.boundary) + len(self.boundary):]
				self.post_state = 0
				# Fall through.
			a = 20
			while True:
				if self.post_state == 0:
					# Reading part headers.
					if b'\r\n\r\n' not in self.body:
						return
					headers, self.body = self._parse_headers(self.body)
					self.post_state = 1
					if 'content-type' not in headers:
						post_type = ('text/plain', {'charset': 'us-ascii'})
					else:
						post_type = self._parse_args(headers['content-type'])
					if 'content-transfer-encoding' not in headers:
						self.post_encoding = '7bit'
					else:
						self.post_encoding = self._parse_args(headers['content-transfer-encoding'])[0].lower()
					# Handle decoding of the data.
					if self.post_encoding == 'base64':
						self._post_decoder = self._base64_decoder
					elif self.post_encoding == 'quoted-printable':
						self._post_decoder = self._quopri_decoder
					else:
						self._post_decoder = lambda x, final: (x, '')
					if 'content-disposition' in headers:
						args = self._parse_args(headers['content-disposition'])[1]
						if 'name' in args:
							self.post_name = args['name']
						else:
							self.post_name = None
						if 'filename' in args:
							fd, self.post_file = tempfile.mkstemp()
							self.post_handle = os.fdopen(fd, 'wb')
							self.post[1][self.post_name] = (self.post_file, args['filename'], headers, post_type)
							if self.post_name in self.post:
								os.remove(self.post[self.post_name][2])
						else:
							self.post_handle = None
					else:
						self.post_name = None
					if self.post_handle is None:
						self.post[0][self.post_name] = [b'', headers, post_type]
					# Fall through.
				if self.post_state == 1:
					# Reading part body.
					if self.endboundary in self.body:
						p = self.body.index(self.endboundary)
					else:
						p = None
					if self.boundary in self.body and (p is None or self.body.index(self.boundary) < p):
						self.post_state = 0
						rest = self.body[self.body.index(self.boundary) + len(self.boundary):]
						self.body = self.body[:self.body.index(self.boundary)]
					elif p is not None:
						self.body = self.body[:p]
						self.post_state = None
					else:
						if len(self.body) <= len(self.boundary):
							break
						rest = self.body[-len(self.boundary):]
						self.body = self.body[:-len(rest)]
					decoded, self.body = self._post_decoder(self.body, self.post_state != 1)
					if self.post_handle is not None:
						self.post_handle.write(decoded)
						if self.post_state != 1:
							self.post_handle.close()
					else:
						self.post[0][self.post_name][0] += decoded
						if self.post_state != 1:
							if self.post[0][self.post_name][2][0] == 'text/plain':
								self.post[0][self.post_name][0] = self.post[0][self.post_name][0].decode(self.post[0][self.post_name][2][1].get('charset', 'us-ascii'))
					if self.post_state is None:
						self._finish_post()
						return
					self.body += rest
		# }}}
		def _finish_post(self):	# {{{
			if not self.server.post(self):
				self.socket.close()
			for f in self.post[1]:
				os.remove(self.post[1][f][0])
			del self.post
		# }}}
		def _base64_decoder(self, data, final):	# {{{
			ret = b''
			pos = 0
			table = b'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/='
			current = []
			while len(data) >= pos + 4 - len(current):
				c = data[pos]
				pos += 1
				if c not in table:
					if c not in '\r\n':
						log('ignoring invalid character %s in base64 string' % c)
					continue
				current.append(table.index(c))
				if len(current) == 4:
					# decode
					ret += byte(current[0] << 2 | current[1] >> 4)
					if current[2] != 65:
						ret += byte(((current[1] << 4) & 0xf0) | current[2] >> 2)
					if current[3] != 65:
						ret += byte(((current[2] << 6) & 0xc0) | current[3])
			return (ret, data[pos:])
		# }}}
		def _quopri_decoder(self, data, final):	# {{{
			ret = b''
			pos = 0
			while b'=' in data[pos:-2]:
				p = data.index(b'=', pos)
				ret += data[:p]
				if data[p + 1:p + 3] == '\r\n':
					ret += '\n'
					pos = p + 3
					continue
				if any(x not in '0123456789ABCDEFabcdef' for x in data[p + 1:p + 3]):
					log('invalid escaped sequence in quoted printable: %s' % data[p:p + 3])
					pos = p + 1
					continue
				ret += byte(int(data[p + 1:p + 3], 16))
				pos = p + 3
			if final:
				ret += data[pos:]
				pos = len(data)
			elif len(pos) >= 2:
				ret += data[pos:-2]
				pos = len(data) - 2
			return (ret, data[pos:])
		# }}}
		def _reply_websocket(self, message, content_type):	# {{{
			m = b''
			e = 0
			url = urlparse(self.headers.get('referer', self.url))
			target = self.headers.get('x-forwarded-host', self.headers.get('host')) + url.path
			if not target.endswith('/'):
				target = target + '/'
			aftertarget = ''
			if url.fragment:
				aftertarget += '#' + url.fragment
			if url.query:
				aftertarget += '?' + url.query
			for match in re.finditer(self.server.websocket_re, makestr(message)):
				g = match.groups()
				if len(g) > 0 and g[0]:
					wstarget = ''
					extra = ' + ' + g[0]
				else:
					# Make sure websocket uses a different address, to allow Apache to detect the protocol.
					wstarget = 'websocket/'
					extra = ''
				m += message[e:match.start()] + makebytes('''\
function() {\
 var p = document.location.protocol;\
 var wp = p[p.length - 2] == 's' ? 'wss:' : 'ws:';\
 var target = wp + '%s'%s;\
 if (window.hasOwnProperty('MozWebSocket'))\
 return new MozWebSocket(target);\
 else\
 return new WebSocket(target);\
 }()''' % (target + wstarget + aftertarget, extra))
				e = match.end()
			m += message[e:]
			self.server.reply(self, 200, m, content_type)
		# }}}
	# }}}
	class Httpd: # {{{
		def __init__(self, port, recv = None, http_connection = Httpd_connection, httpdirs = None, server = None, proxy = (), *a, **ka): # {{{
			self.recv = recv
			self.http_connection = http_connection
			self.httpdirs = httpdirs
			self.proxy = proxy
			self.websocket_re = r'#WEBSOCKET(?:\+(.*?))?#'
			# Initial extensions which are handled from httpdirs; others can be added by the user.
			self.exts = {
					'html': self.reply_html,
					'js': self.reply_js,
					'css': self.reply_css
			}
			self.websockets = set()
			if server is None:
				self.server = network.Server(port, self, *a, **ka)
			else:
				self.server = server
		# }}}
		def __call__(self, socket): # {{{
			return self.http_connection(self, socket, self.httpdirs, proxy = self.proxy)
		# }}}
		def handle_ext(self, ext, mime): # {{{
			self.exts[ext] = lambda socket, message: self.reply(socket, 200, message, mime)
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
		def authenticate(self, connection): # {{{
			return True
		# }}}
		# }}}
		# The following functions can be called by the overloaded page function. {{{
		def reply_html(self, connection, message):	# {{{
			connection._reply_websocket(message, 'text/html;charset=utf8')
		# }}}
		def reply_js(self, connection, message):	# {{{
			connection._reply_websocket(message, 'application/javascript;charset=utf8')
		# }}}
		def reply_css(self, connection, message):	# {{{
			self.reply(connection, 200, message, 'text/css;charset=utf8')
		# }}}
		def reply(self, connection, code, message = None, content_type = None, headers = None):	# Send HTTP status code and headers, and optionally a message.  {{{
			assert code in httpcodes
			#log('Debug: sending reply %d %s for %s\n' % (code, httpcodes[code], connection.address.path))
			connection.socket.send(makebytes('HTTP/1.1 %d %s\r\n' % (code, httpcodes[code])))
			if headers is None:
				headers = {}
			if message is None and code != 101:
				assert content_type is None
				content_type = 'text/html;charset=utf-8'
				message = makebytes('<!DOCTYPE html><html><head><title>%s: %s</title></head><body><h1>%s: %s</h1></body></html>' % (code, httpcodes[code], code, httpcodes[code]))
			if content_type is not None:
				headers['Content-Type'] = content_type
				headers['Content-Length'] = len(message)
			else:
				assert code == 101
				message = b''
			connection.socket.send(makebytes(''.join(['%s: %s\r\n' % (x, headers[x]) for x in headers]) + '\r\n') + message)
		# }}}
		# }}}
		# If httpdirs is not given, or special handling is desired, this can be overloaded.
		def page(self, connection, path = None):	# A non-WebSocket page was requested.  Use connection.address, connection.method, connection.query, connection.headers and connection.body (which should be empty) to find out more.  {{{
			if self.httpdirs is None:
				self.reply(connection, 501)
				return
			if path is None:
				path = connection.address.path
			if path == '/':
				address = 'index'
			else:
				address = '/' + path + '/'
				while '/../' in address:
					# Don't handle this; just ignore it.
					pos = address.index('/../')
					address = address[:pos] + address[pos + 3:]
				address = address[1:-1]
			if '.' in address:
				base, ext = address.rsplit('.', 1)
				base = base.strip('/')
				if ext not in self.exts:
					log('not serving unknown extension %s' % ext)
					self.reply(connection, 404)
					return
				for d in self.httpdirs:
					filename = os.path.join(d, base + os.extsep + ext)
					if os.path.exists(filename):
						break
				else:
					log('file %s not found in %s' % (base + os.extsep + ext, ', '.join(self.httpdirs)))
					self.reply(connection, 404)
					return
			else:
				base = address.strip('/')
				for ext in self.exts:
					for d in self.httpdirs:
						filename = os.path.join(d, base + os.extsep + ext)
						if os.path.exists(filename):
							break
					else:
						continue
					break
				else:
					log('no file %s(with supported extension) found in %s' % (base, ', '.join(self.httpdirs)))
					self.reply(connection, 404)
					return
			return self.exts[ext](connection, open(filename, 'rb').read())
		# }}}
		def post(self, connection):	# A non-WebSocket page was requested with POST.  Same as page() above, plus connection.post, which is a dict of name:(headers, sent_filename, local_filename).  When done, the local files are unlinked; remove the items from the dict to prevent this.  The default is to return an error (so POST cannot be used to retrieve static pages!)
			log('Warning: ignoring POST request.')
			self.reply(connection, 501)
			return False
	# }}}
	class RPChttpd(Httpd): # {{{
		class RPCconnection(Httpd_connection):
			def __init__(self, *a, **ka):
				self.groups = set()
				Httpd_connection.__init__(self, websocket = RPC, *a, **ka)
		class Broadcast:
			def __init__(self, server, group = None):
				self.server = server
				self.group = group
			def __getitem__(self, item):
				return RPChttpd.Broadcast(self.server, item)
			def __getattr__(self, key):
				if key.startswith('_'):
					raise AttributeError('invalid member name')
				def impl(*a, **ka):
					for c in self.server.websockets:
						if self.group is None or self.group in c.groups:
							getattr(c, key).event(*a, **ka)
				return impl
		def __init__(self, port, target, *a, **ka): # {{{
			self.broadcast = RPChttpd.Broadcast(self)
			if 'log' in ka:
				name = ka.pop('log')
				if name:
					global DEBUG
					if DEBUG < 2:
						DEBUG = 2
					if os.path.isdir(name):
						n = os.path.join(name, time.strftime('%F %T%z'))
						old = n
						i = 0
						while os.path.exists(n):
							i += 1
							n = '%s.%d' % (old, i)
					else:
						n = name
					try:
						f = open(n, 'a')
						if n != name:
							sys.stderr.write('Logging to %s\n' % n)
					except IOError:
						fd, n = tempfile.mkstemp(prefix = os.path.basename(n) + '-' + time.strftime('%F %T%z') + '-', text = True)
						sys.stderr.write('Opening file %s failed, using tempfile instead: %s\n' % (name, n))
						f = os.fdopen(fd, 'a')
					network.set_log_output(f)
					log('Start logging to %s, commandline = %s' % (n, repr(sys.argv)))
			Httpd.__init__(self, port, target, RPChttpd.RPCconnection, *a, **ka)
		# }}}
	# }}}
	def fgloop(*a, **ka): # {{{
		activate_all()
		return network.fgloop(*a, **ka)
	# }}}
	def bgloop(*a, **ka): # {{{
		activate_all()
		return network.bgloop(*a, **ka)
	# }}}
