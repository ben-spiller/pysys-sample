#!/bin/sh
# Unix entry point for our my_server sample application; assumes python3 is on PATH
"$(dirname $0)/src/my_server.py" "$@"