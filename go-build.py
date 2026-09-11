#!/usr/bin/env python3
"""
Universal Go cross-compilation script — fully configurable and optimized.

Features:
- Dynamic platform list from `go tool dist list`
- JSON configuration file (overridable by CLI)
- Parallel builds
- Full control over go build flags (-trimpath, -buildvcs, -gcflags, etc.)
- Rich placeholders for output filenames
- CGO, GOARM, GOAMD64, build tags, custom env vars
- Clean output directory
- Platform filtering with include/exclude and wildcards
- Colorized output, progress bar, log levels, interactive mode
- Per-platform overrides (ldflags, goarm, goamd64, cgo, tags, env)
- Save configuration to file
- Generate checksums and create archive
- Built-in documentation via `docs` command
- Build statistics (--stats)
"""

import argparse
import subprocess
import sys
import os
import shutil
import json
import re
import shlex
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import time

# ----------------------------------------------------------------------
# Documentation strings (for built-in docs command)
EN_DOC = """SYNOPSIS
    [scriptname] [build] [OPTIONS]
    [scriptname] docs [LANG]

DESCRIPTION
    This script automates cross-compilation of Go projects for multiple platforms.
    It is fully configurable via command-line arguments or a JSON configuration file,
    supports parallel builds, dynamic platform discovery, per-platform overrides,
    checksum generation, archiving, and more.

COMMANDS
    build (default)
        Build the project for the specified platforms.

    docs [LANG]
        Display this documentation. LANG can be 'en' (default) or 'ru'.

OPTIONS (for build command)
    -c, --config FILE
        Path to JSON configuration file. Settings merged with CLI overrides.

    -p, --project-path PATH
        Path to the Go project (directory containing go.mod). Default: current directory.

    -o, --output-dir DIR
        Output directory for binaries. Default: ./build.

    -n, --name-template TEMPLATE
        Name template with placeholders: {project}, {os}, {arch}, {version}, {date}, {time}, {commit}.
        Default: "{project}-{os}-{arch}-{version}"

    -pl, --platforms LIST
        Comma-separated list of platforms (os/arch) or aliases (all, windows, linux, etc.)
        or wildcards (windows/*, *arm*). Default: all.

    --exclude LIST
        Comma-separated list of platforms or aliases to exclude.

    -v, --version VERSION
        Version string to substitute in name template. Default: "final".

    -ld, --ldflags FLAGS
        Additional ldflags (e.g. '-X main.version=1.0').

    -tags TAGS
        Build tags (comma-separated).

    --cgo {0,1}
        Set CGO_ENABLED (0 or 1). Default: 0.

    --goarm ARM
        Set GOARM (e.g. 7 for armv7).

    --goamd64 AMD64
        Set GOAMD64 (e.g. v3).

    --go-build-args ARGS
        Space-separated flags for 'go build' (e.g. '-trimpath -buildvcs=false -gcflags=all=-l').
        Overrides config.

    --clean
        Remove output directory before building.

    --verbose
        Increase verbosity (equivalent to --log-level=2).

    --quiet
        Suppress most output (only errors).

    --debug
        Enable debug output (equivalent to --log-level=3).

    --log-level {0,1,2,3}
        Log level: 0=quiet, 1=normal, 2=verbose, 3=debug. Default: 1.

    --interactive
        Show configuration and ask for confirmation before building.

    --save-config FILE
        Save the effective configuration to a JSON file.

    --no-color
        Disable colored output.

    --jobs N
        Number of parallel build jobs (default: number of CPU cores).

    --platform-config JSON_OR_FILE
        JSON string or path to file with per-platform overrides (merges with config file).

    --archive
        Create a .tar.gz archive of the output directory after build.

    --checksum
        Generate SHA256 checksums for all built binaries.

    --stats
        Collect and display detailed build statistics (size, time, etc.).

CONFIGURATION FILE FORMAT
    The configuration file is a JSON object with the following keys (all optional):
    {
        "output_dir": "./build",
        "name_template": "{project}-{os}-{arch}-{version}",
        "platforms": ["all"],
        "exclude_platforms": [],
        "version": "final",
        "ldflags": "",
        "tags": "",
        "cgo_enabled": 0,
        "goarm": "",
        "goamd64": "",
        "env": {},
        "go_build_args": ["-trimpath", "-buildvcs=false", "-gcflags=all=-l"],
        "clean_before_build": false,
        "verbose": false,
        "stats": false,
        "platform_config": {
            "linux/arm": {"goarm": "7", "ldflags": "-s -w"}
        }
    }

PLACEHOLDERS
    In the name template, the following placeholders are available:
        {project}   - name of the project (from go.mod or directory)
        {os}        - GOOS
        {arch}      - GOARCH
        {version}   - version string
        {date}      - current date (YYYY-MM-DD)
        {time}      - current time (HHMMSS)
        {commit}    - short Git commit hash (if available)

PLATFORM ALIASES AND WILDCARDS
    - "all"                   – all platforms supported by Go
    - "windows"               – all Windows platforms
    - "linux"                 – all Linux platforms
    - "darwin"                – all macOS platforms
    - "windows/amd64"         – specific platform
    - "windows/*"             – all architectures for Windows
    - "*arm*"                 – all platforms with "arm" in architecture

PER-PLATFORM OVERRIDES
    You can override settings for specific platforms using the "platform_config" key.
    Each key is "os/arch", and the value is an object with any of these fields:
        ldflags, tags, cgo_enabled, goarm, goamd64, env, go_build_args

EXAMPLES
    # Build for all platforms with default settings
    build.py

    # Build only for Linux and Windows amd64
    build.py --platforms linux/amd64,windows/amd64

    # Build for all Linux platforms, excluding armv7
    build.py --platforms linux --exclude linux/arm

    # Use a configuration file and override version
    build.py -c myconfig.json -v 1.2.3

    # Build with custom ldflags and enable CGO for Windows
    build.py --ldflags "-s -w" --cgo 1 --platforms windows/amd64

    # Save effective config for later use
    build.py --save-config saved.json

    # Generate checksums and archive
    build.py --checksum --archive

    # Interactive mode
    build.py --interactive

    # View documentation in Russian
    build.py docs ru

    # Show build statistics
    build.py --stats
"""

