local IS_WIN = package.config:sub(1, 1) == "\\"

local COLOR = not os.getenv("NO_COLOR")
if arg then
  for _, a in ipairs(arg) do
      if a == "--no-color" then COLOR = false end
  end
end

local function c(code, text)
  if text == nil then return nil end
  if not COLOR then return tostring(text) end
  return "\27[" .. code .. "m" .. tostring(text) .. "\27[0m"
end





local function read_file(path)
  local f = io.open(path, "rb")
  if not f then return nil end
  local data = f:read("*a")
  f:close()
  return data
end

local function file_exists(path)
  local f = io.open(path, "rb")
  if f then f:close(); return true end
  return false
end

local function run(cmd)
  local p = io.popen(cmd)
  if not p then return nil end
  local out = p:read("*a")
  p:close()
  return out
end

local function sh_lines(cmd)
  local p = io.popen(cmd .. " 2>/dev/null")
  if not p then return 0 end
  local n = 0
  for _ in p:lines() do n = n + 1 end
  p:close()
  return n
end

local function trim(s)
  if not s then return nil end
  s = s:gsub("^%s+", ""):gsub("%s+$", "")
  if s == "" then return nil end
  return s
end

local function first_line(s)
  s = trim(s)
  if not s then return nil end
  return s:match("([^\n\r]+)")
end

local function basename(p)
  if not p then return nil end
  return p:match("([^/\\]+)$") or p
end

local function human(bytes)
  local units = { "B", "KiB", "MiB", "GiB", "TiB", "PiB" }
  local n = tonumber(bytes) or 0
  local i = 1
  while n >= 1024 and i < #units do
    n = n / 1024
    i = i + 1
  end
  if i == 1 then
    return string.format("%d %s", n, units[i])
  end
  return string.format("%.2f %s", n, units[i])
end


local function ulen(s)
  if not s then return 0 end
  local _, n = s:gsub("[%z\1-\127\194-\244][\128-\191]*", "")
  return n
end



local user = os.getenv("USER") or os.getenv("USERNAME") or "user"
local host = first_line(run("uname -n"))
          or os.getenv("COMPUTERNAME")
          or "host"
local user_host = host.."@"..user



local function get_os()
  if IS_WIN then
    local v = run("ver")
    local ver = v and v:match("Version ([%d%.]+)")
    return "Windows" .. (ver and (" " .. ver) or "")
  end

  local rel = read_file("/etc/os-release")
  if rel then
    local pretty = rel:match('PRETTY_NAME="([^"]+)"') or rel:match("PRETTY_NAME=([^\n]+)")
    if pretty then return trim(pretty) end
  end

  if read_file("/System/Library/CoreServices/SystemVersion.plist") then
    local name = first_line(run("sw_vers -productName")) or "macOS"
    local ver  = first_line(run("sw_vers -productVersion")) or ""
    return trim(name .. " " .. ver)
  end

  return first_line(run("uname -s")) or "Unknown"
end

local function get_kernel()
  if IS_WIN then
    local v = run("ver")
    return v and v:match("Version ([%d%.]+)") or "Windows"
  end
  return first_line(run("uname -sr")) or "Unknown"
end

local function get_host()
  if not IS_WIN then
    local name = trim(read_file("/sys/devices/virtual/dmi/id/product_name"))
    local ver  = trim(read_file("/sys/devices/virtual/dmi/id/product_version"))
    if name then
      return ver and (name .. " (" .. ver .. ")") or name
    end
    local mac = first_line(run("sysctl -n hw.model 2>/dev/null"))
    if mac then return mac end
  end
  return first_line(run("uname -n"))
      or os.getenv("COMPUTERNAME")
      or "Unknown"
end

