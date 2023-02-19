#!/usr/bin/python3

import fhs
import time
import websocketd

fhs.option('port', 'port to connect to', default = '8888')
config = fhs.init(help = 'testing program for websocketd module', version = '0.1', contact = 'Bas Wijnen <wijnen@debian.org>')

class Client:
	def __init__(self, remote):
		self.remote = remote
		self.remote._websocket_closed = self._closed

	def func(self, *args, **kwargs):
		print('func called with args %s and %s' % (repr(args), repr(kwargs)))
		return 'func return'

	def ping(self, arg):
		wake = (yield)
		print('ping', arg)

		now = time.time()
		websocketd.add_timeout(now + 1, wake)
		yield

		self.remote.pong.event(arg)

		websocketd.add_timeout(now + 2, wake)
		yield

		return 'pong %s' % repr(arg)

	def _closed(self):
		print('Server disconnected from client')
		websocketd.endloop()

client = websocketd.RPC(config['port'], Client, tls = False)

websocketd.fgloop()
