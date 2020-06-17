from pysys.constants import *
from pysys.basetest import BaseTest
from pysys.utils.logutils import ColorLogFormatter, stdoutPrint

class PySysTest(BaseTest):
	def execute(self):
		self.log.info('::error file=test/correctness/MyApp_cor_002/run.py,line=9,col=6::This is a test failure in 002')
		self.log.info(r'::error file=test\correctness\MyApp_cor_002\run.py,line=5,col=6::This is another test failure')
		self.log.info('::error file=test/correctness/MyApp_cor_001/run.py,line=2,col=6::This is a test failure 001')
		stdoutPrint('::error file=test/correctness/MyApp_cor_002/run.py,line=9,col=6::This is a test failure in 002 using stdoutPrint')
		self.skipTest('because foo')

	def validate(self):
		pass
