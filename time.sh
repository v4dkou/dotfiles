while true; do
  printf "\033]0;%s%s\007" \
    "$(date '+%H:%M:%S')" \
    "$(df -h --output=avail /home /tmp | awk 'NR > 1 { printf " / %s", $1 }')"
  sleep 1
done &
