#!/usr/bin/env python3
from pathlib import Path
import json,sys
ROOT=Path(__file__).parents[2];sys.path[:0]=[str(ROOT/"server/src"),str(ROOT/"raspberry-pi/src")]
from aerolink_server.simulation import run_fleet_simulation
for n in (1,3,15):print(json.dumps(run_fleet_simulation(n),sort_keys=True))
