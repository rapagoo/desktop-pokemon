"""Windows 화면 관련 기능: 화면 공유·녹화에서 창 빼기, 전체 화면 앱 감지, 전역 단축키.

Windows가 아니거나 API가 없으면 조용히 아무것도 하지 않는다.
"""
import ctypes
import queue
import sys
import threading
from ctypes import wintypes

WDA_EXCLUDEFROMCAPTURE = 0x11      # Windows 10 2004 이상: 캡처에서 빠지고 내 화면엔 보임
GA_ROOT = 2
MONITOR_DEFAULTTONEAREST = 2
MONITORINFOF_PRIMARY = 1
# 바탕화면·작업표시줄은 화면을 꽉 채워도 전체 화면 앱이 아님
SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}

try:
    user32 = ctypes.windll.user32
except AttributeError:             # Windows가 아님
    user32 = None


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def hwnd_of(tk_window):
    """Tk 창의 최상위 Windows 핸들."""
    if not user32:
        return None
    return user32.GetAncestor(tk_window.winfo_id(), GA_ROOT)


def exclude_from_capture(tk_window):
    """화면 공유·녹화·스크린샷에 이 창이 찍히지 않게 한다. 성공하면 True."""
    hwnd = hwnd_of(tk_window)
    if not hwnd:
        return False
    try:
        return bool(user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE))
    except Exception:
        return False


def fullscreen_app_active(own_hwnds=()):
    """주 모니터를 꽉 채운 다른 앱(영상, 발표, 게임 등)이 앞에 있으면 True."""
    if not user32:
        return False
    try:
        fg = user32.GetForegroundWindow()
        if not fg or fg in own_hwnds:
            return False
        cls = ctypes.create_unicode_buffer(256)
        user32.GetClassNameW(fg, cls, 256)
        if cls.value in SHELL_CLASSES:
            return False
        rect = wintypes.RECT()
        user32.GetWindowRect(fg, ctypes.byref(rect))
        info = MONITORINFO(cbSize=ctypes.sizeof(MONITORINFO))
        mon = user32.MonitorFromWindow(fg, MONITOR_DEFAULTTONEAREST)
        if not user32.GetMonitorInfoW(mon, ctypes.byref(info)):
            return False
        if not info.dwFlags & MONITORINFOF_PRIMARY:     # 포켓몬은 주 모니터에만 산다
            return False
        m = info.rcMonitor
        return (rect.left <= m.left and rect.top <= m.top
                and rect.right >= m.right and rect.bottom >= m.bottom)
    except Exception:
        return False


MOD_KEYS = {"alt": 0x1, "ctrl": 0x2, "shift": 0x4, "win": 0x8}
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312


def start_hotkey(hotkey):
    """전역 단축키 등록. 눌릴 때마다 돌려준 큐에 값이 들어간다 (메인 루프에서 꺼내 씀).

    RegisterHotKey는 등록한 스레드의 메시지 큐로 알림을 보내므로, Tk와 섞이지 않게
    전용 스레드에서 등록하고 메시지를 기다린다.
    """
    events = queue.Queue()
    if not user32:
        return events
    mods, key = hotkey
    flags = MOD_NOREPEAT
    for m in mods.split("+"):
        flags |= MOD_KEYS[m.strip().lower()]
    vk = ord(key.upper())

    def run():
        if not user32.RegisterHotKey(None, 1, flags, vk):
            print(f"단축키 {mods}+{key} 등록 실패 (다른 프로그램이 쓰는 중일 수 있음)", file=sys.stderr)
            return
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            if msg.message == WM_HOTKEY:
                events.put(True)

    threading.Thread(target=run, daemon=True).start()
    return events
