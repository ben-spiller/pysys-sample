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
from pysys.writer import BaseRecordResultsWriter, BaseResultsWriter
from pysys.utils.logutils import ColorLogFormatter, stdoutPrint
from pysys.utils.pycompat import PY2
from pysys.utils.fileutils import mkdir, deletedir, toLongPathSafe, fromLongPathSafe
import zipfile
log = logging.getLogger('pysys.writer')

def stripANSIEscapeCodes(text):
	return re.sub(r'\033\[[0-9;]+m', '', text)


class ArtifactPublisher(object):
	"""Interface implemented by writers that implement publishing of file/directory artifacts. 
	
	For example, a writer for a CI provider that supports artifact uploading can subclass this interface to 
	be notified when another writer (or performance reporter) produces an artifact.
	
	To publish an artifact to all registered writers, call `pysys.baserunner.BaseRunner.publishArtifact()`. 
	
	.. versionadded:: 1.6.0
	"""

	def publishArtifact(self, path, category, **kwargs):
		"""
		Called when a file or directory artifact has been written and is ready to be published (e.g. by another writer).
		
		:param str path: Absolute path of the file or directory, using forward slashes as the path separator. 
		:param str category: A string identifying what kind of artifact this is, e.g. 
			"TestOutputArchive" and "TestOutputArchiveDir" (from `pysys.writer.TestOutputArchiveWriter`) or 
			"CSVPerformanceReport" (from `pysys.utils.perfreporter.CSVPerformanceReporter`). 
			If you create your own category, be sure to add an org/company name prefix to avoid clashes.
		"""
		pass

class TestOutcomeSummaryGenerator(BaseResultsWriter):
	"""Mix-in helper class that can be inherited by any writer to allow (configurable) generation of a textual 
	summary of the test outcomes. 

	If subclasses provide their own implementation of `setup` and `processResult` they must ensure this class's 
	methods of those names are also called. Then the summary can be obtained from `logSummary` or `getSummaryText`, 
	typically in the writer's `cleanup` method. 
	"""
	
	showOutcomeReason = True
	"""Configures whether the summary includes the reason for each failure."""
	
	showOutputDir = True
	"""Configures whether the summary includes the (relative) path to the output directory for each failure. """
	
	showOutcomeStats = True
	"""Configures whether the summary includes a count of the number of each outcomes."""
	
	showDuration = False
	"""Configures whether the summary includes the total duration of all tests."""
	
	showTestIdList = False
	"""Configures whether the summary includes a short list of the failing test ids in a form that's easy to paste onto the 
	command line to re-run the failed tests. """

	
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
		self.results[cycle][testObj.getOutcome()].append( (testObj.descriptor.id, testObj.getOutcomeReason(), testObj.output))
		self.outcomes[testObj.getOutcome()] += 1
		self.duration = self.duration + testTime

	def getSummaryText(self, **kwargs):
		"""
		Get the textual summary as a single string (with no coloring). 
		
		To customize what is included in the summary (rather than letting it be user-configurable), 
		use the keyword arguments as for `logSummary`. 
		
		:return str: The summary as a string. 
		"""
		result = []
		def log(fmt, *args, **kwargs):
			result.append(fmt%args)
		return '\n'.join(result)

	def logSummary(self, log, showDuration=None, showOutcomeStats=None, showOutcomeReason=None, showOutputDir=None, showTestIdList=None, **kwargs):
		"""
		Writes a textual summary using the specified log function, with colored output if enabled.
		
		:param Callable[format,args,kwargs=] log: The function to call for each line of the summary (e.g. log.critical). 
			The message is obtained with ``format % args``, and color information is available from the ``extra=`` 
			keyword argument.
		"""
		assert not kwargs, kwargs.keys()

		if showDuration is None: showDuration = str(self.showDuration).lower() == 'true'
		if showOutcomeStats is None: showOutcomeStats = str(self.showOutcomeStats).lower() == 'true'
		if showOutcomeReason is None: showOutcomeReason = str(self.showOutcomeReason).lower() == 'true'
		if showOutputDir is None: showOutputDir = str(self.showOutputDir).lower() == 'true'
		if showTestIdList is None: showTestIdList = str(self.showTestIdList).lower() == 'true'

		if showDuration:
			log(  "Completed test run at:  %s", time.strftime('%A %Y-%m-%d %H:%M:%S %Z', time.localtime(time.time())), extra=ColorLogFormatter.tag(LOG_DEBUG, 0))
			if self.threads > 1: 
				log("Total test duration (absolute): %s", '%.2f secs'%(time.time() - self.startTime), extra=ColorLogFormatter.tag(LOG_DEBUG, 0))
				log("Total test duration (additive): %s", '%.2f secs'%self.duration, extra=ColorLogFormatter.tag(LOG_DEBUG, 0))
			else:
				log("Total test duration:    %s", "%.2f secs"%(time.time() - self.startTime), extra=ColorLogFormatter.tag(LOG_DEBUG, 0))
			log('')		


		if showOutcomeStats:
			executed = sum(self.outcomes.values())
			failednumber = sum([self.outcomes[o] for o in FAILS])
			passed = ', '.join(['%d %s'%(self.outcomes[o], LOOKUP[o]) for o in PRECEDENT if o not in FAILS and self.outcomes[o]>0])
			failed = ', '.join(['%d %s'%(self.outcomes[o], LOOKUP[o]) for o in PRECEDENT if o in FAILS and self.outcomes[o]>0])
			if failed: log('Failure outcomes: %s (%0.1f%%)', failed, 100.0 * (failednumber) / executed, extra=ColorLogFormatter.tag(LOOKUP[FAILED].lower(), [0,1]))
			if passed: log('Success outcomes: %s', passed, extra=ColorLogFormatter.tag(LOOKUP[PASSED].lower(), [0]))
			log('')

		log("Summary of failures: ")
		fails = 0
		for cycle in self.results:
			for outcome, tests in self.results[cycle].items():
				if outcome in FAILS : fails = fails + len(tests)
		if fails == 0:
			log("	THERE WERE NO FAILURES", extra=ColorLogFormatter.tag(LOG_PASSES))
		else:
			failedids = set()
			for cycle in self.results:
				cyclestr = ''
				if len(self.results) > 1: cyclestr = '[CYCLE %d] '%(cycle+1)
				for outcome in FAILS:
					for (id, reason, outputdir) in self.results[cycle][outcome]: 
						failedids.add(id)
						log("  %s%s: %s ", cyclestr, LOOKUP[outcome], id, extra=ColorLogFormatter.tag(LOOKUP[outcome].lower()))
						if showOutputDir:
							log("      %s", os.path.normpath(os.path.relpath(outputdir))+os.sep)
						if showOutcomeReason and reason:
							log("      %s", reason, extra=ColorLogFormatter.tag(LOG_TEST_OUTCOMES))
		
			if showTestIdList and len(failedids) > 1:
				# display just the ids, in a way that's easy to copy and paste into a command line
				failedids = list(failedids)
				failedids.sort()
				if len(failedids) > 20: # this feature is only useful for small test runs
					failedids = failedids[:20]+['...']
				log('')
				log('List of failed test ids:')
				log('%s', ' '.join(failedids))

