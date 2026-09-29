#!/bin/bash
# Build 3MF-To-AD5X.app for macOS.
#
#   ./build_mac.sh            universal2 (Apple Silicon + Intel) - needs a universal2 Python, see below
#   ./build_mac.sh --native   build for this Mac only (works with any Python, handy for a quick test)
#
# The build is NOT signed or notarised, so the first launch on another Mac needs a right-click > Open
# (or: xattr -dr com.apple.quarantine /path/to/3MF-To-AD5X.app).  See README.md.
set -euo pipefail

cd "$(dirname "$0")"
ROOT="$(pwd -P)"

APP_SLUG="3MF-To-AD5X"          # bundle folder / executable name
APP_NAME="3MF To AD5X"          # what users see in the menu bar and Finder
BUNDLE_ID="com.github.mark.3mf-to-ad5x"
VENV="$ROOT/.venv-build"

die() { printf '\n\033[31merror:\033[0m %s\n\n' "$*" >&2; exit 1; }
step() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }

TARGET="universal2"
for arg in "$@"; do
    case "$arg" in
        --native) TARGET="native" ;;
        -h|--help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
        *) die "unknown option: $arg  (try --native)" ;;
    esac
done

# The Python used to build. Override with PYTHON=/path/to/python3 to build with a specific
# interpreter - handy for a portable universal2 Python that is not on your PATH.
PYTHON="${PYTHON:-python3}"

# ---------------------------------------------------------------- prerequisites
[ "$(uname -s)" = "Darwin" ] || die "this script only builds macOS apps; use build_exe.bat on Windows."

step "Checking tools"
for t in iconutil sips codesign lipo plutil; do
    command -v "$t" >/dev/null 2>&1 || die "'$t' not found. Run:  xcode-select --install"
done
command -v "$PYTHON" >/dev/null 2>&1 || die "'$PYTHON' not found. Pass a real path:  PYTHON=/path/to/python3 $0"
PY_BIN="$(command -v "$PYTHON")"
note "python  : $PY_BIN ($("$PY_BIN" -V 2>&1))"
note "iconutil/sips/codesign/lipo/plutil : ok"

[ -f "$ROOT/ad5x_template.json" ] || die "ad5x_template.json is missing from $ROOT - cannot build."

# Which architectures does a Mach-O file carry?
archs_of() {
    if [ -f "$1" ]; then
        lipo -archs "$1" 2>/dev/null || true
    fi
}
is_universal() {
    # A universal2 binary must carry exactly the x86_64 and arm64 slices. Compare whole
    # arch tokens (sorted, so order doesn't matter) instead of substring matching, which
    # would wrongly accept "arm64e" or an extra third slice.
    local got want
    norm_archs() { tr ' ' '\n' | grep -v '^$' | sort | tr '\n' ' ' | sed 's/  */ /g; s/ $//'; }
    got="$(archs_of "$1" | norm_archs)"
    want="$(printf 'arm64 x86_64' | norm_archs)"
    [ "$got" = "$want" ]
}

# ---------------------------------------------------------------- python + Tk
step "Checking Python / Tk"

if ! "$PY_BIN" -c "import tkinter" >/dev/null 2>&1; then
    die "this Python has no tkinter. Install a python.org build (it bundles Tk)."
fi
TK_SO="$("$PY_BIN" -c 'import _tkinter, os; print(getattr(_tkinter, "__file__", "") or "")')"
TK_VER="$("$PY_BIN" -c 'import tkinter; print(tkinter.TkVersion)')"

# Apple refuses universal2 unless BOTH the interpreter and the Tk it links are fat.
if [ "$TARGET" = "universal2" ]; then
    note "python : $(archs_of "$PY_BIN" || echo '?')"
    note "tkinter: $(archs_of "$TK_SO" || echo '?')  (Tk $TK_VER)"
    if ! is_universal "$PY_BIN" || ! is_universal "$TK_SO"; then
        HINT=""
        case " $(archs_of "$PY_BIN") " in
            *arm64e*) HINT="
    note: it says arm64e, which is a different ABI from the plain arm64 slice a universal2 build needs." ;;
        esac
        cat >&2 <<EOF

