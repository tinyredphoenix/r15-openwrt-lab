-- Pure radio config generation for the future LuCI/UCI apply adapter.
-- Returns private strings only: no files, shell commands, services or networking.
local nixio = require 'nixio'
local M = {}

local function ssid(value)
    assert(type(value) == 'string' and #value >= 1 and #value <= 32, 'SSID must contain 1-32 bytes')
    return value
end
local function hex(value)
    return (value:gsub('.', function(c) return string.format('%02x', c:byte()) end))
end
function M.control_ssid(value)
    local escape = {[34]='\\"', [92]='\\\\', [27]='\\e', [10]='\\n', [13]='\\r', [9]='\\t'}
    return (ssid(value):gsub('.', function(c)
        local byte=c:byte()
        return escape[byte] or (byte >= 32 and byte <= 126 and c or string.format('\\x%02x',byte))
    end))
end
local function hmac(key, value)
    assert(nixio.crypto and nixio.crypto.hmac, 'nixio OpenSSL crypto support required')
    local digest=nixio.crypto.hmac('sha1',key)
    digest:update(value)
    local _,raw=digest:final()
    return raw
end
function M.psk(name, key)
    ssid(name)
    assert(type(key)=='string', 'WPA2 key must be a string')
    if #key==64 and not key:find('[^%x]') then return key:lower() end
    assert(#key>=8 and #key<=63 and not key:find('[^ -~]'), 'Use printable ASCII passphrase or 64 hex PSK')
    local result={}
    for block=1,2 do
        local value=hmac(key,name..string.char(0,0,0,block))
        local combined={value:byte(1,20)}
        for iteration=2,4096 do
            value=hmac(key,value)
            for i=1,20 do combined[i]=nixio.bit.bxor(combined[i],value:byte(i)) end
        end
        result[#result+1]=string.char(unpack(combined))
    end
    return hex(table.concat(result):sub(1,32))
end
local function bssid(value)
    if value==nil or value=='' then return nil end
    assert(type(value)=='string' and value:match('^%x%x:%x%x:%x%x:%x%x:%x%x:%x%x$'), 'Invalid BSSID')
    value=value:lower()
    assert(value~='00:00:00:00:00:00' and tonumber(value:sub(1,2),16)%2==0, 'BSSID must be nonzero unicast')
    return value
end
function M.render(config)
    assert(type(config)=='table', 'Configuration table required')
    assert(config.band=='2g' or config.band=='5g', 'Unsupported radio band')
    local ap=config.band=='2g' and 'wlan1' or 'wlan0'
    local sta=ap..'-vxd'
    local upstream=ssid(config.upstream_ssid)
    local downstream=ssid(config.ap_ssid)
    local pin=bssid(config.bssid)
    local supplicant='ctrl_interface=/var/run/r15-wpa\ncountry=IN\nap_scan=1\nnetwork={\n'
    if pin then supplicant=supplicant..'\tbssid='..pin..'\n' end
    supplicant=supplicant..'\tssid='..hex(upstream)..'\n\tscan_ssid=1\n\tproto=RSN\n'..
        '\tkey_mgmt=WPA-PSK\n\tpairwise=CCMP\n\tgroup=CCMP\n\tpsk='..
        M.psk(upstream,config.upstream_key)..'\n}\n'
    local hostapd='driver=nl80211\ninterface='..ap..'\nbridge=br-lan\n'..
        'ctrl_interface=/var/run/r15-hostapd\nssid2='..hex(downstream)..'\n'..
        'country_code=IN\nieee80211d=1\nhw_mode='..(config.band=='2g' and 'g' or 'a')..
        '\nchannel='..(config.band=='2g' and '1' or '36')..'\nieee80211n=1\nwmm_enabled=1\n'..
        'auth_algs=1\nwpa=2\nwpa_key_mgmt=WPA-PSK\nrsn_pairwise=CCMP\nwpa_psk='..
        M.psk(downstream,config.ap_key)..'\n'
    return {ap=ap,sta=sta,bssid=pin or 'auto',supplicant=supplicant,hostapd=hostapd,
            upstream_text=M.control_ssid(upstream)..'\n'}
end
return M
