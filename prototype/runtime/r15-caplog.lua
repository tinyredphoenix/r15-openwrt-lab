-- Drain a private daemon stream fully; cap only the retained log, not daemon files.
io.stdout:setvbuf('no')
local count, maximum, marked = 0, 32700, false
while true do
    local c = io.stdin:read(1)
    if not c then break end
    if count < maximum then
        io.stdout:write(c)
        count = count + 1
    elseif not marked then
        io.stdout:write('\n[log limit reached; further output discarded]\n')
        marked = true
    end
end