$(printf '\033[31m')error:$(printf '\033[0m') this Python is not universal2, so a universal2 .app cannot be built.

    python : $(archs_of "$PY_BIN" || echo unknown)
    tkinter: $(archs_of "$TK_SO" || echo unknown)  (Tk $TK_VER)$HINT

  Fix:  install a universal2 Python from https://www.python.org/downloads/macos/
        (the "macOS 64-bit universal2 installer" - it bundles its own Tcl/Tk 8.6),
        then run:
            /Library/Frameworks/Python.framework/V*/bin/python3 build_mac.sh

        Already have one somewhere off-PATH? Point this script straight at it:
            PYTHON=/path/to/python3 build_mac.sh

  Or build for this Mac only right now:
        ./build_mac.sh --native
EOF
        exit 1
    fi
    note "universal2 python + Tk confirmed - this app will run on Apple Silicon and Intel."
else
    note "native build for $(uname -m); python $(archs_of "$PY_BIN" || echo '?'), Tk $TK_VER"
fi

# ---------------------------------------------------------------- icon -> icns
step "Preparing the icon"
[ -f "$ROOT/assets/appicon.png" ] || die "assets/appicon.png is missing - run:  python3 assets/make_icon.py"
ICNS="$ROOT/assets/appicon.icns"
rm -f "$ICNS"
# iconutil demands every one of these exact names, at these exact pixel sizes.
ICONSET="$(mktemp -d)/appicon.iconset"
trap 'rm -rf "$(dirname "$ICONSET")"' EXIT
mkdir -p "$ICONSET"
while read -r px name; do
    sips -z "$px" "$px" "$ROOT/assets/appicon.png" --out "$ICONSET/$name" >/dev/null
done <<'EOF'
16  icon_16x16.png
32  icon_16x16@2x.png
32  icon_32x32.png
64  icon_32x32@2x.png
128 icon_128x128.png
256 icon_128x128@2x.png
256 icon_256x256.png
512 icon_256x256@2x.png
512 icon_512x512.png
1024 icon_512x512@2x.png
EOF
iconutil -c icns "$ICONSET" -o "$ICNS" || die "iconutil failed to build the .icns"
note "built $(basename "$ICNS") ($(wc -c <"$ICNS" | tr -d ' ') bytes)"

# ---------------------------------------------------------------- pyinstaller
step "Setting up the build environment"
if [ ! -x "$VENV/bin/python" ]; then
    "$PY_BIN" -m venv "$VENV" || die "could not create a virtualenv at $VENV"
fi
VPY="$VENV/bin/python"
"$VPY" -m pip install --quiet --upgrade pip >/dev/null
"$VPY" -c "import PyInstaller" >/dev/null 2>&1 || "$VPY" -m pip install --quiet --upgrade pyinstaller
note "pyinstaller $("$VPY" -m PyInstaller --version 2>/dev/null | tail -1) in $VENV"

EXTRA=()
"$VPY" -c "import tkinterdnd2" >/dev/null 2>&1 && EXTRA+=(--collect-all tkinterdnd2) && note "including drag & drop (tkinterdnd2)"
"$VPY" -c "import PIL.ImageTk" >/dev/null 2>&1 && EXTRA+=(--hidden-import PIL.ImageTk) && note "including Pillow (smooth previews)"

# ---------------------------------------------------------------- build
step "Building $APP_SLUG.app (a minute or two)"
rm -rf "$ROOT/build" "$ROOT/dist" "$ROOT/$APP_SLUG.spec"

set -x
# PyInstaller only accepts x86_64 / arm64 / universal2, and builds for the current
# architecture when the flag is left off entirely.
if [ "$TARGET" = "universal2" ]; then
    ARCH_ARGS=(--target-arch universal2)
else
    ARCH_ARGS=()
fi
"$VPY" -m PyInstaller \
    --noconfirm --clean --windowed --onedir \
    --name "$APP_SLUG" \
    --icon "$ICNS" \
    --osx-bundle-identifier "$BUNDLE_ID" \
    ${ARCH_ARGS[@]+"${ARCH_ARGS[@]}"} \
    --add-data "$ROOT/ad5x_template.json:." \
    ${EXTRA[@]+"${EXTRA[@]}"} \
    "$ROOT/bambu2ad5x_gui.py"
set +x

APP="$ROOT/dist/$APP_SLUG.app"
[ -d "$APP" ] || die "PyInstaller did not produce $APP"

