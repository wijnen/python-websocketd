#!/usr/bin/env python3

import distutils.core
distutils.core.setup (
		name = 'websocketd',
		py_modules = ['websocketd'],
		version = '0.1',
		description = 'WebSocket http server and client',
		author = 'Bas Wijnen',
		author_email = 'wijnen@debian.org',
		)
