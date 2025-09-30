#!/usr/bin/env python3
import os
import sys
import time
import argparse
from panda import Panda

repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, repo_root)
sys.path.insert(0, os.path.dirname(repo_root))

from canfilter import CanFilter, get_all_output_safety_mode

if __name__ == "__main__":
  parser = argparse.ArgumentParser(description='Flash can-filter over can')
  parser.add_argument('--recover', action='store_true')
  parser.add_argument("fn", type=str, nargs='?', help="flash file")
  args = parser.parse_args()

  p = Panda()
  p.set_safety_mode(get_all_output_safety_mode())

  while 1:
    if len(p.can_recv()) == 0:
      break

  if args.recover:
    p.can_send(0x2A0, b"\xce\xfa\xad\xde\x1e\x0b\xb0\x02", 0)
    exit(0)
  else:
    p.can_send(0x2A0, b"\xce\xfa\xad\xde\x1e\x0b\xb0\x0a", 0)

  if args.fn:
    time.sleep(1)
    print("flashing", args.fn)
    CanFilter.flash(p, args.fn)

  print("can flash done")

