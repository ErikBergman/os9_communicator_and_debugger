#!/bin/zsh
# Double-click in Finder to open the local Swedish voice studio.
cd -- "${0:A:h}/../.." || exit 1
exec /usr/bin/python3 tools/freddi_fisk/voice_studio.py "$@"