class TestOutputArchiveWriter(BaseRecordResultsWriter):
	"""Writer that creates zip archives of each failed test's output directory, 
	producing artifacts that could be uploaded to a CI system or file share to allow the failures to be analysed. 
	
	This writer is enabled when running with ``--record``. If using this writer in conjunction with a CI writer that 
	publishes the generated archives, be sure to include this writer first in the list of writers in your project 
	configuration. 

	Publishes artifacts with category name "TestOutputArchive" and the directory (unless there are no archives) 
	as "TestOutputArchiveDir" for any enabled `ArtifactPublisher` writers. 

	.. versionadded:: 1.6.0

	The following properties can be set in the project configuration for this writer:		
	"""

	destDir = '__pysys_output_archives/'
	"""
	The directory to write the archives to, as an absolute path, or relative to the testRootDir. 

	This directory will be deleted at the start of the run if it already exists. 
	
	Project ``${...}`` properties can be used in the path, and additionally the string ``@OUTDIR@`` is replaced by 
	the basename of the output directory for this test run. 
	"""
	
	maxTotalSizeMB = 1024.0
	"""
	The (approximate) limit on the total size of all archives.
	"""
	
	maxArchiveSizeMB = 200.0
	"""
	The (approximate) limit on the size each individual test archive.
	"""
	
	maxArchives = 50
	"""
	The maximum number of archives to create. 
	"""
	
	archiveAtEndOfRun = True # if at end of run can give deterministic order, also reduces I/O while tests are executing
	"""
	By default all archives are created at the end of the run once all tests have finished executing. This avoids 
	I/O contention with execution of tests, and also selection of the tests to generated archives to be done 
	in a deterministic (but pseudo-random) fashion rather than just taking the first N failures. 
	
	Alternatively you can this property to false if you wish to create archives during the test run as each failure 
	occurs. 
	"""
	
	fileExcludesRegex = u''
	"""
	A regular expression indicating test output paths that will be excluded from archiving, for example large 
	temporary files that are not useful for diagnosing problems. 
	
	For example ``".*/MyTest_001/.*/mybigfile.*[.]tmp"``.
	
	The expression is matched against the path of each output file relative to the test root dir, 
	using forward slashes as the path separator. Multiple paths can be specified using "(path1|path2)" syntax. 
	"""
	
	fileIncludesRegex = u'' # executed against the path relative to the test root dir e.g. (pattern1|pattern2)
	"""
	A regular expression indicating test output paths that will be included from archiving. This can be used to 
	archive just some particular files. Note that for use cases such as collecting graphs and code coverage files 
	generated by a test run, the collect-test-output feature is usually a better fit than using this writer. 
	
	The expression is matched against the path of each output file relative to the test root dir, 
	using forward slashes as the path separator. Multiple paths can be specified using "(path1|path2)" syntax. 
	"""
	
	def setup(self, numTests=0, cycles=1, xargs=None, threads=0, testoutdir=u'', runner=None, **kwargs):
		self.runner = runner
		if not self.destDir: raise Exception('Cannot set destDir to ""')
		self.destDir = toLongPathSafe(os.path.normpath(os.path.join(runner.project.root, self.destDir\
				.replace('@OUTDIR@', os.path.basename(runner.outsubdir)) \
				)))
		if os.path.exists(self.destDir) and all(f.endswith(('.txt', '.zip')) for f in os.listdir(self.destDir)):
			deletedir(self.destDir) # remove any existing archives (but not if this dir seems to have other stuff in it!)

		self.archiveAtEndOfRun = str(self.archiveAtEndOfRun).lower()=='true'

		self.fileExcludesRegex = re.compile(self.fileExcludesRegex) if self.fileExcludesRegex else None
		self.fileIncludesRegex = re.compile(self.fileIncludesRegex) if self.fileIncludesRegex else None

		self.maxArchiveSizeMB = float(self.maxArchiveSizeMB)
		self.maxArchives = int(self.maxArchives)
		
		self.__totalBytesRemaining = int(float(self.maxTotalSizeMB)*1024*1024)

		if self.archiveAtEndOfRun:
			self.queuedInstructions = []

		self.skippedTests = []
		self.archivesCreated = 0
		
		self.__artifactWriters = [w for w in self.runner.writers if isinstance(w, ArtifactPublisher)]
		def pub(path, category):
			path = fromLongPathSafe(path).replace('\\','/')
			for a in self.__artifactWriters:
				a.publishArtifact(path, category)

		self.runner.publishArtifact = pub

	def cleanup(self, **kwargs):
		if self.archiveAtEndOfRun:
			for _, id, outputDir in sorted(self.queuedInstructions): # sort by hash of testId so make order deterministic
				self._archiveTestOutputDir(id, outputDir)
		
		if self.skippedTests:
			# if we hit a limit, at least record the names of the tests we missed
			mkdir(self.destDir)
			with io.open(self.destDir+os.sep+'skipped_artifacts.txt', 'w', encoding='utf-8') as f:
				f.write('\n'.join(os.path.normpath(t) for t in self.skippedTests))
		
		(log.info if self.archivesCreated else log.debug)('%s created %d test output archive artifacts in: %s', 
			self.__class__.__name__, self.archivesCreated, self.destDir)

		if self.archivesCreated:
			self.runner.publishArtifact(self.destDir, 'TestOutputArchiveDir')

	def shouldArchive(self, testObj, **kwargs):
		"""
		Decides whether this test is eligible for archiving of its output. 
		
		The default implementation archives only tests that have a failure outcome, 
		but this can be customized if needed by subclasses. 
		
		:param pysys.basetest.BaseTest testObj: The test object under consideration.
		:return bool: True if this test's output can be archived. 
		"""
		return testObj.getOutcome() in FAILS

	def processResult(self, testObj, cycle=0, testTime=0, testStart=0, runLogOutput=u'', **kwargs):
		if not self.shouldArchive(testObj): return 
		
		id = ('%s.cycle%03d'%(testObj.descriptor.id, testObj.testCycle)) if testObj.testCycle else testObj.descriptor.id
		
		if self.archiveAtEndOfRun:
			self.queuedInstructions.append([hash(id), id, testObj.output])
		else:
			self._archiveTestOutputDir(id, testObj.output)
	
	def _newArchive(self, id, **kwargs):
		"""
		Creates and opens a new archive file for the specified id.
		
		:return: (str path, filehandle) The path will include an appropriate extension for this archive type. 
		  The filehandle must have the same API as Python's ZipFile class. 
		"""
		path = self.destDir+os.sep+id+'.zip'
		return path, zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED, allowZip64=True)

	def _archiveTestOutputDir(self, id, outputDir, **kwargs):
		"""
		Creates an archive for the specified test, unless doing so would violate the configured limits 
		(e.g. maxArchives). 
		
		:param str id: The testId (plus a cycle suffix if it's a multi-cycle run). 
		:param str outputDir: The path of the test output dir. 
		"""
		if self.archivesCreated == 0: mkdir(self.destDir)

		if self.archivesCreated == self.maxArchives:
			self.skippedTests.append(outputDir)
			log.debug('Skipping archiving for %s as maxArchives limit is reached', id)
			return
		if self.__totalBytesRemaining < 500:
			self.skippedTests.append(outputDir)
			log.debug('Skipping archiving for %s as maxTotalMB limit is reached', id)
			return
		self.archivesCreated += 1

		try:
			outputDir = toLongPathSafe(outputDir)
			skippedFiles = []
			
			# this is performance-critical so worth caching these
			fileExcludesRegex = self.fileExcludesRegex
			fileIncludesRegex = self.fileIncludesRegex
			isPurgableFile = self.runner.isPurgableFile
			
			bytesRemaining = min(int(self.maxArchiveSizeMB*1024*1024), self.__totalBytesRemaining)
			triedTmpZipFile = False
			
			
			zippath, myzip = self._newArchive(id)
			filesInZip = 0
			with myzip:
				rootlen = len(outputDir) + 1

				for base, dirs, files in os.walk(outputDir):
					# Just the files, don't bother with the directories for now
					
					files.sort(key=lambda fn: [fn!='run.log', fn] ) # be deterministic, and put run.log first
					
					for f in files:
						fn = os.path.join(base, f)
						if fileExcludesRegex is not None and fileExcludesRegex.search(fn.replace('\\','/')):
							skippedFiles.append(fn)
							continue
						if fileIncludesRegex is not None and not fileIncludesRegex.search(fn.replace('\\','/')):
							skippedFiles.append(fn)
							continue
						
						fileSize = os.path.getsize(fn)
						if fileSize == 0:
							# Since (if not waiting until end) this gets called before testComplete has had a chance to clean things up, skip the 
							# files that it would have deleted. Don't bother listing these in skippedFiles since user 
							# won't be expecting them anyway
							continue
						
						if bytesRemaining < 500:
							skippedFiles.append(fn)
							continue
						
						if fileSize > bytesRemaining:
							if triedTmpZipFile: # to save effort, don't keep trying once we're close - from now on only attempt small files
								skippedFiles.append(fn)
								continue
							triedTmpZipFile = True
							
							# Only way to know if it'll fit is to try compressing it
							log.debug('File size of %s might push the archive above the limit; creating a temp zip to check', fn)
							tmpname, tmpzip = self._newArchive(id+'.tmp')
							try:
								with tmpzip:
									tmpzip.write(fn, 'tmp')
									compressedSize = tmpzip.getinfo('tmp').compress_size
									if compressedSize > bytesRemaining:
										log.debug('Skipping file as compressed size of %s bytes exceeds remaining limit of %s bytes: %s', 
											compressedSize, bytesRemaining, fn)
										skippedFiles.append(fn)
										continue
							finally:
								os.remove(tmpname)
						
						memberName = fn[rootlen:].replace('\\','/')
						myzip.write(fn, memberName)
						filesInZip += 1
						bytesRemaining -= myzip.getinfo(memberName).compress_size
				
				if skippedFiles and fileIncludesRegex is None: # keep the archive clean if there's an explicit include
					myzip.writestr('__pysys_skipped_archive_files.txt', os.linesep.join([fromLongPathSafe(f) for f in skippedFiles]).encode('utf-8'))
	
			if filesInZip == 0:
				# don't leave empty zips around
				log.debug('No files added to zip so deleting: %s', zippath)
				self.archivesCreated -= 1
				os.remove(zippath)
				return
	
			self.__totalBytesRemaining -= os.path.getsize(zippath)
			self.runner.publishArtifact(zippath, 'TestOutputArchive')
	
		except Exception:
			self.skippedTests.append(outputDir)
			raise

