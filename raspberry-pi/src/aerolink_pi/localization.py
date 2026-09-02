from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

@dataclass(frozen=True)
class Pose:
    x_m:float; y_m:float; z_m:float; quality:float; monotonic_ms:int

class LocalizationAdapter(Protocol):
    def pose(self,now_ms:int)->Pose: ...

class SimulatorLocalization:
    def __init__(self): self.current=Pose(0,0,0,1.0,0)
    def update(self,x:float,y:float,z:float,quality:float,now_ms:int)->None:
        if not 0 <= quality <= 1: raise ValueError("quality")
        self.current=Pose(x,y,z,quality,now_ms)
    def pose(self,now_ms:int)->Pose:
        if now_ms-self.current.monotonic_ms>500: raise RuntimeError("stale localization")
        return self.current
