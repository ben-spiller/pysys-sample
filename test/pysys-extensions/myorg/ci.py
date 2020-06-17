#!/usr/bin/env python
# PySys System Test Framework, Copyright (C) 2006-2020 M.B. Grieve

# This library is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.

# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.

# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA


"""
Contains writers for recording test results to Continuous Integration providers.

These writers only generate output in ``--record`` mode, and only if the 
environment variables associated with their CI system are set. 
"""

__all__ = ["TravisCIWriter"]

import time, logging, sys, threading, os

from pysys.constants import PrintLogs
from pysys.writer import BaseRecordResultsWriter
from pysys.utils.logutils import ColorLogFormatter, stdoutPrint
from pysys.utils.pycompat import PY2

log = logging.getLogger('pysys.writer')

class GitHubActionsCIWriter(BaseRecordResultsWriter):
	"""
	Writer for GitHub Actions. Only enabled when running under GitHub Actions (specifically, 
	if the ``GITHUB_ACTIONS=true`` environment variable is set).
	
	"""
		
	def isEnabled(self, **kwargs):
		return os.getenv('GITHUB_ACTIONS','')=='true'

	def outputGitHubCommand(cmd, value=u'', params=u'', ):
		# syntax is: ::workflow-command parameter1={data},parameter2={data}::{command value}
		stdoutPrint(u':: %s%s%s'%(cmd, u' '+params if params else u'', u'::%s'%value if value else u''))

	def setup(self, numTests=0, cycles=1, xargs=None, threads=0, testoutdir=u'', runner=None, **kwargs):
		self.runid = os.path.basename(testoutdir)
		self.numTests = numTests
		self.testsSoFar = 0
		
		if runner.printLogs is None:
			# if setting was not overridden by user, default for CI is 
			# to only print failures since otherwise the output is too long 
			# and hard to find the logs of interest
			runner.printLogs = PrintLogs.FAILURES
		
		self.outputGitHubCommand(u'startGroup', self.runid)
		
		# enable coloring automatically, since this CI provider supports it, 
		# but must explicitly disable bright colors since it doesn't yet support that
		runner.project.formatters.stdout.color = True
		ColorLogFormatter.configureANSIEscapeCodes(bright=False)

	def cleanup(self, **kwargs):
		# invoked after all tests but before summary is printed, 
		# a good place to close the folding detail section
		self.outputGitHubCommand(u'endGroup')

	def processResult(self, testObj, cycle=0, testTime=0, testStart=0, runLogOutput=u'', **kwargs):
		# nothing to do for this CI provider as it doesn't collect results, we use the 
		# standard log printing mechanism
		pass