class GitHubActionsCIWriter(BaseRecordResultsWriter, TestOutcomeSummaryGenerator, ArtifactPublisher):
	"""
	Writer for GitHub Actions. 
	
	Produces annotations summarizing failures, adds grouping/folding of detailed test output, and 
	sets step output variables for any published artifacts (e.g. performance .csv files, archived test output etc) 
	which can be used to upload the artifacts when present. Step output variables for published artifacts are named 
	'artifact_CATEGORY' (for more details on artifact categories see `pysys.writer.ArtifactPublisher.publishArtifact`).
		
	Be sure to include a unique run id (e.g. outdir) for each OS/job in the name of any uploaded artifacts so that 
	they do not overwrite each other when uploaded. 
	
	Only enabled when running under GitHub Actions (specifically, if the ``GITHUB_ACTIONS=true`` environment variable is set).
	
	"""
	
	maxAnnotations = 10
	"""
	Configures the maximum number of annotations generated by this invocation of PySys, to cope with GitHub limits. 
	
	This ensure we don't use up our entire allocation of annotations leaving no space for annotations from other 
	tools. Being aware of this limit also allows to us add a warning to the end of the last one to make clear no more 
	annotations will be shown even if there are more warnings. 
	"""

	failureSummaryAnnotations = True
	"""
	Configures whether an annotation is added with a summary of the number of failures and the outcome and reason 
	for each failure. 
	"""
	
	failureLogAnnotations = True
	"""
	Configures whether annotations are added with the (run.log) log output from the first few test failures. 
	"""
	
	
	def isEnabled(self, **kwargs):
		return os.getenv('GITHUB_ACTIONS','')=='true'

	def outputGitHubCommand(self, cmd, value=u'', params={}):
		# syntax is: ::workflow-command parameter1={data},parameter2={data}::{command value}
		stdoutPrint(u'::%s%s::%s'%(cmd, (u' '+u','.join(u'%s=%s'%(k,v) for k,v in params.items())).replace('::', '__') if params else u'', value.replace('%', '%25').replace('\n', '%0A')))

	def setup(self, numTests=0, cycles=1, xargs=None, threads=0, testoutdir=u'', runner=None, **kwargs):
		super(GitHubActionsCIWriter, self).setup(numTests=numTests, cycles=cycles, xargs=xargs, threads=threads, 
			testoutdir=testoutdir, runner=runner, **kwargs)
		
		self.remainingAnnotations = self.maxAnnotations-2 # one is used up for the non-zero exit status and one is used for the summary
		if str(self.failureLogAnnotations).lower()!='true': self.remainingAnnotations = 0
		self.failureLogAnnotations = []

		self.runner = runner
		
		self.runid = os.path.basename(testoutdir)
		
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
		
		self.artifacts = {} # map of category:[paths]

	def publishArtifact(self, path, category, **kwargs):
		self.artifacts.setdefault(category, []).append(path)

	def cleanup(self, **kwargs):
		super(GitHubActionsCIWriter, self).cleanup(**kwargs)

		# invoked after all tests but before summary is printed, 
		# a good place to close the folding detail section
		self.outputGitHubCommand(u'endgroup')
		
		# artifact publishing, mostly for use with uploading
		# currently categories with multiple artifacts can't be used directly with the artifact action, but this may change in future
		for category, paths in self.artifacts.items():
			if os.path.exists(paths[0]): # auto-skip things that don't exist
				self.outputGitHubCommand(u'set-output', u','.join(paths), params={u'name':u'artifact_'+category})
		
		if sum([self.outcomes[o] for o in FAILS]):
			self.outputGitHubCommand(u'group', u'(GitHub test failure annotations)')
			
			if str(self.failureSummaryAnnotations).lower()=='true':
				self.outputGitHubCommand(u'error', self.getSummaryText(), 
					# Slightly better than the default (".github") is to include the path to the project file
					params={u'file':self.runner.project.projectFile.replace(u'\\',u'/')})
			
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
			m = re.search(u' \\[run\\.py:(\\d+)\\]', runLogOutput or u'')
			lineno = m.group(1) if m else None
			
			msg = stripANSIEscapeCodes(runLogOutput)
			self.remainingAnnotations -= 1
			if self.remainingAnnotations == 0: msg += '\n\n(annotation limit reached; for any additional test failures, see the detailed log)'
			params = {u'file':os.path.join(testObj.descriptor.testDir, testObj.descriptor.module).replace(u'\\',u'/')}
			if lineno: params[u'line'] = str(lineno)
			self.failureLogAnnotations.append([u'warning', msg, params])
			
