import sys
import os
import json
import logging

import pysys

class MyServerTestPlugin(object):
	"""
	This is a sample PySys test plugin for configuring and starting MyServer instances. 
	"""

	myPluginProperty = 'default value' # this is just an example; not used in this sample
	"""
	Example of a plugin configuration property. The value for this plugin instance can be overridden using ``<property .../>``.
	Types such as boolean/list[str]/int/float will be automatically converted from string. 
	"""

	def setup(self, testObj):
		self.owner = self.testObj = testObj
		self.log = logging.getLogger('pysys.myorg.MyTestPlugin')

		# Do this if you need to execute something on cleanup:
		testObj.addCleanupFunction(self.__myPluginCleanup)
	
	def __myPluginCleanup(self):
		# TODO; shutdown cleanly
		self.log.info('Cleaning up MyTestPlugin instance')
	
	def createConfigFile(self, port, configfile='myserverconfig.json'):
		"""
		Create a configuration file for this server using the specified port. 
		
		:param int port: The port number. 
		:param str configfile: The output file. 
		"""
		self.owner.write_text(json.dumps({'port':port}), configfile, encoding='utf-8')
		return os.path.join(self.output, configfile)

	def startServer(self, arguments=[], name="my_server", waitForServerUp=True, **kwargs):
		"""
		Start this server as a background process on a dynamically assigned free port, and wait for it to come up. 
		
		:param str name: A logical name for this server (in case a single test starts several of them). 
			Used to define the default stdouterr and displayName
		:param list[str] arguments: Arguments to pass to the server. 
		:param kwargs: Additional keyword arguments are passed through to `pysys.basetest.BaseTest.startProcess()`. 
		"""
		# As this is a server, start in the background by default, but allow user to override by specifying background=False
		kwargs.setdefault('background', True)

		# Use allocateUniqueStdOutErr to make sure if we have multiple instances in this test they don't use the same stdout/err files
		kwargs.setdefault('stdouterr', self.owner.allocateUniqueStdOutErr(name))
		
		if '--port' not in arguments:
			serverPort = self.owner.getNextAvailableTCPPort()
			arguments = arguments+['--port', str(serverPort)]
			kwargs.setdefault('displayName', f'{name}<port {serverPort}>')
		else:
			serverPort = None
		
		# Use startPython rather than startProcess here so we can get Python code coverage
		process = self.owner.startPython(
			arguments=[self.owner.project.appHome+'/src/my_server.py']+arguments,
			
			# NB: always pass through **kwargs when defining a startProcess wrapper
			**kwargs)
		if waitForServerUp and serverPort:
			self.owner.waitForSocket(serverPort, process=process)
			
		process.info = {'port': serverPort}
		return process