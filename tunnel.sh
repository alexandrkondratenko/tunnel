#!/bin/bash

COMMAND="tunnel.py client my.server.com 12345"

ps -e -o pid -o args |
grep "$COMMAND" |
grep -v "grep" |
while read pid rest
do
	kill $pid
done

python3 $COMMAND --forward 22 >> tunnel.log 2>&1 &
