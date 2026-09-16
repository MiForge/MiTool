import os
import platform
import shutil
import subprocess
import sys

import usb.backend.libusb1

_MARKER = os.path.expanduser("~/.mitool_deps_ok")
PREFIX = os.environ.get("PREFIX", "/data/data/com.termux/files/usr")


def _is_termux():
    return os.path.exists("/data/data/com.termux")


PKGS = {
    "apt-get": "libusb-1.0-0",
    "dnf": "libusb1",
    "yum": "libusb1",
    "pacman": "libusb",
    "zypper": "libusb-1_0-0",
}

UDEV_PATH = "/etc/udev/rules.d/51-mitool.rules"
UDEV_RULES = (
    'SUBSYSTEM=="usb", ATTR{idVendor}=="2717", MODE="0666", GROUP="plugdev"\n'
    'SUBSYSTEM=="usb", ATTR{idVendor}=="05c6", MODE="0666", GROUP="plugdev"\n'
    'SUBSYSTEM=="usb", ATTR{idVendor}=="18d1", MODE="0666", GROUP="plugdev"\n'
)


def _run(cmd):
    if not shutil.which(cmd[0]):
        return False
    print(f"Installing missing dependency: {' '.join(cmd)}")
    subprocess.run(cmd)
    return True


def _termux_api_app_installed():
    result = subprocess.run(
        ["cmd", "package", "list", "packages", "--user", "0", "com.termux.api"],
        capture_output=True,
        text=True,
    )
    return "package:com.termux.api" in result.stdout


def _ensure_termux():
    ok = True

    if not _termux_api_app_installed():
        print(
            "Termux:API app is not installed.\n"
            "Download it from https://github.com/termux/termux-api/releases/latest and rerun."
        )
        ok = False

    lib_path = f"{PREFIX}/lib/libusb-1.0.so"
    if not os.path.exists(lib_path):
        _run(["pkg", "install", "-y", "libusb"])
        if not os.path.exists(lib_path):
            print("Could not install libusb. Try manually: pkg install libusb")
            ok = False

    if not shutil.which("termux-usb"):
        _run(["pkg", "install", "-y", "termux-api"])
        if not shutil.which("termux-usb"):
            print("Could not install termux-api. Try manually: pkg install termux-api")
            ok = False

    return ok


def _windows_backend():
    try:
        import libusb_package
        return usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
    except ImportError:
        return None


def _ensure_windows():
    if _windows_backend() is not None:
        return True

    print("libusb backend unavailable, attempting to reinstall libusb_package...")
    subprocess.run([sys.executable, "-m", "pip", "install", "--force-reinstall", "-q", "libusb_package"])

    if _windows_backend() is None:
        print("Still unavailable. Try manually: pip install --force-reinstall libusb_package, then restart mitool.")
        return False
    return True


def _install_libusb_unix():
    if platform.system() == "Darwin":
        if not shutil.which("brew"):
            print("Homebrew not found. Install libusb manually: brew install libusb")
            return False
        return _run(["brew", "install", "libusb"])

    for mgr, pkg in PKGS.items():
        if not shutil.which(mgr):
            continue
        cmd = [mgr, "-S", "--noconfirm", pkg] if mgr == "pacman" else [mgr, "install", "-y", pkg]
        if os.geteuid() != 0:
            if not shutil.which("sudo"):
                print(f"Need root to install {pkg}. Try manually: sudo {' '.join(cmd)}")
                return False
            cmd = ["sudo"] + cmd
        return _run(cmd)

    print("No supported package manager found. Install libusb manually for your distro.")
    return False


def _ensure_udev():
    if platform.system() != "Linux" or _is_termux():
        return
    if os.geteuid() != 0 and not shutil.which("sudo"):
        return

    try:
        if open(UDEV_PATH).read() == UDEV_RULES:
            return
    except OSError:
        pass

    prefix = [] if os.geteuid() == 0 else ["sudo"]
    print("Writing udev rules ->", UDEV_PATH)
    p = subprocess.Popen(prefix + ["tee", UDEV_PATH], stdin=subprocess.PIPE, text=True, stdout=subprocess.DEVNULL)
    p.communicate(UDEV_RULES)
    subprocess.run(prefix + ["udevadm", "control", "--reload-rules"])
    subprocess.run(prefix + ["udevadm", "trigger"])


def _ensure_unix():
    if not usb.backend.libusb1.get_backend():
        if not _install_libusb_unix():
            return False
        if not usb.backend.libusb1.get_backend():
            print("Installed but still not detected. Try manually and rerun mitool.")
            return False

    _ensure_udev()
    return True


def ensure_deps():
    if os.path.exists(_MARKER):
        return

    if platform.system() == "Windows":
        ok = _ensure_windows()
    elif _is_termux():
        ok = _ensure_termux()
    else:
        ok = _ensure_unix()

    if ok:
        open(_MARKER, "w").close()
