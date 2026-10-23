-- R15 vendor-radio settings. CBI performs authenticated UCI save/apply.
-- No shell commands, interface creation or management configuration occurs here.
local m=Map('r15_radio',translate('Wireless repeater'),
    translate('The selected band is used for the upstream connection and local Wi-Fi. The channel follows the upstream automatically. This build supports WPA2-Personal with AES, 2.4 GHz channels 1–13 and 5 GHz channels 36–48.'))
local s=m:section(NamedSection,'repeater','repeater')
s.addremove=false
local function encode(value)
    return (value:gsub('.',function(c) return string.format('%02x',c:byte()) end))
end
local function decode(value)
    if type(value)~='string' or #value<2 or #value>64 or #value%2~=0 or value:find('[^%x]') then return nil end
    return (value:gsub('..',function(c) return string.char(tonumber(c,16)) end))
end
local enabled=s:option(Flag,'enabled',translate('Enable repeater'))
enabled.rmempty=false
enabled.default='0'
local band=s:option(ListValue,'band',translate('Wi-Fi band'))
band:value('2g',translate('2.4 GHz'))
band:value('5g',translate('5 GHz'))
band.rmempty=false
local function network(name,key_name,title,key_title)
    -- Capture before CBI parses writes, so a new SSID cannot conceal a stale PSK.
    local original_name=decode(m.uci:get('r15_radio','repeater',name))
    local original_key=m.uci:get('r15_radio','repeater',key_name)
    local field=s:option(Value,name,title)
    field.rmempty=false
    function field.cfgvalue(self,section)
        if self.tag_error and self.tag_error[section] then return self:formvalue(section) end
        return decode(m.uci:get('r15_radio',section,name))
    end
    function field.validate(self,value)
        if type(value)~='string' or #value<1 or #value>32 then
            return nil,translate('Use a Wi-Fi name containing 1–32 bytes.')
        end
        return value
    end
    function field.write(self,section,value)
        return m.uci:set('r15_radio',section,name,encode(value))
    end
    local key=s:option(Value,key_name,key_title)
    key.password=true
    key.rmempty=false
    function key.validate(self,value,section)
        if type(value)~='string' then return nil,translate('Enter a Wi-Fi password.') end
        local derived=#value==64 and not value:find('[^%x]')
        if not derived and (#value<8 or #value>63 or value:find('[^ -~]')) then
            return nil,translate('Use 8–63 printable ASCII characters or a 64-digit hexadecimal key.')
        end
        if derived and type(original_key)=='string' and value:lower()==original_key:lower()
            and field:formvalue(section)~=original_name then
            return nil,translate('Re-enter the Wi-Fi password when changing its name.')
        end
        return value
    end
end
network('upstream_ssid_hex','upstream_key',translate('Upstream Wi-Fi name'),translate('Upstream Wi-Fi password'))
network('ap_ssid_hex','ap_key',translate('Local Wi-Fi name'),translate('Local Wi-Fi password'))
local pin=s:option(Value,'bssid',translate('Optional upstream BSSID'),
    translate('Leave empty to find the upstream by its Wi-Fi name automatically.'))
pin.rmempty=true
function pin.validate(self,value)
    if value==nil or value=='' then return value end
    if type(value)~='string' or not value:match('^%x%x:%x%x:%x%x:%x%x:%x%x:%x%x$') then
        return nil,translate('Enter a valid unicast BSSID or leave empty.')
    end
    value=value:lower()
    if value=='00:00:00:00:00:00' or tonumber(value:sub(1,2),16)%2~=0 then
        return nil,translate('Enter a valid unicast BSSID or leave empty.')
    end
    return value
end
return m
