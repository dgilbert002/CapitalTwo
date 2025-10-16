#!/usr/bin/env python3
"""Test script to compile main.py and show exact error location"""

import py_compile
import sys

try:
    py_compile.compile('main.py', doraise=True)
    print("main.py compiled successfully!")
except py_compile.PyCompileError as e:
    print(f"Compilation error: {e}")
    sys.exit(1)

