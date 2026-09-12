-- @python
print_colored("[?YW]    Installing go-build...[?RT]\n")
run_cli("-install github.com/pt-main/run-scripts@main/go-build.py go-build 'Universal crossplatform go building script'")

print_colored("[?YW]    Installing addMit...[?RT]\n")
run_cli("-install github.com/pt-main/run-scripts@main/addMit.py addMit 'Write MIT license in current dir to LICENSE file'")

print_colored("[?YW]    Installing addApcache20...[?RT]\n")
run_cli("-install github.com/pt-main/run-scripts@main/addApache20.py addApache20 'Write Apache 2.0 license in current dir to LICENSE file'")

-- @noreq
print_colored("[?YW]    Installing sysinfo...[?RT]\n")
run_cli("-install github.com/pt-main/run-scripts@main/sysinfo.lua sysinfo 'Show system info (works on windows, macos, linux)'")

-- @!
print_colored("[?YW]Instalation start...[?RT]\n")

local args = get_args()
for i = 1, #args do
    local arg = args[i]
    print_colored("[?YW]Installing " .. arg .. "...[?RT]\n")
    script(arg)
    print("")
end

print_colored("[?BGN]Instalation complete...[?RT]\n")
