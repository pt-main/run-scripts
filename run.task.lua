-- @python
print_colored("[?YW]    Installing go-build...[?RT]\n")
run_cli("-install github.com/pt-main/run-scripts@main/go-build.py go-build 'Universal crossplatform go building script'")

print_colored("[?YW]    Installing addMit...[?RT]\n")
run_cli("-install github.com/pt-main/run-scripts@main/addMit.py addMit 'Write MIT license in current dir to LICENSE file'")

print_colored("[?YW]    Installing addApache20...[?RT]\n")
run_cli("-install github.com/pt-main/run-scripts@main/addApache20.py addApache20 'Write Apache 2.0 license in current dir to LICENSE file'")

-- @noreq
print_colored("[?YW]    Installing sysinfo...[?RT]\n")
run_cli("-install github.com/pt-main/run-scripts@main/sysinfo.lua sysinfo 'Show system info (works on windows, macos, linux)'")

print_colored("[?YW]    Installing luabench...[?RT]\n")
run_cli("-install github.com/pt-main/run-scripts@main/lua-bench.lua luabench 'Lua speed benchmark'")

print_colored("[?YW]    Installing fastfetch...[?RT]\n")
run_cli("-install github.com/pt-main/run-scripts@main/sysfetch.lua sysfetch 'Colored beautifull system info'")

-- @all
script("noreq")
script("python")

-- @
print_colored("[?YW]Installation start...[?RT]\n")

local args = get_args()

local ok = true

if #args == 0 then
    print_colored("[?RD]Has no args! Installation canceled[?RT]")
    ok = false
else
    for i = 1, #args do
        script(args[i])
    end
end

if ok then 
    print_colored("[?BGN]Installation complete...[?RT]\n")
end
