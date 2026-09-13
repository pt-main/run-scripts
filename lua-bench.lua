local clock      = os.clock
local load_chunk = loadstring or load   


local HAS_JIT  = (type(jit) == "table")
local HAS_INT  = (math.type ~= nil)     
local HAS_UTF8 = (utf8 ~= nil)          
local BIT      = rawget(_G, "bit") or rawget(_G, "bit32")



local NATIVE_INT_OPS = (load_chunk("return function(a,b) return a//b, a&b end") ~= nil)



local function measure(fn, arg, warmup, runs)
    for _ = 1, warmup do fn(arg) end
    collectgarbage("collect")
    collectgarbage("collect")
    local best = math.huge
    for _ = 1, runs do
        collectgarbage("collect")
        local t0 = clock()
        fn(arg)
        local dt = clock() - t0
        if dt < best then best = dt end
    end
    return best
end


local TESTS = {}
local function add(name, N, fn)
    TESTS[#TESTS+1] = { name = name, N = N, fn = fn }
end


add("num: sum 1..N", 5e7, function(N)
    local s = 0
    for i = 1, N do s = s + i end
    return s
end)

add("num: mul-acc", 2e7, function(N)
    local s = 1
    for i = 1, N do s = s * 1.0000001 + i * 0.5 end
    return s
end)


add("num: 3^i (i in 0..63)", 2e7, function(N)
    local s = 0
    for i = 1, N do s = s + 3 ^ (i % 64) end
    return s
end)

add("num: sqrt + div", 1e7, function(N)
    local s = 0
    for i = 1, N do s = s + math.sqrt(i) / (i + 1) end
    return s
end)

if NATIVE_INT_OPS then
    
    local f = assert(load_chunk([[
        return function(N)
            local s = 0
            for i = 1, N do
                s = s + (i // 3) + (i & 0xFF)
            end
            return s
        end
    ]]))()
    add("num: i//3 + i&0xFF (native)", 2e7, f)
elseif BIT then
    local band   = BIT.band
    local rshift = BIT.rshift
    add("num: rshift + band (bitlib)", 2e7, function(N)
        local s = 0
        for i = 1, N do
            s = s + rshift(i, 1) + band(i, 0xFF)
        end
        return s
    end)
end


local function add1(x) return x + 1 end

add("call: local function", 2e7, function(N)
    local s = 0
    for i = 1, N do s = add1(s) end
    return s
end)

local Lib = { inc = function(x) return x + 1 end }
add("call: table method", 2e7, function(N)
    local s = 0
    for i = 1, N do s = Lib.inc(s) end
    return s
end)

add("call: closure", 1e7, function(N)
    local up = 0
    local f = function() up = up + 1; return up end
    for _ = 1, N do f() end
    return up
end)


add("tbl: fill array", 5e6, function(N)
    local t = {}
    for i = 1, N do t[i] = i end
    return t
end)

add("tbl: ipairs read (1e3 array)", 1e4, function(N)
    local t = {}
    for i = 1, 1000 do t[i] = i end
    local s = 0
    for _ = 1, N do
        for _, v in ipairs(t) do s = s + v end
    end
    return s
end)

add("tbl: hash lookup", 2e7, function(N)
    local t = { a=1, b=2, c=3, d=4 }
    local s = 0
    for _ = 1, N do s = s + t.a + t.b + t.c + t.d end
    return s
end)

add("tbl: hash insert", 5e5, function(N)
    local t = {}
    for i = 1, N do t["k" .. i] = i end
    return t
end)


add("str: concat ..", 5e6, function(N)
    local s = ""
    for _ = 1, N do
        s = s .. "x"
        if #s > 50000 then s = "" end   
    end
    return s
end)

add("str: tostring + len", 5e6, function(N)
    local s = 0
    for i = 1, N do s = s + #tostring(i) end
    return s
end)

add("str: find plain", 2e6, function(N)
    local str = string.rep("abcdefg", 100)
    local n = 0
    for _ = 1, N do
        if string.find(str, "cd", 1, true) then n = n + 1 end
    end
    return n
end)


add("oo: metatable __add", 5e6, function(N)
    local mt = {}
    mt.__add = function(a, b) return { x = a.x + b.x, y = a.y + b.y } end
    local a = setmetatable({ x=1, y=2 }, mt)
    local b = setmetatable({ x=3, y=4 }, mt)
    local v = a
    for _ = 1, N do v = v + b end
    return v.x
end)


add("coro: yield/resume", 5e5, function(N)
    local co = coroutine.create(function()
        for i = 1, N do coroutine.yield(i) end
    end)
    local s = 0
    while coroutine.resume(co) do s = s + 1 end
    return s
end)

add("pcall: overhead", 1e6, function(N)
    local n = 0
    for i = 1, N do
        if pcall(add1, i) then n = n + 1 end
    end
    return n
end)

add("sort: 10k random", 10, function(N)
    local r = 0
    for _ = 1, N do
        math.randomseed(42)
        local t = {}
        for i = 1, 10000 do t[i] = math.random() end
        table.sort(t)
        r = r + t[1]
    end
    return r
end)

local function fib(n)
    if n < 2 then return n end
    return fib(n-1) + fib(n-2)
end
add("recur: fib(30)", 3, function(N)
    local s = 0
    for _ = 1, N do s = s + fib(30) end
    return s
end)


local function run_phase()
    local out = {}
    for _, t in ipairs(TESTS) do
        out[t.name] = measure(t.fn, t.N, 2, 3)   
    end
    return out
end


local function header(title)
    print(("="):rep(78))
    print(title)
    print(("="):rep(78))
end

local function print_env()
    header("Lua Benchmark Suite v3")
    print(("engine : %s"):format(_VERSION))
    if HAS_JIT then
        print(("jit    : %s   arch=%s   os=%s")
            :format(jit.version, jit.arch, jit.os))
        print(("jit on : %s"):format(tostring(jit.status())))
    else
        print("jit    : <not available>")
    end
    print(("int    : %s   native bit-ops: %s   bit-lib: %s   utf8: %s")
        :format(tostring(HAS_INT), tostring(NATIVE_INT_OPS),
                BIT and "yes" or "no", tostring(HAS_UTF8)))
    print()
end

local function print_results(label, r)
    print(("-"):rep(78))
    print(string.format("%-34s %10s  %13s", label .. " — test", "time,s", "ops/s"))
    print(("-"):rep(78))
    for _, t in ipairs(TESTS) do
        local dt = r[t.name]
        print(string.format("%-34s %10.4f  %13.0f",
            t.name, dt, t.N / dt))
    end
    print()
end

local function print_summary(a, b)
    header("SUMMARY — JIT ON  vs  JIT OFF")
    print(string.format("%-34s %9s  %9s  %9s",
        "test", "jit on,s", "jit off,s", "speedup"))
    print(("-"):rep(78))
    local sum_sp, n = 0, 0
    for _, t in ipairs(TESTS) do
        local ton, toff = a[t.name], b[t.name]
        local sp = toff / ton
        sum_sp = sum_sp + sp
        n = n + 1
        print(string.format("%-34s %9.4f  %9.4f  %8.2fx",
            t.name, ton, toff, sp))
    end
    print(("-"):rep(78))
    print(string.format("%-34s %9s  %9s  %8.2fx",
        "AVERAGE", "", "", sum_sp / n))
    print()
end


print_env()

if HAS_JIT then
    
    jit.on()
    jit.flush()
    collectgarbage("collect")
    collectgarbage("collect")
    header("PHASE 1/2 — JIT ON")
    local r_on = run_phase()
    print_results("JIT ON", r_on)

    
    jit.off()
    jit.flush()   
    collectgarbage("collect")
    collectgarbage("collect")
    header("PHASE 2/2 — JIT OFF (interpreter)")
    local r_off = run_phase()
    print_results("JIT OFF", r_off)

    print_summary(r_on, r_off)
else
    collectgarbage("collect")
    collectgarbage("collect")
    header("PHASE 1/1 — interpreter")
    local r = run_phase()
    print_results("LUA", r)
end