local function fmt_uptime(seconds)
  seconds = math.floor(tonumber(seconds) or 0)
  local d = math.floor(seconds / 86400)
  local h = math.floor(seconds % 86400 / 3600)
  local m = math.floor(seconds % 3600 / 60)
  local parts = {}
  if d > 0 then parts[#parts + 1] = d .. "d" end
  if h > 0 then parts[#parts + 1] = h .. "h" end
  parts[#parts + 1] = m .. "m"
  return table.concat(parts, " ")
end

local function get_uptime()
  if IS_WIN then return nil end

  local up = read_file("/proc/uptime")
  if up then
    return fmt_uptime(up:match("^(%S+)"))
  end

  
  local boot = run("sysctl -n kern.boottime 2>/dev/null")
  if boot then
    local sec = boot:match("sec%s*=%s*(%d+)")
    if sec then
      return fmt_uptime(os.time() - tonumber(sec))
    end
  end
  return nil
end

local function get_shell()
  local sh = os.getenv("SHELL") or os.getenv("COMSPEC")
  if sh and sh ~= "" then return basename(sh) end
  return nil
end

local function get_terminal()
  return os.getenv("TERM_PROGRAM")
      or (os.getenv("WT_SESSION") and "Windows Terminal")
      or os.getenv("TERM")
end

local function get_cpu()
  if IS_WIN then
    local out = run("wmic cpu get name /value")
    local name = out and out:match("Name=([^\n]+)")
    if name then return trim(name) end
    return os.getenv("PROCESSOR_IDENTIFIER")
  end

  local cpuinfo = read_file("/proc/cpuinfo")
  if cpuinfo then
    local model = trim(cpuinfo:match("model name%s*:%s*([^\n]+)")
                    or cpuinfo:match("Model%s*:%s*([^\n]+)"))
    local cores = 0
    for line in cpuinfo:gmatch("[^\n]+") do
      if line:match("^processor%s*:") then cores = cores + 1 end
    end
    if model then
      return string.format("%s (%d)", model, cores)
    end
  end

  local mac = first_line(run("sysctl -n machdep.cpu.brand_string 2>/dev/null"))
  if mac then
    local cores = tonumber(first_line(run("sysctl -n hw.ncpu 2>/dev/null"))) or 0
    return string.format("%s (%d)", mac, cores)
  end
  return nil
end

local function get_memory()
  local mem = read_file("/proc/meminfo")
  if mem then
    local total = tonumber(mem:match("MemTotal:%s*(%d+)"))
    local avail = tonumber(mem:match("MemAvailable:%s*(%d+)"))
                  or tonumber(mem:match("MemFree:%s*(%d+)"))
    if total then
      local used = total - (avail or 0)
      return string.format("%s / %s", human(used * 1024), human(total * 1024))
    end
  end

  if IS_WIN then
    local out = run("wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /value")
    if out then
      local free = tonumber(out:match("FreePhysicalMemory=(%d+)"))
      local tot  = tonumber(out:match("TotalVisibleMemorySize=(%d+)"))
      if tot then
        return string.format("%s / %s",
          human((tot - (free or 0)) * 1024), human(tot * 1024))
      end
    end
  end

  local bytes = tonumber(first_line(run("sysctl -n hw.memsize 2>/dev/null")))
  if bytes then return human(bytes) end
  return nil
end

local function get_swap()
  if IS_WIN then return nil end
  local mem = read_file("/proc/meminfo")
  if not mem then return nil end
  local t = tonumber(mem:match("SwapTotal:%s*(%d+)"))
  local f = tonumber(mem:match("SwapFree:%s*(%d+)"))
  if not t or t == 0 then return nil end
  return string.format("%s / %s", human((t - (f or 0)) * 1024), human(t * 1024))
end

local function get_disk()
  if IS_WIN then return nil end
  local out = run("df -h / 2>/dev/null")
  if not out then return nil end
  local line = out:match("\n([^\n]+)")
  if not line then return nil end
  local size, used, _, pct = line:match("^%S+%s+(%S+)%s+(%S+)%s+(%S+)%s+(%S+)")
  if size then
    return string.format("%s / %s (%s)", used, size, pct)
  end
  return nil
end

local function get_ip()
  if IS_WIN then
    local out = run("ipconfig")
    if out then
      return out:match("IPv4[^:]*:%s*([%d%.]+)")
    end
    return nil
  end

  local out = run("hostname -I 2>/dev/null")
  local ip = out and out:match("(%d+%.%d+%.%d+%.%d+)")
  if ip then return ip end

  ip = first_line(run("ipconfig getifaddr en0 2>/dev/null"))
  return ip
end

local function get_locale()
  return os.getenv("LANG") or os.getenv("LC_ALL") or os.getenv("LC_MESSAGES")
end

local function get_datetime()
  return os.date("%Y-%m-%d %H:%M:%S")
end

local function get_loadavg()
  local s = first_line(read_file("/proc/loadavg"))
  if not s then return nil end
  local a, b, cc = s:match("(%S+)%s+(%S+)%s+(%S+)")
  return a and (a .. ", " .. b .. ", " .. cc) or nil
end

local function get_procs()
  if IS_WIN then return nil end
  local p = io.popen("ls /proc 2>/dev/null | grep -c '^[0-9]\\+$'")
  if not p then return nil end
  local n = p:read("*a"); p:close()
  return trim(n)
end

local function get_de()
  return os.getenv("XDG_CURRENT_DESKTOP")
      or os.getenv("DESKTOP_SESSION")
      or os.getenv("SESSIONNAME")
end

local function get_wm()
  return os.getenv("WAYLAND_DISPLAY") and "Wayland"
      or os.getenv("XDG_SESSION_TYPE")
      or (os.getenv("DISPLAY") and "X11")
end

local function get_battery()
  if IS_WIN then return nil end
  local base = "/sys/class/power_supply/"
  local p = io.popen("ls " .. base .. " 2>/dev/null")
  if not p then return nil end
  local result
  for bat in p:lines() do
    if bat:match("^BAT") then
      local cap   = trim(read_file(base .. bat .. "/capacity"))
      local state = trim(read_file(base .. bat .. "/status"))
      if cap then
        result = cap .. "%" .. (state and (" [" .. state .. "]") or "")
        break
      end
    end
  end
  p:close()
  return result
end

local function dmi(field)
  return trim(read_file("/sys/devices/virtual/dmi/id/" .. field))
end

local function get_board()
  local v = dmi("board_vendor")
  local n = dmi("board_name")
  if n then return (v and (v .. " ") or "") .. n end
  return nil
end

local function get_bios()
  local v = dmi("bios_vendor")
  local ver = dmi("bios_version")
  if ver then return (v and (v .. " ") or "") .. ver end
  return nil
end

local function get_packages()
  if IS_WIN then return nil end
  if file_exists("/var/lib/dpkg/status") then
    return sh_lines("dpkg-query -f '.\n' -W") .. " (dpkg)"
  end
  if file_exists("/var/lib/pacman/local") then
    return sh_lines("ls /var/lib/pacman/local") .. " (pacman)"
  end
  if file_exists("/var/lib/rpm") then
    return sh_lines("rpm -qa") .. " (rpm)"
  end
  if file_exists("/lib/apk/db/installed") then
    return sh_lines("apk info") .. " (apk)"
  end
  return nil
end

local function get_resolution()
  if IS_WIN then return nil end
  local p = io.popen("xrandr 2>/dev/null | grep '\\*'")
  if p then
    local line = p:read("*l")
    p:close()
    local r = line and line:match("(%d+x%d+)")
    if r then return r end
  end
  local p2 = io.popen("ls /sys/class/drm/*/modes 2>/dev/null | head -1")
  if p2 then
    local f = trim(p2:read("*a"))
    p2:close()
    if f then return first_line(read_file(f)) end
  end
  return nil
end





local LOGO = {
  "  _                ",
  " | |   _   _  __ _ ",
  " | |  | | | |/ _` |",
  " | |__| |_| | (_| |",
  " |_____\\__,_|\\__,_|",
}

local LOGO_COLORS = { "38;5;51", "38;5;45", "38;5;39", "38;5;33", "38;5;27" }

local function color_mode()
  local ct = os.getenv("COLORTERM") or ""
  if ct == "truecolor" or ct == "24bit" then return "truecolor" end
  if (os.getenv("TERM") or ""):match("256color") then return "256" end
  return "16"
end

local function color_bar()
  if not COLOR then return nil end

  local mode  = color_mode()
  local n     = #user_host
  local parts = {}

  for i = 0, n - 1 do
    local t = i / (n - 1)
    local h = t * 300
    local c = 1
    local x = c * (1 - math.abs((h / 60) % 2 - 1))
    local r, g, b
    if     h <  60 then r, g, b = c, x, 0
    elseif h < 120 then r, g, b = x, c, 0
    elseif h < 180 then r, g, b = 0, c, x
    elseif h < 240 then r, g, b = 0, x, c
    else                r, g, b = x, 0, c end

    if mode == "truecolor" then
      parts[#parts + 1] = string.format("\27[48;2;%d;%d;%dm ",
        math.floor(r * 255 + 0.5),
        math.floor(g * 255 + 0.5),
        math.floor(b * 255 + 0.5))
    elseif mode == "256" then
      local ri = math.floor(r * 5 + 0.5)
      local gi = math.floor(g * 5 + 0.5)
      local bi = math.floor(b * 5 + 0.5)
      parts[#parts + 1] = string.format("\27[48;5;%dm ", 16 + 36*ri + 6*gi + bi)
    else
      local codes = { 41, 43, 42, 46, 44, 45 }
      parts[#parts + 1] = string.format("\27[%dm ", codes[(i % #codes) + 1])
    end
  end

  parts[#parts + 1] = "\27[0m"
  return table.concat(parts)
end





local entries = {
  { "OS",         get_os() },
  { "Host",       get_host() },
  { "Kernel",     get_kernel() },
  { "Uptime",     get_uptime() },
  { "Shell",      get_shell() },
  { "Terminal",   get_terminal() },
  { "DE",         get_de() },
  { "WM",         get_wm() },
  { "Locale",     get_locale() },
  { "DateTime",   get_datetime() },
  { "CPU",        get_cpu() },
  { "Board",      get_board() },
  { "BIOS",       get_bios() },
  { "Memory",     get_memory() },
  { "Swap",       get_swap() },
  { "Disk",       get_disk() },
  { "Resolution", get_resolution() },
  { "Packages",   get_packages() },
  { "Processes",  get_procs() },
  { "Load",       get_loadavg() },
  { "Battery",    get_battery() },
  { "IP",         get_ip() },
}

local info = {}
info[#info + 1] = c("1;36", user) .. c("1;37", "@") .. c("1;36", host)
info[#info + 1] = c("90", string.rep("-", ulen(user) + ulen(host) + 1))

for idx, e in ipairs(entries) do
  if e[2] and e[2] ~= "" then
    info[#info + 1] = c("1;34", e[1] .. ":") .. " " .. e[2]
  end
end

local bar = color_bar()
if bar then info[#info + 1] = bar end





local logo_w = 0
for _, l in ipairs(LOGO) do
  local w = ulen(l)
  if w > logo_w then logo_w = w end
end

local total = math.max(#LOGO, #info)

io.write("\n")
for i = 1, total do
  local left = LOGO[i] or ""
  left = left .. string.rep(" ", logo_w - ulen(left))
  left = c(LOGO_COLORS[((i - 1) % #LOGO_COLORS) + 1], left)
  io.write(left .. "   " .. (info[i] or "") .. "\n")
end
io.write("\n")
