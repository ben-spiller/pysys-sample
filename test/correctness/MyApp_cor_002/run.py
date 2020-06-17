from pysys.constants import *
from pysys.basetest import BaseTest
from pysys.utils.logutils import ColorLogFormatter, stdoutPrint

class PySysTest(BaseTest):
	def execute(self):
		stdoutPrint('::error file=test/correctness/MyApp_cor_002/run.py,line=9,col=6::This is a test failure in 002')
		stdoutPrint('::error::This is a 1 multi-line%0Amessage')
		stdoutPrint('::error::This is a 2 multi-line\\nmessage')
		stdoutPrint('::error::This is a 3 message with :: colons : all over the place\\oh yes!')

		stdoutPrint(r'::error file=test\correctness\MyApp_cor_002\run.py,line=5,col=6::This is another test failure')
		stdoutPrint('::error file=test/correctness/MyApp_cor_001/run.py,line=2,col=6::This is a test failure 001')
		
		#self.skipTest('because foo')

	def validate(self):
		self.assertThat('a == b', a='Hello world', b='Hello world')
		self.assertThat('a == b', a='Hello world', b='Hello!')
		
