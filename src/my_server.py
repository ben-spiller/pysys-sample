#!/usr/bin/env python3
import sys
import os
import time
import argparse
import http.server
import socketserver
import logging

__version__ = '1.0.0'

logging.basicConfig(format='%(asctime)-15s %(levelname)6s: %(message)s', stream=sys.stdout)
log = logging.getLogger()

os.chdir(os.path.dirname(__file__))

parser = argparse.ArgumentParser(description='MyServer - a trivial HTTP server used to illustrate how to test a server with PySys.')
parser.add_argument('--port', dest='port', type=int, help='The port to listen on', required=True)
parser.add_argument('--loglevel', dest='loglevel', help='The log level e.g. INFO/DEBUG', default='INFO')
args = parser.parse_args()

log.setLevel(getattr(logging, args.loglevel.upper()))

class MyHandler(http.server.SimpleHTTPRequestHandler):
	pass

httpd = socketserver.TCPServer(("", args.port), MyHandler)

log.debug('Initializing server with args: %s', sys.argv[1:])
log.info("Started MyServer v%s on port %d", __version__, args.port)
httpd.serve_forever()
