#!/usr/bin/env python

import distutils.core
distutils.core.setup (
		name = 'wshttpd',
		py_modules = ['wshttpd'],
		version = '0.1',
		description = 'WebSocket http server',
		author = 'Bas Wijnen',
		author_email = 'wijnen@debian.org',
		)