# ---------------------------------------------------------------- Info.plist
step "Finishing the bundle"
PLIST="$APP/Contents/Info.plist"
plist_set() { /usr/libexec/PlistBuddy -c "Set :$1 $2" "$PLIST" 2>/dev/null || /usr/libexec/PlistBuddy -c "Add :$1 string $2" "$PLIST"; }
plist_set "CFBundleName"           "$APP_NAME"
plist_set "CFBundleDisplayName"    "$APP_NAME"
plist_set "CFBundleExecutable"     "$APP_SLUG"
plist_set "CFBundleIdentifier"     "$BUNDLE_ID"
plist_set "CFBundleShortVersionString" "1.0.0"
plist_set "CFBundleVersion"        "1.0.0"
plist_set "CFBundleIconFile"       "appicon"
plist_set "LSApplicationCategoryType" "public.app-category.utilities"
/usr/libexec/PlistBuddy -c "Add :NSHighResolutionCapable bool true"  "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :LSMinimumSystemVersion string 11.0" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :NSRequiresAquaSystemAppearance bool false" "$PLIST" 2>/dev/null || true
plutil -lint "$PLIST" >/dev/null || die "Info.plist is malformed"
# PyInstaller names the icon after the bundle; make sure it is actually there.
[ -f "$APP/Contents/Resources/appicon.icns" ] || cp "$ICNS" "$APP/Contents/Resources/appicon.icns"

# ---------------------------------------------------------------- ad-hoc sign
# Every slice must carry at least an ad-hoc signature or Apple Silicon refuses to run it.
step "Signing (ad-hoc - not a Developer ID)"
codesign --force --deep --sign - --timestamp=none "$APP" 2>&1 | sed 's/^/    /'
codesign --verify --deep --strict "$APP" 2>&1 | sed 's/^/    /' || note "warning: codesign --verify reported a problem"

# ---------------------------------------------------------------- verify
step "Verifying"
EXE="$APP/Contents/MacOS/$APP_SLUG"
[ -x "$EXE" ] || die "no executable at $EXE"
note "executable : $(archs_of "$EXE")"
if [ "$TARGET" = "universal2" ]; then
    is_universal "$EXE" || die "the built executable is not universal2 ($(archs_of "$EXE")) - the build did not do what was asked."
    # The bundled Tcl/Tk must be fat too, or it loads on one Mac and not the other.
    BAD=0
    while IFS= read -r lib; do
        case "$(archs_of "$lib")" in
            *x86_64*arm64*) ;;
            *) note "WARNING: not universal2 -> $(basename "$lib") ($(archs_of "$lib"))"; BAD=1 ;;
        esac
    done < <(find "$APP/Contents/Frameworks" "$APP/Contents/Resources" -type f \( -name '*.dylib' -o -name '*.so' \) 2>/dev/null)
    [ "$BAD" = 0 ] && note "all bundled Tcl/Tk libraries are universal2"
fi
"$VENV/bin/python" - "$APP" <<'PY'
import os, sys
# the template has to travel inside the bundle or the app cannot convert anything
found = []
for root, _, files in os.walk(sys.argv[1]):
    if "ad5x_template.json" in files:
        found.append(os.path.join(root, "ad5x_template.json"))
print("    ad5x_template.json bundled: %s" % (found[0] if found else "MISSING"))
sys.exit(0 if found else 1)
PY

step "Smoke-testing the app"
SELFTEST_OUT="$("$EXE" --selftest 2>&1)" && SELFTEST_RC=0 || SELFTEST_RC=$?
printf '    %s\n' "$SELFTEST_OUT"
[ "$SELFTEST_RC" = 0 ] || die "the packaged app failed its self-test (exit $SELFTEST_RC)"

# also confirm the real GUI stays up, not just that --selftest returns
"$EXE" &
APP_PID=$!
sleep 6
if kill -0 "$APP_PID" 2>/dev/null; then
    kill "$APP_PID" 2>/dev/null || true
    wait "$APP_PID" 2>/dev/null || true
    note "the GUI launched and stayed running."
else
    wait "$APP_PID" 2>/dev/null || true
    die "the GUI exited immediately. Run it from a terminal to see why:  '$EXE'"
fi

# ---------------------------------------------------------------- done
rm -rf "$ROOT/build" "$ROOT/$APP_SLUG.spec"
rm -rf "$VENV"          # keep the repo clean; rebuilds recreate it

cat <<EOF

$(printf '\033[1;32mDone!\033[0m')  $APP

    built for : $TARGET ($(archs_of "$EXE"))
    size      : $(du -sh "$APP" | cut -f1)
    signed    : ad-hoc (unsigned build - see below)

    Test it:      open "$APP"
    Copy it to:   another Mac, then right-click the app > Open > Open.

    If macOS still refuses (Gatekeeper), run:
        xattr -dr com.apple.quarantine "$APP"

    Check it:    codesign --verify --deep --strict "$APP" && lipo -archs "$EXE"

EOF
