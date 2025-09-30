import binascii
import time

try:
  from panda.python.spi import PandaSpiNackResponse  # type: ignore[attr-defined]
except Exception:  # pylint: disable=broad-except
  PandaSpiNackResponse = None  # type: ignore[assignment]

DEBUG = False


def _is_timeout_exception(exc):
  return isinstance(exc, TimeoutError) or (isinstance(exc, Exception) and len(exc.args) == 1 and exc.args[0] == "timeout")

def _is_spi_nack(exc):
  return PandaSpiNackResponse is not None and isinstance(exc, PandaSpiNackResponse)


def _call_can_send(panda, addr, dat, bus, *, attempts=5, delay=0.01):
  for retry in range(attempts):
    try:
      panda.can_send(addr, dat, bus)
      return
    except Exception as exc:  # pylint: disable=broad-except
      if _is_spi_nack(exc) and retry < attempts - 1:
        time.sleep(delay)
        continue
      raise


def panda_send(panda, addr, dat, bus):
  #if addr in (673, 681, 1, 2):
  #  print(f"SEND: bus: {bus}, addr: {addr}, data: {binascii.hexlify(dat)}")
  _call_can_send(panda, addr, dat, bus)

def panda_recv(panda):
  try:
    x = panda.can_recv()
  except Exception as exc:  # pylint: disable=broad-except
    if _is_timeout_exception(exc):
      return []
    raise
  #for y in x:
    #print(f"RECV: bus: {y[3]}, addr: {y[0]}, data: {binascii.hexlify(y[2])}")
  #  if y[0] in (673, 681, 1, 2):
  #    print(f"RECV: bus: {y[3]}, addr: {y[0]}, data: {binascii.hexlify(y[2])}")
  return x

def msg(x):
  if DEBUG:
    print("S:", binascii.hexlify(x))
  if len(x) <= 7:
    ret = bytes([len(x)]) + x
  else:
    assert False
  return ret.ljust(8, b"\x00")

_CAN_SEND_MANY_FORMAT = None
kmsgs = []


def _panda_send_many(panda, addr, frames, bus):
  """Compatibility wrapper for panda.can_send_many."""
  global _CAN_SEND_MANY_FORMAT

  def _call(messages):
    for retry in range(5):
      try:
        panda.can_send_many(messages)
        return
      except Exception as exc:  # pylint: disable=broad-except
        if _is_spi_nack(exc) and retry < 4:
          time.sleep(0.01)
          continue
        raise

  if _CAN_SEND_MANY_FORMAT == "legacy":
    _call([(addr, None, frame, bus) for frame in frames])
    return
  if _CAN_SEND_MANY_FORMAT == "modern":
    _call([(addr, frame, bus) for frame in frames])
    return

  try:
    _call([(addr, None, frame, bus) for frame in frames])
  except Exception as exc:  # pylint: disable=broad-except
    message = str(exc)
    if isinstance(exc, ValueError) and ("expected 3" in message or "too many values" in message):
      _call([(addr, frame, bus) for frame in frames])
      _CAN_SEND_MANY_FORMAT = "modern"
      return
    if isinstance(exc, TypeError) and "4" in message and "3" in message:
      _call([(addr, frame, bus) for frame in frames])
      _CAN_SEND_MANY_FORMAT = "modern"
      return
    raise
  else:
    _CAN_SEND_MANY_FORMAT = "legacy"


def recv(panda, cnt, addr, nbus):
  global kmsgs
  ret = []

  while len(ret) < cnt:
    new_msgs = panda_recv(panda)
    if not new_msgs:
      time.sleep(0.01)
      continue
    kmsgs += new_msgs
    nmsgs = []
    for msg in kmsgs:
      if len(msg) == 4:
        ids, ts, dat, bus = msg
      elif len(msg) == 3:
        ids, dat, bus = msg
        ts = None
      else:
        raise ValueError(f"unexpected panda CAN message format: {msg!r}")

      if ids == addr and bus == nbus and len(ret) < cnt:
        ret.append(dat)
      else:
        # leave around
        nmsgs.append(msg)
    kmsgs = nmsgs[-256:]
  return ret

