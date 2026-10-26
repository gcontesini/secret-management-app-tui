#!/usr/bin/env python3
"""Stand-in for rage that asks for its passphrase on /dev/tty.

Format: b"FAKE-RAGE:" + passphrase + b"\n" + reversed payload.
"""

import sys
import termios

mode = sys.argv[1]


def ask(prompt):
  with open( "/dev/tty", "r+b", buffering=0 ) as tty:
    tty.write( prompt.encode() )
    attrs = termios.tcgetattr( tty )
    quiet = attrs[:]
    quiet[3] &= ~termios.ECHO
    termios.tcsetattr( tty, termios.TCSANOW, quiet )
    answer = tty.readline().decode().strip()
    termios.tcsetattr( tty, termios.TCSANOW, attrs )

  return answer


data = sys.stdin.buffer.read()

if mode == "-e":
  first = ask( "Enter passphrase (leave empty to autogenerate): " )
  second = ask( "Confirm passphrase: " )
  if first != second:
    sys.exit( "passphrases differ" )
  sys.stdout.buffer.write( b"FAKE-RAGE:" + first.encode() + b"\n" + data[::-1] )
else:
  header, _, body = data.partition( b"\n" )
  given = ask( "Enter passphrase: " )
  if header != b"FAKE-RAGE:" + given.encode():
    sys.exit( "Error: decryption failed: incorrect passphrase" )
  sys.stdout.buffer.write( body[::-1] )