RU_DOC = """
ИМЯ
    build.py - Универсальный скрипт кросс-компиляции Go

СИНТАКСИС
    build.py [build] [ОПЦИИ]
    build.py docs [ЯЗЫК]

ОПИСАНИЕ
    Этот скрипт автоматизирует кросс-компиляцию проектов Go для множества платформ.
    Он полностью настраивается через аргументы командной строки или JSON-конфиг,
    поддерживает параллельную сборку, динамическое обнаружение платформ,
    переопределения для отдельных платформ, генерацию контрольных сумм, архивацию и многое другое.

КОМАНДЫ
    build (по умолчанию)
        Собрать проект для указанных платформ.

    docs [ЯЗЫК]
        Показать эту документацию. ЯЗЫК может быть 'en' (по умолчанию) или 'ru'.

ОПЦИИ (для команды build)
    -c, --config ФАЙЛ
        Путь к JSON-файлу конфигурации. Настройки объединяются с параметрами CLI.

    -p, --project-path ПУТЬ
        Путь к проекту Go (каталог с go.mod). По умолчанию: текущий каталог.

    -o, --output-dir КАТАЛОГ
        Каталог для выходных бинарных файлов. По умолчанию: ./build.

    -n, --name-template ШАБЛОН
        Шаблон имени с плейсхолдерами: {project}, {os}, {arch}, {version}, {date}, {time}, {commit}.
        По умолчанию: "{project}-{os}-{arch}-{version}"

    -pl, --platforms СПИСОК
        Список платформ (os/arch) через запятую, или псевдонимы (all, windows, linux, ...)
        или шаблоны с '*' (windows/*, *arm*). По умолчанию: all.

    --exclude СПИСОК
        Список платформ или псевдонимов для исключения через запятую.

    -v, --version ВЕРСИЯ
        Строка версии для подстановки в шаблон имени. По умолчанию: "final".

    -ld, --ldflags ФЛАГИ
        Дополнительные флаги ldflags (например '-X main.version=1.0').

    -tags ТЕГИ
        Теги сборки (через запятую).

    --cgo {0,1}
        Установить CGO_ENABLED (0 или 1). По умолчанию: 0.

    --goarm ARM
        Установить GOARM (например 7 для armv7).

    --goamd64 AMD64
        Установить GOAMD64 (например v3).

    --go-build-args АРГУМЕНТЫ
        Флаги для 'go build' через пробел (например '-trimpath -buildvcs=false -gcflags=all=-l').
        Переопределяет конфиг.

    --clean
        Удалить каталог вывода перед сборкой.

    --verbose
        Увеличить подробность (эквивалентно --log-level=2).

    --quiet
        Подавить большую часть вывода (только ошибки).

    --debug
        Включить отладочный вывод (эквивалентно --log-level=3).

    --log-level {0,1,2,3}
        Уровень логирования: 0=тихо, 1=нормально, 2=подробно, 3=отладка. По умолчанию: 1.

    --interactive
        Показать конфигурацию и запросить подтверждение перед сборкой.

    --save-config ФАЙЛ
        Сохранить эффективную конфигурацию в JSON-файл.

    --no-color
        Отключить цветной вывод.

    --jobs N
        Количество параллельных задач сборки (по умолчанию: число ядер CPU).

    --platform-config JSON_ИЛИ_ФАЙЛ
        JSON-строка или путь к файлу с переопределениями для платформ (объединяется с конфигом).

    --archive
        Создать архив .tar.gz каталога вывода после сборки.

    --checksum
        Сгенерировать SHA256-контрольные суммы для всех собранных бинарников.

    --stats
        Собрать и показать подробную статистику сборки (размер, время и т.д.).

ФОРМАТ КОНФИГУРАЦИОННОГО ФАЙЛА
    Файл конфигурации представляет собой JSON-объект со следующими ключами (все необязательны):
    {
        "output_dir": "./build",
        "name_template": "{project}-{os}-{arch}-{version}",
        "platforms": ["all"],
        "exclude_platforms": [],
        "version": "final",
        "ldflags": "",
        "tags": "",
        "cgo_enabled": 0,
        "goarm": "",
        "goamd64": "",
        "env": {},
        "go_build_args": ["-trimpath", "-buildvcs=false", "-gcflags=all=-l"],
        "clean_before_build": false,
        "verbose": false,
        "stats": false,
        "platform_config": {
            "linux/arm": {"goarm": "7", "ldflags": "-s -w"}
        }
    }

ПЛЕЙСХОЛДЕРЫ
    В шаблоне имени доступны следующие плейсхолдеры:
        {project}   - имя проекта (из go.mod или каталога)
        {os}        - GOOS
        {arch}      - GOARCH
        {version}   - строка версии
        {date}      - текущая дата (ГГГГ-ММ-ДД)
        {time}      - текущее время (ЧЧММСС)
        {commit}    - короткий хеш Git-коммита (если доступен)

ПСЕВДОНИМЫ И ШАБЛОНЫ ПЛАТФОРМ
    - "all"                   – все платформы, поддерживаемые Go
    - "windows"               – все платформы Windows
    - "linux"                 – все платформы Linux
    - "darwin"                – все платформы macOS
    - "windows/amd64"         – конкретная платформа
    - "windows/*"             – все архитектуры для Windows
    - "*arm*"                 – все платформы с "arm" в архитектуре

ПЕРЕОПРЕДЕЛЕНИЯ ДЛЯ ПЛАТФОРМ
    Вы можете переопределять настройки для конкретных платформ, используя ключ "platform_config".
    Каждый ключ — это "os/arch", а значение — объект с любыми из этих полей:
        ldflags, tags, cgo_enabled, goarm, goamd64, env, go_build_args

ПРИМЕРЫ
    # Собрать для всех платформ с настройками по умолчанию
    build.py

    # Собрать только для Linux и Windows amd64
    build.py --platforms linux/amd64,windows/amd64

    # Собрать для всех Linux, исключая armv7
    build.py --platforms linux --exclude linux/arm

    # Использовать конфигурационный файл и переопределить версию
    build.py -c myconfig.json -v 1.2.3

    # Собрать с пользовательскими ldflags и включить CGO для Windows
    build.py --ldflags "-s -w" --cgo 1 --platforms windows/amd64

    # Сохранить эффективную конфигурацию для последующего использования
    build.py --save-config saved.json

    # Сгенерировать контрольные суммы и архив
    build.py --checksum --archive

    # Интерактивный режим
    build.py --interactive

    # Просмотр документации на русском
    build.py docs ru

    # Показать статистику сборки
    build.py --stats
"""

