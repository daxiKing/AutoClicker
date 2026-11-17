"""AutoClicker launcher — splash, application bootstrap and clean shutdown."""

from __future__ import annotations

import ctypes
import sys
import traceback
from datetime import datetime
from pathlib import Path

# Make the package importable when the shortcut is launched from elsewhere.
BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

from novaclick import __app_name__, __version__
from novaclick.core import wininput
from novaclick.core.paths import DATA_DIR
from novaclick.ui.splash import SplashScreen
from novaclick.ui.theme import apply_theme
from novaclick.ui.widgets import make_app_icon
from novaclick.ui.window import MainWindow

ERROR_LOG = DATA_DIR / "errors.log"
_MUTEX_HANDLE = None


def _install_error_log() -> None:
    def hook(kind, value, tb) -> None:
        text = "".join(traceback.format_exception(kind, value, tb))
        try:
            with ERROR_LOG.open("a", encoding="utf-8") as handle:
                handle.write(f"\n[{datetime.now().isoformat(timespec='seconds')}]\n{text}")
        except OSError:
            pass
        try:
            sys.stderr.write(text)
        except Exception:
            pass

    sys.excepthook = hook


def _claim_single_instance() -> bool:
    """Return False when another AutoClicker process already owns the mutex."""
    global _MUTEX_HANDLE
    if not sys.platform.startswith("win"):
        # Linux launches are guarded by the session manager; the Windows mutex
        # is not available there.
        return True
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW.argtypes = (
            ctypes.c_void_p,
            ctypes.c_int,
            ctypes.c_wchar_p,
        )
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        _MUTEX_HANDLE = kernel32.CreateMutexW(None, False, "AutoClicker.Singleton.1")
        if kernel32.GetLastError() == 183:  # ERROR_ALREADY_EXISTS
            ctypes.windll.user32.MessageBoxW(
                0,
                "AutoClicker is already running.\n\n"
                "Use the existing window, or close it before launching another copy.",
                "AutoClicker",
                0x00000040,  # MB_ICONINFORMATION
            )
            return False
    except Exception:
        # If the mutex API is unavailable, do not block the app.
        pass
    return True


def main() -> int:
    _install_error_log()

    # Physical-pixel coordinates must match SendInput targeting.
    wininput.enable_dpi_awareness()
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "AutoClicker.Automation.1"
        )
    except Exception:
        pass

    if not _claim_single_instance():
        return 0

    try:
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
        )
    except Exception:
        pass

    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setOrganizationName("AutoClicker")
    app.setApplicationVersion(__version__)
    app.setWindowIcon(make_app_icon())
    apply_theme(app)
    app.setQuitOnLastWindowClosed(True)

    wininput.begin_timer_resolution()

    holder: dict[str, object] = {"window": None, "reveal": None}

    def cleanup() -> None:
        window = holder.get("window")
        if window is not None:
            try:
                window.shutdown()
            except Exception:
                traceback.print_exc()
        try:
            wininput.end_timer_resolution()
        except Exception:
            pass

    app.aboutToQuit.connect(cleanup)

    splash = SplashScreen()
    splash.show()
    splash.raise_()

    def boot() -> None:
        try:
            window = MainWindow()
        except Exception as exc:
            traceback.print_exc()
            splash.close()
            QMessageBox.critical(
                None,
                "AutoClicker could not start",
                "The interface failed to initialize.\n\n"
                f"{type(exc).__name__}: {exc}\n\n"
                f"Details were written to:\n{ERROR_LOG}",
            )
            app.quit()
            return

        holder["window"] = window
        window.setWindowOpacity(1.0)

        def reveal() -> None:
            window.show_initial()
            window.start_services()
            splash.fade_out()

        splash.finished.connect(reveal)
        splash.mark_ready()

    QTimer.singleShot(90, boot)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
