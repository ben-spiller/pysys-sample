from pysys.constants import *
from pysys.basetest import BaseTest

class PySysTest(BaseTest):
	def execute(self):
		self.startPython([self.input+'/test.py'])

	def validate(self):
		pass
