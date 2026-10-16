#!/bin/bash
# Source OpenFOAM-14 and AdditiveFOAM, then run the given command.
. /opt/openfoam14/etc/bashrc || exit 1
. /opt/AdditiveFOAM/etc/bashrc || exit 1
exec "$@"
