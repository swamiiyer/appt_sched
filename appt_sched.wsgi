#!/usr/bin/python

import sys
import logging

logging.basicConfig(stream = sys.stderr)
sys.path.insert(0, "/var/www/appt_sched")

from appt_sched import app as application
