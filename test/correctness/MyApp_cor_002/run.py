from pysys.constants import *
from pysys.basetest import BaseTest

class PySysTest(BaseTest):
	def execute(self):
		self.skipTest('because foo')

	def validate(self):
		pass
