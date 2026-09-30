#!/usr/bin/env bash
set -euo pipefail

readonly ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
# Derive the home from the account we are running as, so no literal username is
# baked into paths. Every step here is optional: $USER is not always exported
# (cron, containers, some login managers) and `getent` is missing on musl and
# minimal images - where `set -e` would otherwise abort with no message at all.
USER_HOME="${ER_USER_HOME:-}"
if [[ -z "$USER_HOME" ]]; then
    account="${USER:-$(id -un 2>/dev/null || true)}"
    USER_HOME="$(getent passwd "$account" 2>/dev/null | cut -d: -f6 || true)"
fi
: "${USER_HOME:=$HOME}"
readonly USER_HOME
readonly STEAM_ROOT="${ER_STEAM_ROOT:-$USER_HOME/.steam/steam}"
readonly GAME_DIR="${ER_GAME_DIR:-$STEAM_ROOT/steamapps/common/ELDEN RING/Game}"
# Playing a loose-file mod such as Elden Ring Reforged? Point ER_MOD_DIR at the
# folder holding its regulation.bin. There is no reliable place to guess from -
# mods get unpacked wherever you keep them - so this is not auto-detected.
readonly MOD_DIR="${ER_MOD_DIR:-}"
readonly NATIVE_DIR="$ROOT/cache/native-oodle"
readonly SOURCE_DIR="$NATIVE_DIR/source"
readonly BUILD_DIR="$NATIVE_DIR/build"
readonly VENV_DIR="$ROOT/cache/python"
readonly PYTHON="$VENV_DIR/bin/python"
readonly LIB="$BUILD_DIR/liblinoodle.so"
readonly LINOODLE_COMMIT=90b8d825f7f89272f03f52b5d1db4708e07eb83f

# Package name per distro for each command we need, so a missing dependency can
# print the exact line to paste rather than just its own name.
#   command | debian/ubuntu | fedora/rhel | arch | opensuse
readonly PACKAGES="
git|git|git|git|git
cmake|cmake|cmake|cmake|cmake
cc|build-essential|gcc-c++|base-devel|gcc-c++
node|nodejs|nodejs|nodejs|nodejs18
python3|python3|python3|python|python3
venv|python3-venv|python3|python|python3
"

# -> the install command for this machine, or empty if the distro is unknown.
install_hint() {
    local command_name="$1" row field=0
    row="$(printf '%s\n' "$PACKAGES" | grep "^$command_name|" || true)"
    [[ -n "$row" ]] || return 0
    if command -v apt-get >/dev/null; then
        field=2; printf 'sudo apt install '
    elif command -v dnf >/dev/null; then
        field=3; printf 'sudo dnf install '
    elif command -v pacman >/dev/null; then
        field=4; printf 'sudo pacman -S '
    elif command -v zypper >/dev/null; then
        field=5; printf 'sudo zypper install '
    else
        return 0
    fi
    printf '%s\n' "$row" | cut -d'|' -f"$field"
}

missing=()

need_command() {
    local command_name="$1" probe="${2:-$1}"
    command -v "$probe" >/dev/null || missing+=("$command_name")
}

