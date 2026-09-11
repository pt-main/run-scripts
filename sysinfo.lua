local function capture(cmd)
    local f = io.popen(cmd .. " 2>/dev/null")
    if not f then return nil end
    local out = f:read("*a")
    f:close()
    if not out or out == "" then return nil end
    return out
end

local function trim(s)
    return (s:gsub("^%s+", ""):gsub("%s+$", ""))
end

local function detect_os()
    local sep = package.config:sub(1, 1)
    if sep == "\\" then return "windows" end

    local uname = capture("uname -s")
    if uname then
        uname = trim(uname):lower()
        if uname:find("darwin") then return "macos" end
        if uname:find("linux")  then return "linux" end
    end
    return "unknown"
end

local function get_env()
    local user = os.getenv("USER") or os.getenv("USERNAME") or "?"
    local home = os.getenv("HOME") or os.getenv("USERPROFILE") or "?"
    local shell = os.getenv("SHELL") or os.getenv("COMSPEC") or "?"
    return user, home, shell
end

local function get_cpu(os_name)
    if os_name == "linux" then
        local f = io.open("/proc/cpuinfo", "r")
        if f then
            local model, cores = nil, 0
            for line in f:lines() do
                if not model then
                    model = line:match("^model name%s*:%s*(.+)$")
                end
                if line:match("^processor%s*:") then
                    cores = cores + 1
                end
            end
            f:close()
            return model or "?", cores
        end
    elseif os_name == "macos" then
        local model = capture("sysctl -n machdep.cpu.brand_string")
        local cores = tonumber(trim(capture("sysctl -n hw.ncpu") or "")) or 0
        return model and trim(model) or "?", cores
    elseif os_name == "windows" then
        local model = capture('wmic cpu get name /value')
        local cores = capture('wmic cpu get NumberOfCores /value')
        model = model and trim(model:match("Name=(.+)") or "?") or "?"
        cores = tonumber(trim(cores and (cores:match("NumberOfCores=(%d+)") or "0") or "0")) or 0
        return model, cores
    end
    return "?", 0
end

local function get_mem(os_name)
    if os_name == "linux" then
        local f = io.open("/proc/meminfo", "r")
        if f then
            local total, avail
            for line in f:lines() do
                total = total or tonumber(line:match("^MemTotal:%s*(%d+)"))
                avail = avail or tonumber(line:match("^MemAvailable:%s*(%d+)"))
            end
            f:close()
            if total then
                return string.format("%.1f GB total, %.1f GB free",
                    total / 1024 / 1024, (avail or 0) / 1024 / 1024)
            end
        end
    elseif os_name == "macos" then
        local bytes = tonumber(trim(capture("sysctl -n hw.memsize") or "0")) or 0
        return string.format("%.1f GB total", bytes / 1024 / 1024 / 1024)
    elseif os_name == "windows" then
        local out = capture('wmic computersystem get TotalPhysicalMemory /value')
        local bytes = tonumber(out and (out:match("TotalPhysicalMemory=(%d+)") or "0") or "0") or 0
        return string.format("%.1f GB total", bytes / 1024 / 1024 / 1024)
    end
    return "?"
end

local function get_disk(os_name)
    local out
    if os_name == "windows" then
        out = capture("wmic logicaldisk get size,freespace,caption")
    else
        out = capture("df -h /")
    end
    if not out then return "?" end
    local lines = {}
    for line in out:gmatch("([^\r\n]+)") do
        table.insert(lines , "         : " .. line)
    end
    return table.concat(lines, "\n")
end

local function get_kernel(os_name)
    if os_name == "windows" then
        local out = capture("ver")
        return out and trim(out) or "?"
    end
    return trim(capture("uname -sr") or "?")
end

local function get_lua_version()
    return _VERSION .. " (" .. tostring(_G.jit and _G.jit.version or "PUC") .. ")"
end

local os_name = detect_os()
local user, home, shell = get_env()
local cpu_model, cpu_cores = get_cpu(os_name)
local mem = get_mem(os_name)
local disk = get_disk(os_name)
local kernel = get_kernel(os_name)

print("=== System Info ===")
print(("OS       : %s"):format(os_name))
print(("Kernel   : %s"):format(kernel))
print(("User     : %s"):format(user))
print(("Home     : %s"):format(home))
print(("Shell    : %s"):format(shell))
print(("CPU      : %s (%d cores)"):format(cpu_model, cpu_cores))
print(("Memory   : %s"):format(mem))
print(("Disk     : \n%s"):format(disk))
print(("Lua      : %s"):format(get_lua_version()))
print(("Time     : %s"):format(os.date("%Y-%m-%d %H:%M:%S")))
