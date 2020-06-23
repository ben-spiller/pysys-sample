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

__all__ = ["GitHubActionsCIWriter"]

import time, logging, sys, threading, os
import re

from pysys.constants import PrintLogs, PRECEDENT, FAILS, FAILS, LOOKUP
from pysys.writer import BaseRecordResultsWriter
from pysys.utils.logutils import ColorLogFormatter, stdoutPrint
from pysys.utils.pycompat import PY2

log = logging.getLogger('pysys.writer')

def stripColorEscapeSequences(text):
	return re.sub(r'\033\[[0-9;]+m', '', text)
	
class BaseResultsSummaryCIWriter(BaseRecordResultsWriter):
	"""
	Base class useful for CI writers that creates a textual (non-coloured) summary of the outcomes from the whole test run. 
	"""
	
	showOutcomeReason = True
	"""
	Configures whether the summary text includes the reason for each failure. 
	"""
	
	showTestDir = True
	"""
	Configures whether the summary text includes the (relative) path to the test directory for each failure. 
	"""
	
	showOutputDir = False
	"""
	Configures whether the summary text includes the (relative) path to the output directory for each failure. 
	"""
	
	def setup(self, cycles=0, threads=0, **kwargs):
		self.results = {}
		self.startTime = time.time()
		self.duration = 0.0
		for cycle in range(cycles):
			self.results[cycle] = {}
			for outcome in PRECEDENT: self.results[cycle][outcome] = []
		self.threads = threads
		self.outcomes = {o: 0 for o in PRECEDENT}

	def processResult(self, testObj, cycle=-1, testTime=-1, testStart=-1, **kwargs):
		self.results[cycle][testObj.getOutcome()].append( (testObj.descriptor.id, testObj.getOutcomeReason(), testObj.descriptor.testDir, testObj.output))
		self.outcomes[testObj.getOutcome()] += 1
		self.duration = self.duration + testTime
	
	def getResultSummaryLines(self):
		"""
		Generate a list of lines summarizing the test results. 
		
		:return list[str]: Lines summarizing the test results. 
		"""
		r = []
		
		# numeric summaries
		executed = sum(self.outcomes.values())
		failednumber = sum([self.outcomes[o] for o in FAILS])
		passed = ', '.join(['%d %s'%(self.outcomes[o], LOOKUP[o]) for o in PRECEDENT if o not in FAILS and self.outcomes[o]>0])
		failed = ', '.join(['%d %s'%(self.outcomes[o], LOOKUP[o]) for o in PRECEDENT if o in FAILS and self.outcomes[o]>0])
		if failed: r.append('Failure outcomes: %s (%0.1f%%)'%(failed, 100.0 * (failednumber) / executed))
		if passed: r.append('Success outcomes: %s'%(passed))
		r.append('')

		r.append("Summary of failure outcomes: ")
		fails = 0
		for cycle in self.results:
			for outcome, tests in self.results[cycle].items():
				if outcome in FAILS : fails = fails + len(tests)
		if fails == 0:
			r.append("	THERE WERE NO FAILURES")
		else:
			failedids = set()
			for cycle in self.results:
				cyclestr = ''
				if len(self.results) > 1: cyclestr = '[CYCLE %d] '%(cycle+1)
				for outcome in FAILS:
					for (id, reason, testdir, outputdir) in self.results[cycle][outcome]: 
						failedids.add(id)
						r.append("  %s%s: %s "%( cyclestr, LOOKUP[outcome], id))
						# directories are shown relative to the current directory (which may or may not be the test root dir)
						if self.showOutputDir:
							r.append("      %s"% os.path.normpath(os.path.relpath(outputdir))+os.sep)
						if self.showTestDir:
							testDir = os.path.normpath(os.path.relpath(testdir))
							if testDir != id: # no point logging the same thing twice
								r.append("      %s"% testDir+os.sep)
							
						if self.showOutcomeReason and reason:
							r.append("      %s"% reason)
		return r
		

