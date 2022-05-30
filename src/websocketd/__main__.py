# Python module for serving WebSockets and web pages.
# vim: set fileencoding=utf-8 foldmethod=marker :

# {{{ Copyright 2013-2022 Bas Wijnen <wijnen@debian.org>
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

# This can be run from the commandline as python3 -m websocketd <link|copy>
# Without an argument, usage is shown.
# With the link argument, all js-files are linked into current directory.
# With the copy arguemnt, all js-files are copied into current directory.

import sys
import os
import shutil
import importlib.resources

if len(sys.argv) != 2 or sys.argv[1] not in ('copy', 'link'):
	print('''\
This module can be run from the command line to copy or link
all javascript files into the working directory.

Give "copy" or "link" as argument to specify whether the files should be
copied or symlinked.''', file = sys.stderr)
	sys.exit(1)

files = [x for x in importlib.resources.contents(__package__) if x.endswith(os.extsep + 'js')]
for file in files:
	print(file)
	with importlib.resources.path('websocketd', file) as p:
		if sys.argv[1] == 'link':
			os.symlink(os.path.realpath(p), file)
		else:
			shutil.copy(p, file)
