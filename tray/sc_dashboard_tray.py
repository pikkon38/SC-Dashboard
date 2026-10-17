"""SC Dashboard for Windows: runs the companion in the background with a system tray icon,
and keeps itself up to date from GitHub Releases."""
import argparse
import ctypes
import json
import os
import subprocess
import sys
import threading
import time
import webbrowser

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "companion"))  # running from source

import sc_companion as comp  # noqa: E402
import updater  # noqa: E402

APP = "SC Dashboard"
SETTINGS_PATH = os.path.join(comp.DATA_DIR, "tray.json")
LOG_PATH = os.path.join(comp.DATA_DIR, "companion.log")
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
CHECK_EVERY = 6 * 3600


def message(text, error=False):
    if comp.IS_WINDOWS:
        ctypes.windll.user32.MessageBoxW(None, text, APP, 0x10 if error else 0x40)
    else:
        print(text)


def log_to_file():
    """A windowed app has no console, so everything printed goes to companion.log."""
    os.makedirs(comp.DATA_DIR, exist_ok=True)
    if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 2_000_000:
        os.replace(LOG_PATH, LOG_PATH + ".old")
    f = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    f.write(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} ---\n")
    sys.stdout = sys.stderr = f


def single_instance():
    if not comp.IS_WINDOWS:
        return True
    ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\SCDashboardTray")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


class Settings(dict):
    def __init__(self):
        super().__init__(auto_update=True)
        try:
            with open(SETTINGS_PATH, encoding="utf-8") as f:
                self.update(json.load(f))
        except (OSError, ValueError):
            pass

    def save(self):
        with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
            json.dump(self, f, indent=2)


def startup_enabled():
    if not comp.IS_WINDOWS:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, APP)
            return True
    except OSError:
        return False


def set_startup(on):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, APP, 0, winreg.REG_SZ, f'"{sys.executable}"')
        else:
            try:
                winreg.DeleteValue(k, APP)
            except OSError:
                pass


def open_path(path):
    if comp.IS_WINDOWS:
        os.startfile(path)


class TrayApp:
    def __init__(self, args):
        self.args = args
        self.settings = Settings()
        self.update = None      # newest release, when newer than this one
        self.status = ""        # shown in the menu while checking / updating
        self.icon = None
        self.server = None
        self.url = ""

    # ---- companion -------------------------------------------------------
    def start_server(self):
        try:
            self.server, self.url = comp.start(self.args.port, self.args.pin, self.args.dry_run, self.args.log)
        except OSError as e:
            message(f"Couldn't start on port {self.args.port}. Is another copy of the dashboard "
                    f"(or the old .bat version) still running?\n\n{e}", error=True)
            return False
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        return True

    # ---- updates ---------------------------------------------------------
    def check(self, manual=False, at_start=False):
        self.status = "Checking for updates…"
        self.refresh()
        try:
            self.update = updater.newer_than(comp.VERSION)
        except Exception as e:
            print("  update check failed:", e)
            self.status = ""
            self.refresh()
            if manual:
                self.notify("Couldn't reach GitHub to check for updates.")
            return
        self.status = ""
        self.refresh()
        if not self.update:
            if manual:
                self.notify(f"You're up to date (version {comp.VERSION}).")
            return
        print(f"  update available: {self.update['version']}")
        if at_start and self.settings["auto_update"]:
            self.install()
        else:
            self.notify(f"Version {self.update['version']} is available. "
                        "Right-click the tray icon and choose Update.")

    def install(self):
        rel = self.update
        if not rel:
            return
        self.status = f"Downloading version {rel['version']}…"
        self.refresh()
        self.notify(f"Updating to version {rel['version']}. The dashboard will be back in a few seconds.")
        try:
            path = updater.download(rel)
        except Exception as e:
            print("  update download failed:", e)
            self.status = ""
            self.refresh()
            self.notify("The update couldn't be downloaded. It will try again next time.")
            return
        updater.run_installer(path)
        self.quit()

    def check_loop(self):
        self.check(at_start=True)
        while True:
            time.sleep(CHECK_EVERY)
            self.check()

    # ---- tray ------------------------------------------------------------
    def notify(self, text):
        print("  " + text)
        try:
            if self.icon:
                self.icon.notify(text, APP)
        except Exception:
            pass

    def refresh(self):
        if self.icon:
            self.icon.update_menu()

    def copy_url(self):
        subprocess.run("clip", input=self.url.encode("utf-16-le"), check=False,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        self.notify(f"Copied {self.url}. Open it in Safari on your iPad.")

    def toggle_auto(self):
        self.settings["auto_update"] = not self.settings["auto_update"]
        self.settings.save()

    def quit(self):
        if self.server:
            threading.Thread(target=self.server.shutdown, daemon=True).start()
        if self.icon:
            self.icon.stop()

    def menu(self):
        from pystray import Menu, MenuItem as Item
        return Menu(
            Item(lambda _: f"{APP} {comp.VERSION}", None, enabled=False),
            Item(lambda _: f"iPad address: {self.url}", lambda: self.copy_url(), default=True),
            Item("Open dashboard on this PC", lambda: webbrowser.open(self.url)),
            Menu.SEPARATOR,
            Item(lambda _: self.status, None, enabled=False, visible=lambda _: bool(self.status)),
            Item(lambda _: f"Update to version {self.update['version']}" if self.update else "",
                 lambda: threading.Thread(target=self.install, daemon=True).start(),
                 visible=lambda _: bool(self.update) and not self.status),
            Item("Check for updates", lambda: threading.Thread(target=self.check, kwargs={"manual": True},
                                                                daemon=True).start()),
            Item("Install updates when it starts", lambda: self.toggle_auto(),
                 checked=lambda _: self.settings["auto_update"]),
            Item("Start with Windows", lambda: set_startup(not startup_enabled()),
                 checked=lambda _: startup_enabled(), visible=comp.IS_WINDOWS),
            Menu.SEPARATOR,
            Item("Open log", lambda: open_path(LOG_PATH)),
            Item("Open settings folder", lambda: open_path(comp.DATA_DIR)),
            Menu.SEPARATOR,
            Item("Quit", lambda: self.quit()),
        )

    def run(self):
        import pystray
        from icon import draw
        if not self.start_server():
            return
        self.icon = pystray.Icon("sc-dashboard", draw(64), f"{APP} {comp.VERSION}\n{self.url}", self.menu())

        def ready(icon):
            icon.visible = True
            self.notify(f"Running. On your iPad open {self.url}")
            if not self.args.no_update:
                threading.Thread(target=self.check_loop, daemon=True).start()

        self.icon.run(setup=ready)


def main():
    ap = argparse.ArgumentParser(description=APP)
    ap.add_argument("--port", type=int, default=8770)
    ap.add_argument("--pin", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--log", default="", help="path to Star Citizen's Game.log")
    ap.add_argument("--no-update", action="store_true", help="don't check GitHub for updates")
    args = ap.parse_args()
    if getattr(sys, "frozen", False) or sys.stdout is None:
        log_to_file()
    if not single_instance():
        message("SC Dashboard is already running. Look for its icon in the system tray.")
        return
    TrayApp(args).run()


if __name__ == "__main__":
    main()