def isotp_recv_subaddr(panda, addr, bus, sendaddr, subaddr):
  msg = recv(panda, 1, addr, bus)[0]

  # TODO: handle other subaddr also communicating
  assert msg[0] == subaddr

  if msg[1] & 0xf0 == 0x10:
    # first
    tlen = ((msg[1] & 0xf) << 8) | msg[2]
    dat = msg[3:]

    # 0 block size?
    CONTINUE = bytes([subaddr]) + b"\x30" + b"\x00" * 6
    panda_send(panda, sendaddr, CONTINUE, bus)

    idx = 1
    for mm in recv(panda, (tlen - len(dat) + 5) // 6, addr, bus):
      assert mm[0] == subaddr
      assert mm[1] == (0x20 | (idx & 0xF))
      dat += mm[2:]
      idx += 1
  elif msg[1] & 0xf0 == 0x00:
    # single
    tlen = msg[1] & 0xf
    dat = msg[2:]
  else:
    print(binascii.hexlify(msg))
    assert False

  return dat[0:tlen]

# **** import below this line ****

def isotp_send(panda, x, addr, bus=0, recvaddr=None, subaddr=None, rate=None):
  if recvaddr is None:
    recvaddr = addr + 8

  if len(x) <= 7 and subaddr is None:
    #panda.can_send(addr, msg(x), bus)
    panda_send(panda, addr, msg(x), bus)
  elif len(x) <= 6 and subaddr is not None:
    #panda.can_send(addr, bytes([subaddr]) + msg(x)[0:7], bus)
    panda_send(panda, addr, bytes([subaddr]) + msg(x)[0:7], bus)
  else:
    if subaddr:
      ss = bytes([subaddr, 0x10 + (len(x) >> 8), len(x) & 0xFF]) + x[0:5]
      x = x[5:]
    else:
      ss = bytes([0x10 + (len(x) >> 8), len(x) & 0xFF]) + x[0:6]
      x = x[6:]
    idx = 1
    sends = []
    while len(x) > 0:
      if subaddr:
        sends.append(((bytes([subaddr, 0x20 + (idx & 0xF)]) + x[0:6]).ljust(8, b"\x00")))
        x = x[6:]
      else:
        sends.append(((bytes([0x20 + (idx & 0xF)]) + x[0:7]).ljust(8, b"\x00")))
        x = x[7:]
      idx += 1

    # actually send
    panda_send(panda, addr, ss, bus)
    rr = recv(panda, 1, recvaddr, bus)[0]
    if rr.find(b"\x30\x01") != -1:
      for s in sends[:-1]:
        panda_send(panda, addr, s, bus)
        rr = recv(panda, 1, recvaddr, bus)[0]
      panda_send(panda, addr, sends[-1], bus)
    else:
      if rate is None:
        _panda_send_many(panda, addr, sends, bus)
      else:
        for dat in sends:
          panda_send(panda, addr, dat, bus)
          time.sleep(rate)

def isotp_recv(panda, addr, bus=0, sendaddr=None, subaddr=None, bs=0, st=0):
  if sendaddr is None:
    sendaddr = addr - 8

  if subaddr is not None:
    dat = isotp_recv_subaddr(panda, addr, bus, sendaddr, subaddr)
  else:
    msg = recv(panda, 1, addr, bus)[0]

    if msg[0] & 0xf0 == 0x10:
      # first
      tlen = ((msg[0] & 0xf) << 8) | msg[1]
      dat = msg[2:]

      # consecutive
      idx = 1
      if bs > 0:
        bs_byte = chr(bs).encode('ascii')
        st_byte = chr(st).encode('ascii')
        CONTINUE = b"\x30" + bs_byte + st_byte + b"\x00" * 5
        while (tlen - len(dat) + 6) // 7 > 0:
          panda_send(panda, sendaddr, CONTINUE, bus)
          cnt = min((tlen - len(dat) + 6) // 7, bs)
          for mm in recv(panda, cnt, addr, bus):
            assert mm[0] == (0x20 | (idx & 0xF))
            dat += mm[1:]
            idx += 1
      else:
        CONTINUE = b"\x30" + b"\x00" * 7
        panda_send(panda, sendaddr, CONTINUE, bus)
        for mm in recv(panda, (tlen - len(dat) + 6) // 7, addr, bus):
          assert mm[0] == (0x20 | (idx & 0xF))
          dat += mm[1:]
          idx += 1

    elif msg[0] & 0xf0 == 0x00:
      # single
      tlen = msg[0] & 0xf
      dat = msg[1:]
    else:
      assert False
    dat = dat[0:tlen]

  if DEBUG:
    print("R:", binascii.hexlify(dat))

  return dat
