#!/usr/bin/env python

import distutils.core
distutils.core.setup (
		name = 'websockets',
		py_modules = ['websockets'],
		version = '0.1',
		description = 'WebSocket http server and client',
		author = 'Bas Wijnen',
		author_email = 'wijnen@debian.org',
		)
