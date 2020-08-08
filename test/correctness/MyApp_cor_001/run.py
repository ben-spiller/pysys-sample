from pysys.constants import *
from pysys.basetest import BaseTest

class PySysTest(BaseTest):
	def execute(self):
		PYTHON_EXE = sys.executable
		self.startProcess(PYTHON_EXE, [self.input+'/test.py', str(self.getNextAvailableTCPPort())], stdouterr='test')
		self.startPython([self.input+'/test.py'], stdouterr='testX')

	def validate(self):
		pass
