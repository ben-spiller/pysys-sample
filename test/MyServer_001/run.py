import pysys
from pysys.constants import *

class PySysTest(pysys.basetest.BaseTest):
	def execute(self):
		# Tell PySys to pick a free TCP port to start the server on (this allows running many tests in parallel without clashes)
		serverPort = self.getNextAvailableTCPPort()
		
		# A common system testing task is pre-processing a file, for example to substitute in required testing parameters
		self.copy(self.input+'/myserverconfig.json', self.output, mappers=[
			lambda line: line.replace('@SERVER_PORT@', str(serverPort)),
		])
		
		# Start the server application we're testing (as a background process)
		# self.project provides access to properties in pysysproject.xml, such as appHome which is the location of 
		# the application we're testing
		server = self.startProcess(
			self.project.appHome+'/my_server.%s'%('bat' if IS_WINDOWS else 'sh'), 
			arguments=['--configfile', self.output+'/myserverconfig.json', ], 
			environs=self.createEnvirons(addToExePath=os.path.dirname(PYTHON_EXE)),
			stdouterr='my_server', displayName='my_server<port %s>'%serverPort, background=True)
		
		# To make the test easier to debug, register a function that will log any lines from the server's stderr during 
		# this test's cleanup phase (i.e. after validate), in case there were any errors in the server
		self.addCleanupFunction(lambda: self.logFileContents('my_server.err'))
		
		# Wait for the server to start by polling for a grep regular expression. The errorExpr/process arguments 
		# ensure we abort with a really informative message if the server fails to start
		self.waitForGrep('my_server.out', 'Started MyServer .*on port .*', errorExpr=[' (ERROR|FATAL) '], process=server) 
		
		# Logging a blank line every now and again can make the test output easier to read
		self.log.info('')
		
		# Run a test tool from this test's Input/ directory. In this case it's written in Python so we use the 
		# startPython() convenience method to invoke startProcess() with the Pythone executable as the first argument
		# By default PySys expects these processes should return a 0 (success) exit code, so the test will abort with 
		# an error if not
		self.startPython([self.input+'/httpget.py', f'http://localhost:{serverPort}/data/myfile.json'], stdouterr='httpget_myfile')
		self.startPython([self.input+'/httpget.py', f'http://localhost:{serverPort}/non-existent-path'], stdouterr='httpget_nonexistent', 
			expectedExitStatus='!= 0')

		# Check that the server hasn't terminated unexpectedly while processing the above requests
		self.assertThat('server.running()', server=server)


		#####
		self.startPython([self.input+'/httpget.py', f'http://localhost:{serverPort}'], stdouterr='httpget_root', background=True)
		self.startPython([self.input+'/httpget.py', f'http://localhost:{serverPort}/data'], stdouterr='httpget_data_dir', background=True)
		self.waitForBackgroundProcesses(excludes=[server])

		# Most projects will want to define test plugins to allow sharing functionality across tests. In this case 
		# we've defined "myserver" as an alias for our MyServerTestPlugin
		server = self.myserver.startServer(arguments=[])

		"""
		add:
		
		a test showing process handling options: stopProcss, backgroundprocesses, testplugin
			stopProcess(process[, abortOnError])
			
			including error handling
			
			waitForSocket(port[, host, timeout, ])



		
		a test showing various assertion styles: (same assertion in lots of ways?)
				
				# This is the typical case - "value" is assigned to the first (...) regex group, and keyword parameters 
			# (e.g. "expected=") are used to validate that the "value" is correct
			self.assertThatGrep('myserver.log', r'Successfully authenticated user "([^"]*)"', 
					"value == expected", expected='myuser')
				assertDiff with preprocessing to remove timestamps
			
			getExprFromFile(path, expr[, groups, ])

			include abort/addOutcome
		
		a test showing multiple modes, perhaps encoding??
		
			modes - XML vs JSON?
			I18N testing
		
		use of a test plugin to start our server. maybe set user data on the return value?
		
		manual tester: with web browser
		
		performance test
			with execution order hint
			disableCoverage
		robustness with memory and flexible iteration count
		
		
		Skipping based on OS - skip in all cases
		"""

	def validate(self):
		self.logFileContents('my_server.out')
		
		self.assertThat('message == expected', 
			message=pysys.utils.fileutils.loadJSON(self.output+'/httpget_myfile.out')['message'], 
			expected="Hello world!", 
			url='/data/myfile.json', # extra arguments can be used to give a more informative message if there's a failure
			)
		pass
