#!/usr/bin/env python3
"""Compatibility entry into the enclosing image-to-3d core; no sibling Skill."""
from pathlib import Path
import runpy
import sys
core=Path(__file__).resolve().parents[3]/'scripts'
if not (core/'project.py').is_file():
 raise SystemExit('Missing enclosing image-to-3d core')
sys.path.insert(0,str(core))
runpy.run_path(str(core/'project.py'),run_name='__main__')
