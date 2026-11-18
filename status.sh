#!/bin/bash
while :; do 
  workspaces=$(swaymsg -t get_workspaces | jq -r '.[] | if .focused then "[\(.name)]" else .name end' | xargs)
  layout=$(swaymsg -t get_inputs | jq -r '[.[] | select(.type=="keyboard")][0].xkb_active_layout_name' | head -c 2)
  echo "$(date +"%b %d %H:%M") | $layout | $workspaces"
  sleep 0.5
done
