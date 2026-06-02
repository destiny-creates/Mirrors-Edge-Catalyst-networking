#!/bin/bash
BIN=/home/parrot/Downloads/ME/MirrorsEdgeCatalyst.exe

echo "=== BLAZE/SDK VERSION STRINGS ==="
strings -n 4 "$BIN" | grep -iE '^(BlazeSDK|SDK [0-9]|heat2|fire2|Blaze [0-9]|15\.[0-9]|1\.3[0-9]\.)' | sort -u

echo ""
echo "=== GAME MODES ==="
strings -n 5 "$BIN" | grep -iE '(frostbite_multi|frostbite_co|frostbite_single|TimeRun|SocialPlay|speedrun|arson.*mode|MEC.*game|game.*type.*MEC|DeathMatch|CaptureFlag)' | grep -iv 'Blaze::GameReporting' | sort -u

echo ""
echo "=== QOS URL TEMPLATES ==="
strings -n 8 "$BIN" | grep -iE 'https?://%s|qos/|/firetype|/firewall|/qos' | sort -u

echo ""
echo "=== COMPONENT IDs ==="
strings -n 5 "$BIN" | grep -iE '(componentId|component_id|COMPONENT_ID|blazeComponent|GAMEMANAGER|REDIRECTOR|AUTHENTICATION|UTIL_COMPONENT|STATS_COMPONENT|MESSAGING_COMPONENT|ASSOCIATIONLIST|GAMEREPORTING)' | grep -v 'Blaze::' | sort -u | head -40

echo ""
echo "=== PROTOCOL PORTS ==="
strings -n 4 "$BIN" | grep -iE '(SSL.*[0-9]{4}|TCP.*[0-9]{4}|UDP.*[0-9]{4}|[0-9]{4}.*SSL|[0-9]{4}.*TCP|[0-9]{4}.*UDP|port.*42[0-9][0-9]|port.*10[0-9][0-9][0-9]|443|10041|10042|17502|17503|42100|42110|42210)' | sort -u