class GitHubActionsCIWriter(BaseResultsSummaryCIWriter):
	"""
	Writer for GitHub Actions. Only enabled when running under GitHub Actions (specifically, 
	if the ``GITHUB_ACTIONS=true`` environment variable is set).
	
	"""
	
	maxAnnotations = 10
	"""
	GitHub currently has a limit on the number of annotations per step (and also per job, and per API call etc), 
	which is captured by this configuration property. 
	
	This ensure we don't use up our allocation of annotations with less important ones. Being aware of this limit 
	also allows to us add a warning to the end of the last one to make clear no more annotations will be shown even if 
	there are more warnings. 
	
	NB: There is also a 64kB limit on the total length of each annotation.
	"""
	
	failureLogAnnotations = True
	"""
	Configures whether annotations are added with the (run.log) log output from the first few test failures. 
	"""
	
	failureSummaryAnnotations = True
	"""
	Configures whether an annotation is added with a summary of the number of failures and the outcome and reason 
	for each failure. 
	"""
	
	def isEnabled(self, **kwargs):
		return os.getenv('GITHUB_ACTIONS','')=='true'

	def outputGitHubCommand(self, cmd, value=u'', params=u'', ):
		# syntax is: ::workflow-command parameter1={data},parameter2={data}::{command value}
		stdoutPrint(u'::%s%s::%s'%(cmd, u' '+params if params else u'', value.replace('%', '%25').replace('\n', '%0A')))

	def setup(self, numTests=0, cycles=1, xargs=None, threads=0, testoutdir=u'', runner=None, **kwargs):
		super(GitHubActionsCIWriter, self).setup(numTests=numTests, cycles=cycles, xargs=xargs, threads=threads, 
			testoutdir=testoutdir, runner=runner, **kwargs)
		
		self.remainingAnnotations = self.maxAnnotations-2 # one is used up for the non-zero exit status and one is used for the summary
		if str(self.failureLogAnnotations).lower()!='true': self.remainingAnnotations = 0
		self.failureLogAnnotations = []

		self.runner = runner
		
		self.runid = os.path.basename(testoutdir)
		self.numTests = numTests
		
		if runner.printLogs is None:
			# if setting was not overridden by user, default for CI is 
			# to only print failures since otherwise the output is too long 
			# and hard to find the logs of interest
			runner.printLogs = PrintLogs.FAILURES
		
		self.outputGitHubCommand(u'group', u'Logs for failed test run: %s' % self.runid)
		
		# enable coloring automatically, since this CI provider supports it
		runner.project.formatters.stdout.color = True
		# in this provider, colors render more clearly with bright=False
		ColorLogFormatter.configureANSIEscapeCodes(bright=False)

	def cleanup(self, **kwargs):
		# invoked after all tests but before summary is printed, 
		# a good place to close the folding detail section
		self.outputGitHubCommand(u'endgroup')

		super(GitHubActionsCIWriter, self).cleanup(**kwargs)
		
		if sum([self.outcomes[o] for o in FAILS]):
			self.outputGitHubCommand(u'group', u'(GitHub test failure annotations)')
			
			if str(self.failureSummaryAnnotations).lower()=='true':
				self.outputGitHubCommand(u'error', u'\n'.join(self.getResultSummaryLines()), 
					# Slightly better than the default (".github") is to include the path to the project file
					params=u'file='+self.runner.project.projectFile.replace('\\','/'))
			
			if self.failureLogAnnotations:
				# Do them all in a group at the end since otherwise the annotation output gets mixed up with the test 
				# log output making it hard to understand
				for a in self.failureLogAnnotations:
					self.outputGitHubCommand(*a)

			self.outputGitHubCommand(u'endgroup')

	def processResult(self, testObj, cycle=0, testTime=0, testStart=0, runLogOutput=u'', **kwargs):
		super(GitHubActionsCIWriter, self).processResult(testObj, cycle=cycle, testTime=testTime, 
			testStart=testStart, runLogOutput=runLogOutput, **kwargs)
		
		if self.remainingAnnotations > 0 and testObj.getOutcome() in FAILS:
			# Currently, GitHub actions doesn't show the annotation against the source code unless the specified line 
			# number is one of the lines changes or surrounding context lines, but we do the best we can
			m = re.search(r' \[run\.py:(\d+)\]', runLogOutput or u'')
			lineno = m.group(1) if m else None
			
			msg = stripColorEscapeSequences(runLogOutput)
			self.remainingAnnotations -= 1
			if self.remainingAnnotations == 0: msg += '\n\n(annotation limit reached; for any additional test failures, see the detailed log)'
			self.failureLogAnnotations.append([u'warning', msg, u'file='+os.path.join(testObj.descriptor.testDir, testObj.descriptor.module).replace('\\','/')+((u',line=%s'%lineno) if lineno else u'')])
			

