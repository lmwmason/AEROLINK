#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).parents[2];sys.path[:0]=[str(ROOT/"server/src"),str(ROOT/"raspberry-pi/src")]
from aerolink_server.real_sitl import main
raise SystemExit(main())
