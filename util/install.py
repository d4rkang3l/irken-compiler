# -*- Mode: Python -*-

# run this as $ python util/install.py

import os
import sys
PJ = os.path.join

# if you change this, you should consider changing the default
#   value in self/context.scm to match it.
PREFIX = "/usr/local/"
IRKENLIB = PJ (PREFIX, "lib/irken/lib")
IRKENINC = PJ (PREFIX, "lib/irken/include")
IRKENBIN = PJ (PREFIX, "bin")

def getenv_or (name, default):
    v = os.getenv (name)
    if v is not None:
        return v
    else:
        return default

def system (cmd):
    print cmd
    if os.system (cmd) != 0:
        sys.stderr.write ('system cmd failed: %r\n' % (cmd,))
        raise SystemError

def mkdir (path):
    if not os.path.isdir (path):
        system ('mkdir -p %s' % (path,))

mkdir (IRKENLIB)
mkdir (IRKENBIN)
mkdir (IRKENINC)

# copy library
for path in os.listdir ('lib'):
    if path.endswith ('.scm'):
        system ('cp -p %s %s' % (PJ ('lib', path), IRKENLIB))

# copy headers
headers = ['header1.c', 'gc1.c', 'pxll.h', 'rdtsc.h', 'preamble.ll']
for path in headers:
    system ('cp -p include/%s %s' % (path, IRKENINC))

# we need a new binary with the new CFLAGS
print 'building new binary with updated CFLAGS for install...'
cflags = getenv_or ('CFLAGS', '-std=c99 -O3 -fomit-frame-pointer -g -I%s' % (IRKENINC,))
flags = open ('self/flags.scm', 'rb').read()

# this way we pull in whatever decisions were made for bootstrap.py, updating only IRKENINC
open ('self/flags.scm', 'wb').write (
    flags.replace ('./include', IRKENINC)
    )

system ('self/compile self/compile.scm -q')

# rebuild bytecode
print 'building new bytecode image...'
system ('self/compile self/compile.scm -b -q')

# copy binary
system ('cp -p self/compile %s/irken' % (IRKENBIN,))
# copy vm
system ('cp -p vm/irkvm %s/irkvm' % (IRKENBIN,))
# copy byte compiler image
system ('cp -p self/compile.byc %s/' % (IRKENLIB,))
# make irkc script
open ('vm/irkc', 'wb').write (
    "#!/bin/sh\n%s/irkvm %s/compile.byc $@\n" % (IRKENBIN, IRKENLIB)
)
os.chmod ('vm/irkc', 0755)
system ('cp -p vm/irkc %s/' % (IRKENBIN,))

