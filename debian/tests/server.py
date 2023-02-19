#!/usr/bin/python3

import fhs
import websocketd

fhs.option('port', 'port to listen to', default = '8888')
config = fhs.init(help = 'testing program for websocketd module', version = '0.1', contact = 'Bas Wijnen <wijnen@debian.org>')

class Server:
	def __init__(self, remote):
		self.remote = remote
		self.remote._websocket_closed = self._closed
		self.remote.ping.bg(lambda arg: self.remote._websocket_close(), 'pang')
		self.remote.func('peng', 'pyng', foo = 'pung', bar = 'prng')

	def func(self, *args, **kwargs):
		print('func called with args %s and %s' % (repr(args), repr(kwargs)))
		return 'func return'

	def pong(self, arg):
		print('pong received, arg = %s' % repr(arg))
		return 3

	def _closed(self):
		print('Server disconnected from client')
		websocketd.endloop()

client = websocketd.RPChttpd(config['port'], Server, tls = False)

websocketd.fgloop()
