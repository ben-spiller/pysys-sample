import pysys
from pysys.constants import *

class PySysTest(pysys.basetest.BaseTest):
	def execute(self):
		serverPort = self.getNextAvailableTCPPort()
		server = self.startProcess(self.project.appHome+'/my_server.%s'%('bat' if IS_WINDOWS else 'sh'), 
			arguments=['--port', str(serverPort)], 
			environs=self.createEnvirons(addToExePath=os.path.dirname(sys.executable)),
			stdouterr='my_server', displayName='my_server<port %s>'%serverPort,
			background=True)
		
		# Log any lines from the server's stderr during test cleanup (after validate) in case there is a error
		self.addCleanupFunction(lambda: self.logFileContents('my_server.err'))

		self.startProcess('curl', 
			arguments=['localhost:%d'%serverPort], 
			stdouterr='curl-root')
		self.startProcess('curl', 
			arguments=['localhost:%d/data'%serverPort], 
			stdouterr='curl-data')
		self.startProcess('curl', 
			arguments=['localhost:%d/data/myfile.json'%serverPort], 
			stdouterr='curl-myfile')

		
		# check that the server hasn't terminated unexpectedly while processing the above request
		self.assertThat('server.running()', server=server)

	def validate(self):
		self.logFileContents('my_server.out')
		self.logFileContents('curl-root.out')
		self.logFileContents('curl-root.err')
		self.logFileContents('curl-data.out')
		self.logFileContents('curl-myfile.out')
		
		self.assertThat('message == expected', 
			message=pysys.utils.fileutils.loadJSON(self.output+'/curl-myfile.out')['message'], 
			expected="Hello world!", 
			url='/data/myfile.json', # extra arguments can be used to give a more informative message if there's a failure
			)
		pass
