from pysys.constants import *
from pysys.basetest import BaseTest
from pysys.utils.logutils import ColorLogFormatter, stdoutPrint

class PySysTest(BaseTest):
	def execute(self):
		pass # change one file

	def validate(self):
		self.assertThat('a == b', a='Hello world', b='Hello wirld')
		self.assertThat('a == b', a='Hello world', b='Hello!')
		self.abort(TIMEDOUT, 'This is simulated test failure')

		