report_missing() {
    ((${#missing[@]})) || return 0
    printf '\n缺少依赖 / Missing dependencies: %s\n\n' "${missing[*]}" >&2
    local command_name hint
    for command_name in "${missing[@]}"; do
        hint="$(install_hint "$command_name")"
        if [[ -n "$hint" ]]; then
            printf '  %-10s %s\n' "$command_name" "$hint" >&2
        else
            printf '  %-10s (请用你的包管理器安装 / install it with your package manager)\n' "$command_name" >&2
        fi
    done
    printf '\nNode.js 18+ 也可从 https://nodejs.org 获取 / Node.js 18+ is also available from https://nodejs.org\n' >&2
    exit 1
}

check_host() {
    need_command git
    need_command cmake
    need_command python3
    need_command node
    # Either compiler will build the Oodle shim; clang is only preferred.
    if ! command -v clang >/dev/null && ! command -v cc >/dev/null && \
       ! command -v gcc >/dev/null; then
        missing+=(cc)
    fi
    # A venv is only needed when uv is absent - uv brings its own.
    if ! command -v uv >/dev/null; then
        python3 -c 'import venv, ensurepip' 2>/dev/null || missing+=(venv)
    fi
    report_missing

    # Versions, once we know the commands exist at all.
    python3 - <<'PY' || exit 1
import sys
if sys.version_info < (3, 9):
    sys.exit(f"需要 Python 3.9 或更高版本，当前为 / Python 3.9 or newer is required; this is {sys.version.split()[0]}")
PY
    local node_major
    node_major="$(node -p 'process.versions.node.split(".")[0]' 2>/dev/null || echo 0)"
    if (( node_major < 18 )); then
        printf '需要 Node.js 18 或更高版本，当前为 / Node.js 18 or newer is required; this is %s\n' \
            "$(node --version 2>/dev/null || echo 'not runnable')" >&2
        printf '请从 https://nodejs.org 或你的包管理器安装 / Get it from https://nodejs.org or your package manager.\n' >&2
        exit 1
    fi

    test -r "$GAME_DIR/eldenring.exe" || {
        printf '未在此处找到艾尔登法环 / Elden Ring was not found at: %s\n' "$GAME_DIR" >&2
        exit 1
    }
    test -r "$GAME_DIR/regulation.bin" || {
        printf '未找到 regulation.bin / regulation.bin was not found at: %s\n' "$GAME_DIR" >&2
        exit 1
    }
    test -r "$GAME_DIR/oo2core_6_win64.dll" || {
        printf '未找到游戏的 Oodle DLL / The game Oodle DLL was not found at: %s\n' "$GAME_DIR" >&2
        exit 1
    }
    if [[ -n "$MOD_DIR" && ! -r "$MOD_DIR/regulation.bin" ]]; then
        printf '未找到 ERR 模组文件 / ERR mod files were not found at: %s\n' "$MOD_DIR" >&2
        exit 1
    fi
}

display_path() {
    local p="$1"
    printf '%s' "${p/#"$USER_HOME"/\~}"
}

if [[ "${1:-}" == "--check" ]]; then
    check_host
    printf '游戏 / Game: %s\n' "$(display_path "$GAME_DIR")"
    printf '模组文件 / Mod files: %s\n' "$(display_path "${MOD_DIR:-none}")"
    printf '原生 Oodle / Native Oodle: %s\n' "$(display_path "$LIB")"
    exit 0
fi

check_host

if [[ ! -d "$SOURCE_DIR/.git" ]]; then
    mkdir -p "$NATIVE_DIR"
    git clone --quiet --recurse-submodules https://github.com/McSimp/linoodle.git "$SOURCE_DIR"
fi
git -C "$SOURCE_DIR" checkout --quiet "$LINOODLE_COMMIT"
git -C "$SOURCE_DIR" submodule update --init --recursive --quiet

if [[ ! -f "$LIB" ]]; then
    # clang is what linoodle is developed against, but gcc builds it fine.
    if command -v clang >/dev/null && command -v clang++ >/dev/null; then
        compilers=(-DCMAKE_C_COMPILER=clang -DCMAKE_CXX_COMPILER=clang++)
    else
        printf '未找到 clang，改用 gcc 构建 Oodle 兼容层 / clang not found, building the Oodle shim with gcc.\n'
        compilers=(-DCMAKE_C_COMPILER=gcc -DCMAKE_CXX_COMPILER=g++)
    fi
    jobs="$(nproc 2>/dev/null || getconf _NPROCESSORS_ONLN 2>/dev/null || echo 2)"
    cmake -S "$SOURCE_DIR" -B "$BUILD_DIR" \
        -DCMAKE_BUILD_TYPE=Release \
        "${compilers[@]}" \
        '-DCMAKE_CXX_FLAGS=-include cstdint -include utility -Wno-error'
    cmake --build "$BUILD_DIR" --target linoodle -j"$jobs"
fi

mkdir -p "$NATIVE_DIR/runtime"
ln -sfn "$GAME_DIR/oo2core_6_win64.dll" \
    "$NATIVE_DIR/runtime/oo2core_8_win64.dll"

# uv is much faster, but it is a niche tool to demand - fall back to the stdlib
# venv module, which every supported Python already has.
printf '\n正在安装 Python 依赖包 / Installing Python packages...\n'
if command -v uv >/dev/null; then
    uv venv --quiet --allow-existing "$VENV_DIR"
    uv pip install --quiet --python "$PYTHON" \
        zstandard pycryptodome pillow texture2ddecoder numpy
else
    [[ -x "$PYTHON" ]] || python3 -m venv "$VENV_DIR"
    "$PYTHON" -m pip install --quiet --upgrade pip
    "$PYTHON" -m pip install --quiet \
        zstandard pycryptodome pillow texture2ddecoder numpy
fi

export ER_GAME_DIR="$GAME_DIR"
export ER_MOD_DIR="$MOD_DIR"
export ER_LINOODLE="$LIB"
cd "$NATIVE_DIR/runtime"

printf '\n[1/8] 正在获取社区格式文档（paramdefs 等）/ Fetching the community format documents...\n'
# paramdefs 与 eventflag/MFG 表是社区整理的格式文档，不是游戏文件，所以没有随
# 本仓库分发。读取任何 param 之前必须先有它们。
# The paramdefs (and the event-flag and MFG tables) are community format documents
# rather than game files, so they are not shipped in this repository; nothing can
# read the params until they are here.
"$PYTHON" "$ROOT/tools/fetch_docs.py"
printf '\n[2/8] 正在提取基础地图底图（瓦片）/ Extracting base map tiles...\n'
"$PYTHON" "$ROOT/tools/extract_tiles.py" --game-dir "$GAME_DIR"
printf '\n[3/8] 正在生成标记数据 / Building marker data...\n'
"$PYTHON" "$ROOT/tools/build_markers.py" "$GAME_DIR"
printf '\n[4/8] 正在索引地图文件 / Indexing map files...\n'
"$PYTHON" "$ROOT/tools/dev/enumerate_maps.py"
printf '\n[5/8] 正在提取道具位置、商人与角色掉落 / Extracting item locations, merchants and one-time drops...\n'
"$PYTHON" "$ROOT/tools/extract_items.py" --game-dir "$GAME_DIR" --mod-dir "$MOD_DIR"
printf '\n[6/8] 正在提取地图图标 / Extracting map icons...\n'
"$PYTHON" "$ROOT/tools/extract_icons.py" --game-dir "$GAME_DIR" --mod-dir "$MOD_DIR"
# Rune and Ember Pieces are Reforged collectibles - an unmodded game has none,
# so this only runs with a mod directory set.
if [[ -n "$MOD_DIR" ]]; then
    printf '\n[7/8] 正在提取 Reforged 卢恩/余烬碎片 / Extracting Reforged rune/ember pieces...\n'
    "$PYTHON" "$ROOT/tools/extract_pieces.py" --game-dir "$GAME_DIR" --mod-dir "$MOD_DIR"
else
    printf '\n[7/8] 已跳过 Reforged 卢恩/余烬碎片，未设置 ER_MOD_DIR / skipped - ER_MOD_DIR not set\n'
fi

# Everything above came out of your own copy of the game. This step is the one
# exception, so it asks before it runs. Set ER_TIPS=yes/no to answer in advance
# and keep setup unattended.
tips="${ER_TIPS:-}"
if [[ -z "$tips" ]]; then
    printf '\n[8/8] 路线说明（可选） / Route descriptions (optional)\n\n'
    printf '  你的标记现在已经能说明"这是什么"和"它有多高"，但说明不了\n'
    printf '  "怎么过去"——路线不在游戏文件里，那是别人写的内容。\n'
    printf '  Fextralife wiki 的互动地图为它的大多数标记写了路线，这一步会\n'
    printf '  抓取这些文字并附加到你的约 2,000 个标记上。\n\n'
    printf '  Your markers can now say what a thing is and how high up it is.\n'
    printf '  What they cannot say is how to get to it - that is not in the\n'
    printf '  game files, it is something people write. The Fextralife wiki\n'
    printf '  interactive map has a written route for most of its markers, and\n'
    printf '  this attaches them to about 2,000 of yours.\n\n'
    printf '  那些文字属于他们——既不属于你，也不属于游戏——他们的条款要求\n'
    printf '  不得自动抓取。它只保存在这台电脑上供你自己使用：请勿转载，\n'
    printf '  也不要随本工具一起分发。没有它地图依然是完整的。\n\n'
    printf '  That text is theirs - not yours, and not the game files - and\n'
    printf '  their terms ask that it is not fetched automatically. It stays on\n'
    printf '  this PC for your own use: do not republish it or ship it with a\n'
    printf '  copy of this tool. The map is complete without it.\n\n'
    read -r -p '  抓取路线说明吗？/ Fetch them? [y/N] ' tips </dev/tty || tips=n
fi
if [[ "$tips" =~ ^[Yy] ]]; then
    printf '\n正在抓取路线说明 / Fetching route descriptions...\n'
    # Non-fatal on purpose: no internet, or a changed wiki, must not fail a
    # setup whose real work is already done.
    "$PYTHON" "$ROOT/tools/fetch_tips.py" ||
        printf '\n  抓取失败。其他内容都已生成、地图可正常使用，只是标记不会有\n  "如何抵达"的文字。 / Could not fetch them. Everything else is built; markers will\n  just have no "how to get there" text.\n'
else
    printf '\n[8/8] 已跳过路线说明 / Route descriptions - skipped\n'
fi

printf '\n安装完成。运行 ./start-map.sh 打开实时地图。\nSetup complete. Run ./start-map.sh to open the live map.\n'
