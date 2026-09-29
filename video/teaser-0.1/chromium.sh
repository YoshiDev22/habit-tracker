#!/bin/sh
# cdp.py launches the browser without --no-sandbox; as root in a container Chromium refuses to start.
exec "${CHROMIUM:-/opt/pw-browsers/chromium}" --no-sandbox --hide-scrollbars "$@"
