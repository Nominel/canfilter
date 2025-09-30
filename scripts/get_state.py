#!/usr/bin/env python3
import sys
import time
import struct
import argparse
import pprint
from panda import Panda
from canfilter import CanFilter, get_all_output_safety_mode

if __name__ == "__main__":

  p = Panda()
  p.set_safety_mode(get_all_output_safety_mode())

  while 1:
    if len(p.can_recv()) == 0:
      break

  st = CanFilter.get_state(p)
  pprint.pprint(st)