# ----------------------------------------------------------------------
# Default values (can be overridden by config file or CLI)
DEFAULT_CONFIG = {
    "output_dir": "./build",
    "name_template": "{project}-{os}-{arch}-{version}",
    # "platforms" will be filled dynamically from `go tool dist list`
    "exclude_platforms": [],
    "version": "final",
    "ldflags": "",
    "tags": "",
    "cgo_enabled": 0,
    "goarm": "",          # e.g. "7" for armv7
    "goamd64": "",        # e.g. "v3"
    "env": {},            # extra environment variables for all builds
    "go_build_args": [    # all flags passed to 'go build'
        "-trimpath",
        "-buildvcs=false",
        "-gcflags=all=-l"
    ],
    "clean_before_build": False,
    "verbose": False,
    "stats": False,
    "platform_config": {},  # per-platform overrides: {"os/arch": {"ldflags": "...", "goarm": "7", ...}}
}

# ----------------------------------------------------------------------
# Color support (ANSI codes)
COLORS = {
    "reset": "\033[0m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "cyan": "\033[36m",
}
USE_COLORS = sys.stdout.isatty()

def colorize(text, color, use_colors=None):
    if use_colors is None:
        use_colors = USE_COLORS
    if use_colors and color in COLORS:
        return f"{COLORS[color]}{text}{COLORS['reset']}"
    return text

def print_info(msg, color="blue"):
    print(colorize(msg, color))

def print_success(msg):
    print(colorize(msg, "green"))

def print_warning(msg):
    print(colorize(msg, "yellow"))

def print_error(msg):
    print(colorize(msg, "red"), file=sys.stderr)

# ----------------------------------------------------------------------
# Platform detection
_ALL_PLATFORMS = None

def get_all_platforms(force_refresh=False):
    """Return list of (os, arch) tuples from `go tool dist list`."""
    global _ALL_PLATFORMS
    if _ALL_PLATFORMS is not None and not force_refresh:
        return _ALL_PLATFORMS
    try:
        result = subprocess.run(
            ["go", "tool", "dist", "list"],
            capture_output=True,
            text=True,
            check=True,
        )
        platforms = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split("/")
            if len(parts) == 2:
                platforms.append((parts[0], parts[1]))
        _ALL_PLATFORMS = platforms
        return platforms
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print_error(f"Failed to get platform list from 'go tool dist list': {e}")
        print_error("Please ensure Go is installed and in PATH.")
        sys.exit(1)

# ----------------------------------------------------------------------
def get_platform_aliases():
    """Build alias map from OS families to list of (os, arch)."""
    all_plats = get_all_platforms()
    alias_map = {"all": all_plats}
    # Group by OS
    os_groups = {}
    for os_, arch in all_plats:
        os_groups.setdefault(os_, []).append((os_, arch))
    for os_, platforms in os_groups.items():
        alias_map[os_] = platforms
    return alias_map

def expand_platform_alias(alias):
    """Expand alias or wildcard to list of (os, arch)."""
    alias_map = get_platform_aliases()
    # If alias is exact match in map
    if alias in alias_map:
        return alias_map[alias]
    # If alias contains wildcard '*', filter all platforms
    if "*" in alias:
        # Convert wildcard to regex: * -> .*, and escape other regex chars
        pattern = alias.replace("*", ".*")
        # Match against "os/arch"
        regex = re.compile(f"^{pattern}$")
        all_plats = get_all_platforms()
        matched = []
        for os_, arch in all_plats:
            if regex.match(f"{os_}/{arch}"):
                matched.append((os_, arch))
        return matched
    # If it's a specific platform "os/arch"
    if "/" in alias:
        parts = alias.split("/")
        if len(parts) == 2:
            return [(parts[0], parts[1])]
    return []

def resolve_platforms(platforms_list, exclude_list):
    """
    platforms_list: list of strings (may include aliases, wildcards)
    exclude_list: list of strings (same)
    Returns list of (os, arch) tuples.
    """
    result = set()
    for item in platforms_list:
        expanded = expand_platform_alias(item)
        if not expanded:
            print_warning(f"Unknown platform alias or invalid format: '{item}'")
        result.update(expanded)

    # Apply exclusions
    excludes = set()
    for ex in exclude_list:
        expanded = expand_platform_alias(ex)
        if expanded:
            excludes.update(expanded)
        else:
            print_warning(f"Invalid exclude format: '{ex}'")

    result = result - excludes
    return list(result)

# ----------------------------------------------------------------------
def get_git_commit(project_path):
    """Return short git commit hash, or empty string if not a git repo."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=project_path,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""

def get_project_name(project_path):
    """Read module name from go.mod, fallback to directory name."""
    mod_file = Path(project_path) / "go.mod"
    if mod_file.exists():
        with open(mod_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("module "):
                    mod_name = line[len("module "):].strip().split()[0]
                    return mod_name.split("/")[-1]
    return Path(project_path).name

def run_command(cmd, cwd, env=None, verbose=False, description=""):
    """Run a shell command, return (success, output)."""
    if isinstance(cmd, str):
        cmd = shlex.split(cmd)
    if verbose:
        print_info(f"Running: {' '.join(cmd)}", "cyan")
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            if verbose:
                print_error(f"Command failed (code {proc.returncode}): {' '.join(cmd)}")
                if proc.stderr:
                    print_error(proc.stderr)
                if proc.stdout:
                    print_error(proc.stdout)
            return False, proc.stderr
        if verbose:
            if proc.stdout:
                print_info(proc.stdout, "cyan")
            if proc.stderr:
                print_info(proc.stderr, "yellow")
        return True, proc.stdout
    except Exception as e:
        print_error(f"Exception while running command: {e}")
        return False, str(e)

def build_for_platform(project_path, output_dir, goos, goarch, config, verbose, log_level):
    """Build for a single platform using config settings, with per-platform overrides."""
    project_name = get_project_name(project_path)
    git_commit = get_git_commit(project_path)
    now = datetime.now()

    # Apply per-platform overrides
    platform_key = f"{goos}/{goarch}"
    plat_conf = config.get("platform_config", {}).get(platform_key, {})
    # Merge: platform override > global > default
    ldflags = plat_conf.get("ldflags", config["ldflags"])
    tags = plat_conf.get("tags", config["tags"])
    cgo_enabled = plat_conf.get("cgo_enabled", config["cgo_enabled"])
    goarm = plat_conf.get("goarm", config["goarm"])
    goamd64 = plat_conf.get("goamd64", config["goamd64"])
    env_extra = plat_conf.get("env", {})
    go_build_args = plat_conf.get("go_build_args", config["go_build_args"])

    # Prepare placeholders
    placeholders = {
        "project": project_name,
        "os": goos,
        "arch": goarch,
        "version": config["version"],
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H%M%S"),
        "commit": git_commit,
    }

    # Generate filename
    name = config["name_template"].format(**placeholders)
    if goos == "windows" and not name.endswith(".exe"):
        name += ".exe"

    output_file = Path(output_dir) / name
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # Build command: go build + user-defined args + -o + "."
    cmd = ["go", "build"]
    if go_build_args:
        cmd.extend(go_build_args)
    if ldflags:
        cmd.extend(["-ldflags", ldflags])
    if tags:
        cmd.extend(["-tags", tags])
    cmd.extend(["-o", str(output_file), "."])

    env = os.environ.copy()
    env["GOOS"] = goos
    env["GOARCH"] = goarch
    env["CGO_ENABLED"] = str(cgo_enabled)
    if goarm and goarch == "arm":
        env["GOARM"] = goarm
    if goamd64 and goarch == "amd64":
        env["GOAMD64"] = goamd64
    # Add extra env vars (global + per-platform)
    for k, v in config["env"].items():
        env[k] = v
    for k, v in env_extra.items():
        env[k] = v

    if log_level >= 2:  # verbose or debug
        print_info(f"\nBuilding for {goos}/{goarch} -> {output_file}", "blue")
        print_info(f"  Command: {' '.join(cmd)}", "cyan")
        print_info(f"  Environment: GOOS={goos} GOARCH={goarch} CGO_ENABLED={env['CGO_ENABLED']}", "cyan")

    start_time = time.time()
    success, err = run_command(cmd, project_path, env, verbose=(log_level>=2))
    elapsed = time.time() - start_time

    if not success:
        print_error(f"ERROR: Build failed for {goos}/{goarch} (took {elapsed:.1f}s)")
        if log_level >= 1:
            print_error(err)
        return False, output_file, elapsed

    if log_level >= 1:
        print_info(f"  Build successful in {elapsed:.1f}s", "green")
    return True, output_file, elapsed

# ----------------------------------------------------------------------
def generate_checksums(output_dir, platforms_results):
    """Generate SHA256 checksums for all built binaries and save to file."""
    import hashlib
    checksum_file = Path(output_dir) / "sha256sums.txt"
    with open(checksum_file, "w") as f:
        for (goos, goarch), (success, output_file, elapsed) in platforms_results.items():
            if success and output_file.exists():
                sha = hashlib.sha256()
                with open(output_file, "rb") as bf:
                    sha.update(bf.read())
                f.write(f"{sha.hexdigest()}  {output_file.name}\n")
    print_success(f"Checksums saved to {checksum_file}")

def create_archive(output_dir, archive_name=None):
    """Create a .tar.gz archive of the output directory."""
    import tarfile
    if not archive_name:
        archive_name = f"build-{datetime.now().strftime('%Y%m%d-%H%M%S')}.tar.gz"
    archive_path = Path(output_dir).parent / archive_name
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(output_dir, arcname=Path(output_dir).name)
    print_success(f"Archive created: {archive_path}")

# ----------------------------------------------------------------------
def print_stats(results, total_elapsed):
    """Print detailed build statistics."""
    success_results = [(goos, goarch, ok, out_file, elapsed) 
                       for (goos, goarch), (ok, out_file, elapsed) in results.items() 
                       if ok and out_file and out_file.exists()]
    total = len(results)
    success = len(success_results)
    if success == 0:
        print_warning("No successful builds to gather statistics.")
        return

    sizes = [out_file.stat().st_size for _, _, _, out_file, _ in success_results]
    times = [elapsed for _, _, _, _, elapsed in success_results]

    min_size = min(sizes)
    max_size = max(sizes)
    avg_size = sum(sizes) / len(sizes)
    total_size = sum(sizes)

    min_time = min(times)
    max_time = max(times)
    avg_time = sum(times) / len(times)
    sum_time = sum(times)

    # Convert sizes to human-readable units
    def human_size(size):
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

    print_info("\n--- Build Statistics ---", "blue")
    print(f"  Total builds attempted: {total}")
    print(f"  Successful builds:      {success}")
    print(f"  Failed builds:          {total - success}")
    print(f"  Total build time:       {total_elapsed:.1f}s")
    print(f"  Total binary size:      {human_size(total_size)}")
    print(f"  Min binary size:        {human_size(min_size)}")
    print(f"  Max binary size:        {human_size(max_size)}")
    print(f"  Average binary size:    {human_size(avg_size)}")
    print(f"  Min build time:         {min_time:.1f}s")
    print(f"  Max build time:         {max_time:.1f}s")
    print(f"  Average build time:     {avg_time:.1f}s")
    # Median
    sorted_sizes = sorted(sizes)
    sorted_times = sorted(times)
    median_size = sorted_sizes[len(sorted_sizes)//2] if sorted_sizes else 0
    median_time = sorted_times[len(sorted_times)//2] if sorted_times else 0
    print(f"  Median binary size:     {human_size(median_size)}")
    print(f"  Median build time:      {median_time:.1f}s")

# ----------------------------------------------------------------------
def show_docs(lang):
    """Print built-in documentation."""
    if lang == 'ru':
        print(RU_DOC)
    else:
        print(EN_DOC)

# ----------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Universal Go cross-compilation script (fully configurable)",
        epilog="Commands: build (default) or docs [en|ru]. Example: %(prog)s docs ru"
    )
    # Positional arguments for command and language
    parser.add_argument(
        'command',
        nargs='?',
        default='build',
        choices=['build', 'docs'],
        help="Command to run: 'build' (default) or 'docs'"
    )
    parser.add_argument(
        'lang',
        nargs='?',
        default='en',
        help="Language for docs: 'en' or 'ru' (only used with 'docs' command)"
    )

    # Build options
    parser.add_argument(
        "-c", "--config",
        help="Path to JSON configuration file. Settings merged with CLI overrides."
    )
    parser.add_argument(
        "-p", "--project-path",
        help="Path to the Go project (directory containing go.mod)."
    )
    parser.add_argument(
        "-o", "--output-dir",
        help="Output directory for binaries."
    )
    parser.add_argument(
        "-n", "--name-template",
        help="Name template with placeholders: {project}, {os}, {arch}, {version}, {date}, {time}, {commit}"
    )
    parser.add_argument(
        "-pl", "--platforms",
        help="Comma-separated list of platforms (os/arch) or aliases (all, windows, linux, etc.) or wildcards (windows/*, *arm*)."
    )
    parser.add_argument(
        "--exclude",
        help="Comma-separated list of platforms or aliases to exclude."
    )
    parser.add_argument(
        "-v", "--version",
        help="Version string to substitute in name template."
    )
    parser.add_argument(
        "-ld", "--ldflags",
        help="Additional ldflags (e.g. '-X main.version=1.0')"
    )
    parser.add_argument(
        "-tags", "--tags",
        help="Build tags (comma-separated)."
    )
    parser.add_argument(
        "--cgo",
        type=int, choices=[0, 1],
        help="Set CGO_ENABLED (0 or 1)."
    )
    parser.add_argument(
        "--goarm",
        help="Set GOARM (e.g. 7 for armv7)."
    )
    parser.add_argument(
        "--goamd64",
        help="Set GOAMD64 (e.g. v3)."
    )
    parser.add_argument(
        "--go-build-args",
        help="Space-separated flags for 'go build' (e.g. '-trimpath -buildvcs=false -gcflags=all=-l'). Overrides config."
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Remove output directory before building."
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Increase verbosity (equivalent to --log-level=2)."
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress most output (only errors)."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug output (equivalent to --log-level=3)."
    )
    parser.add_argument(
        "--log-level",
        type=int, choices=[0,1,2,3], default=1,
        help="Log level: 0=quiet, 1=normal, 2=verbose, 3=debug."
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Show configuration and ask for confirmation before building."
    )
    parser.add_argument(
        "--save-config",
        metavar="FILE",
        help="Save the effective configuration to a JSON file."
    )
    parser.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colored output."
    )
    parser.add_argument(
        "--jobs",
        type=int,
        help="Number of parallel build jobs (default: number of CPU cores)."
    )
    parser.add_argument(
        "--platform-config",
        help="JSON string or path to file with per-platform overrides (merges with config file)."
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Create a .tar.gz archive of the output directory after build."
    )
    parser.add_argument(
        "--checksum",
        action="store_true",
        help="Generate SHA256 checksums for all built binaries."
    )
    parser.add_argument(
        "--stats",
        action="store_true",
        help="Collect and display detailed build statistics (size, time, etc.)."
    )

    args = parser.parse_args()

    # If 'docs' command is given, show documentation and exit
    if args.command == 'docs':
        show_docs(args.lang)
        sys.exit(0)

    # Otherwise, proceed with build
    # Global color setting
    global USE_COLORS
    if args.no_color:
        USE_COLORS = False

    # Determine log level
    if args.quiet:
        log_level = 0
    elif args.debug:
        log_level = 3
    elif args.verbose:
        log_level = 2
    else:
        log_level = args.log_level

    # Load config from file if provided
    config = DEFAULT_CONFIG.copy()
    if args.config:
        config_path = Path(args.config)
        if not config_path.exists():
            print_error(f"Config file '{config_path}' not found.")
            sys.exit(1)
        with open(config_path, "r", encoding="utf-8") as f:
            file_config = json.load(f)
            config.update(file_config)

    # Load platform-config if provided (could be file or JSON string)
    if args.platform_config:
        pc = args.platform_config
        # Try to parse as JSON, if fails assume it's a file path
        try:
            pc_data = json.loads(pc)
        except json.JSONDecodeError:
            pc_path = Path(pc)
            if pc_path.exists():
                with open(pc_path, "r", encoding="utf-8") as f:
                    pc_data = json.load(f)
            else:
                print_error(f"Platform config file not found: {pc}")
                sys.exit(1)
        config["platform_config"] = pc_data

    # Override with CLI arguments (if provided)
    cli_overrides = {
        "project_path": args.project_path,
        "output_dir": args.output_dir,
        "name_template": args.name_template,
        "platforms": args.platforms,
        "exclude_platforms": args.exclude,
        "version": args.version,
        "ldflags": args.ldflags,
        "tags": args.tags,
        "cgo_enabled": args.cgo,
        "goarm": args.goarm,
        "goamd64": args.goamd64,
        "clean_before_build": args.clean,
        "stats": args.stats,
    }
    for key, value in cli_overrides.items():
        if value is not None:
            config[key] = value

    if args.go_build_args is not None:
        config["go_build_args"] = args.go_build_args.split()

    # If platforms is a string, parse it; if not set, default to "all"
    if "platforms" not in config or not config["platforms"]:
        config["platforms"] = ["all"]
    if isinstance(config["platforms"], str):
        config["platforms"] = [p.strip() for p in config["platforms"].split(",") if p.strip()]

    if isinstance(config["exclude_platforms"], str):
        config["exclude_platforms"] = [p.strip() for p in config["exclude_platforms"].split(",") if p.strip()]

    # Resolve project path
    project_path = Path(config.get("project_path", ".")).resolve()
    if not project_path.exists():
        print_error(f"Project path '{project_path}' does not exist.")
        sys.exit(1)

    output_dir = Path(config["output_dir"]).resolve()

    # Clean output directory if requested
    if config["clean_before_build"] and output_dir.exists():
        if log_level >= 1:
            print_info(f"Cleaning output directory: {output_dir}", "blue")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Resolve platform list
    try:
        platforms = resolve_platforms(config["platforms"], config["exclude_platforms"])
    except Exception as e:
        print_error(f"Error resolving platforms: {e}")
        sys.exit(1)

    if not platforms:
        print_warning("No platforms to build. Exiting.")
        sys.exit(0)

    # Interactive mode
    if args.interactive:
        print_info("\n--- Effective configuration ---", "blue")
        print(json.dumps(config, indent=2, default=str))
        print_info(f"\nPlatforms to build ({len(platforms)}):", "blue")
        for os_, arch in platforms:
            print(f"  {os_}/{arch}")
        response = input("\nProceed with build? (y/N): ").strip().lower()
        if response not in ("y", "yes"):
            print_info("Aborted by user.", "yellow")
            sys.exit(0)

    # Save configuration if requested
    if args.save_config:
        save_path = Path(args.save_config)
        save_path.parent.mkdir(parents=True, exist_ok=True)
        # Convert Path objects to strings
        config_copy = config.copy()
        config_copy["project_path"] = str(project_path)
        config_copy["output_dir"] = str(output_dir)
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(config_copy, f, indent=2, default=str)
        print_success(f"Configuration saved to {save_path}")

    # Build in parallel
    success_count = 0
    total = len(platforms)
    jobs = args.jobs or os.cpu_count() or 4

    if log_level >= 1:
        print_info(f"Building {total} platforms using up to {jobs} parallel jobs...", "blue")
        if log_level >= 2:
            print_info(f"Platforms: {platforms}", "cyan")

    # Progress tracking
    completed = 0
    results = {}  # platform -> (success, output_file, elapsed)
    start_time_total = time.time()

    with ThreadPoolExecutor(max_workers=jobs) as executor:
        future_to_platform = {
            executor.submit(
                build_for_platform,
                project_path,
                output_dir,
                goos,
                goarch,
                config,
                (log_level >= 2),
                log_level
            ): (goos, goarch)
            for goos, goarch in platforms
        }
        for future in as_completed(future_to_platform):
            goos, goarch = future_to_platform[future]
            try:
                ok, out_file, elapsed = future.result()
                results[(goos, goarch)] = (ok, out_file, elapsed)
                if ok:
                    success_count += 1
                completed += 1
                # Update progress bar (simple)
                percent = int(100 * completed / total)
                bar = "#" * int(percent / 2) + "-" * (50 - int(percent / 2))
                sys.stdout.write(f"\r[{bar}] {completed}/{total} ({percent}%)")
                sys.stdout.flush()
            except Exception as e:
                print_error(f"Exception for {goos}/{goarch}: {e}")
                results[(goos, goarch)] = (False, None, 0)
                completed += 1
    sys.stdout.write("\n")  # newline after progress bar

    total_elapsed = time.time() - start_time_total

    # Generate checksums if requested
    if args.checksum:
        generate_checksums(output_dir, results)

    # Create archive if requested
    if args.archive:
        create_archive(output_dir)

    # Summary report
    if log_level >= 1:
        print_info(f"\n--- Build summary (took {total_elapsed:.1f}s) ---", "blue")
        for (goos, goarch), (ok, out_file, elapsed) in results.items():
            status = colorize("✓", "green") if ok else colorize("✗", "red")
            size = f"{out_file.stat().st_size / 1024:.1f} KB" if ok and out_file and out_file.exists() else "N/A"
            print(f"{goos}/{goarch:20} {status}  {size:>12}  {elapsed:.1f}s")

    # Show statistics if requested (either via CLI or config)
    if args.stats or config.get("stats", False):
        print_stats(results, total_elapsed)

    print_success(f"\nBuild complete: {success_count}/{total} succeeded.")
    if success_count < total:
        sys.exit(1)

if __name__ == "__main__":
    main()
