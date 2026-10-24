# Source only. ROOT/BASE/LOG point at a fresh private RAM session.
event() { printf '%s\t%s\n' "$(cut -d ' ' -f 1 /proc/uptime)" "$1" >> "$LOG/events.tsv"; }
starttime() { sed 's/^.*) //' "/proc/$1/stat" 2>/dev/null | awk '{print $20}'; }
owned() { [ "$1" -gt 1 ] && [ "$(starttime "$1")" = "$2" ] && [ "$(readlink "/proc/$1/root" 2>/dev/null)" = "$ROOT" ]; }
root_processes() {
    for rp in /proc/[0-9]*/root; do
        [ "$(readlink "$rp" 2>/dev/null)" = "$ROOT" ] || continue
        pid=${rp#/proc/}; pid=${pid%/root}
        [ "$pid" -gt 1 ] || continue
        born=$(starttime "$pid")
        [ -n "$born" ] && printf 'descendant\t%s\t%s\n' "$pid" "$born"
    done
}
start_owned() {
    service=$1; shift
    # A draining pipe caps only the log, never LuCI's cache/session file sizes.
    pipe=$BASE/pipes/$service
    mkfifo -m 600 "$pipe" || return 1
    chroot "$ROOT" /usr/bin/lua /usr/libexec/r15-caplog.lua < "$pipe" > "$LOG/$service.log" 2> "$LOG/$service.logger-stderr" &
    reader=$!; reader_birth=$(starttime "$reader")
    [ -n "$reader_birth" ] && [ "$reader" -gt 1 ] || return 1
    printf '%s\t%s\t%s\n' "$service" "$reader" "$reader_birth" >> "$LOG/loggers.tsv"
    chroot "$ROOT" "$@" < /dev/null > "$pipe" 2>&1 &
    child=$!; birth=$(starttime "$child")
    [ -n "$birth" ] && [ "$child" -gt 1 ] || return 1
    printf '%s\t%s\t%s\n' "$service" "$child" "$birth" >> "$LOG/owned.tsv"
    attempt=0
    while [ "$attempt" -lt 4 ]; do
        owned "$child" "$birth" && { event "started:$service:$child"; return 0; }
        kill -0 "$child" 2>/dev/null || return 1
        sleep 1; attempt=$((attempt + 1))
    done
    return 1
}
mount_new() {
    destination=$1; shift
    # A previous session's mount must never be adopted.
    awk -v p="$destination" '$2==p { found=1 } END { exit !found }' /proc/mounts && return 1
    mount "$@" "$destination" || return 1
    printf '%s\n' "$destination" >> "$LOG/mounts.tsv"
}
stop_records() {
    signal=$1; records=$2
    while read -r role pid born; do
        if owned "$pid" "$born"; then
            event "stop:$signal:$role:$pid"
            kill -"$signal" "$pid" 2>/dev/null
        fi
    done < "$records"
}
cleanup() {
    trap '' INT TERM HUP
    event cleanup-start
    awk '{ line[NR]=$0 } END { for(i=NR;i>0;i--) print line[i] }' "$LOG/owned.tsv" > "$LOG/cleanup.tsv"
    stop_records TERM "$LOG/cleanup.tsv"
    sleep 1
    stop_records KILL "$LOG/cleanup.tsv"
    # Drain helpers are direct children, including one blocked before chroot.
    while read -r role pid born; do
        if [ "$pid" -gt 1 ] && [ "$(starttime "$pid")" = "$born" ]; then
            # Ownership was recorded immediately after spawning this exact child.
            kill -TERM "$pid" 2>/dev/null
            sleep 1
            if [ "$(starttime "$pid")" = "$born" ]; then kill -KILL "$pid" 2>/dev/null; fi
        fi
        wait "$pid" 2>/dev/null; result=$?
        printf '%s\t%s\t%s\n' "$role" "$pid" "$result" >> "$LOG/logger-exits.tsv"
    done < "$LOG/loggers.tsv"
    # SSH/CGI workers may outlive their parent. Only this unique chroot qualifies.
    root_processes > "$LOG/descendants.tsv"
    stop_records TERM "$LOG/descendants.tsv"
    sleep 1
    stop_records KILL "$LOG/descendants.tsv"
    sleep 1
    root_processes > "$LOG/remaining.tsv"
    if [ -s "$LOG/remaining.tsv" ]; then
        event cleanup-incomplete-processes
        printf 'INCOMPLETE: processes remain; mounts retained\n' > "$LOG/cleanup-result.txt"
        return 1
    fi
    while read -r role pid born; do
        wait "$pid" 2>/dev/null; result=$?
        printf '%s\t%s\t%s\n' "$role" "$pid" "$result" >> "$LOG/exits.tsv"
    done < "$LOG/cleanup.tsv"
    awk '{ line[NR]=$0 } END { for(i=NR;i>0;i--) print line[i] }' "$LOG/mounts.tsv" > "$LOG/unmounts.tsv"
    failed=0
    while read -r destination; do
        [ -n "$destination" ] || continue
        if umount "$destination"; then event unmounted; else event unmount-failed; failed=1; fi
    done < "$LOG/unmounts.tsv"
    if [ "$failed" = 0 ]; then
        printf 'COMPLETE\n' > "$LOG/cleanup-result.txt"
        event cleanup-end
    else
        printf 'INCOMPLETE: mount cleanup failed\n' > "$LOG/cleanup-result.txt"
        return 1
    fi
}
