"""Ensure Spark's Python workers use the same interpreter as the test driver.

Without this, executors launch the default `python3` (which may lack pyspark), and tasks fail.
JAVA_HOME must still be provided by the environment; where no JVM is present the Spark tests
skip themselves.
"""

import os
import sys

os.environ.setdefault("PYSPARK_PYTHON", sys.executable)
os.environ.setdefault("PYSPARK_DRIVER_PYTHON", sys.executable)
