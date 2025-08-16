#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import os, platform, shutil, subprocess, threading, base64, io, tkinter as tk
from tkinter import messagebox, Toplevel

# ========== 你可以改的配置 ==========
END_GIF_PATH   = "timer Lee.gif"   # 结束时弹出的 GIF（文件名可带空格）
END_AUDIO_PATH = "alert.mp3"       # 结束时播放的音频（.mp3/.wav），没有则回退一次蜂鸣

# 结束弹窗 GIF 的缩放策略（两种方式，任选其一）：
SCALE = None        # 手动比例：None 表示不用手动；整数>=1表示缩小为 1/SCALE；小数<1 表示“放大”(例如 0.5=放大2倍)
MAX_GIF_SIZE = 500  # 自动目标尺寸：最长边尽量接近这个像素（SCALE 为 None 时生效；<=0 则关闭自动）
ANIM_INTERVAL_MS = 100  # GIF 播放间隔

# 页眉内嵌熊猫 GIF（占位，可换成你自己的 base64）
PANDA_GIF_B64 = """
R0lGODlhIAAgAKECAAAAAP///wAAAMLCwgAAACH5BAEKAAIALAAAAAAgACAAAALheLrc/jDKSau9OOvNu/9gKI5kaZ5oqq5s674vq9wFADs=
"""

# 托盘图标（16x16 PNG 占位，可选）
TRAY_ICON_PNG_B64 = """
iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAMAAAAoLQ9TAAAAXVBMVEUAAAD/////////////////////////////////////////////////////////////
///////////////////////////8AAABlPj8mAAAAGnRSTlMAAQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRs9X7mPAAAAQElEQVQY02NgQAZGJmBkYGBg
YJgBAMaBExgYpIhEwQEGwYQmQGAAkQbCkQZBgQjB8DgkQwEGgY1gQkGgYwYF0gJgZkGAAAPwQm3w5qf2sAAAAASUVORK5CYII=
"""

# ---------- 最兜底蜂鸣 ----------
def _beep_fallback():
    try:
        if platform.system() == "Windows":
            import winsound
            winsound.Beep(1000, 300)
        else:
            print('\a', end='', flush=True)
    except Exception:
        pass

# ---------- 可停止的跨平台音频控制器 ----------
class AudioController:
    """
    macOS:  afplay 进程（可终止）
    Linux:  paplay/aplay/ffplay 三选一（可终止）
    Windows: winsound.PlaySound(..., SND_ASYNC)；stop 用 PlaySound(None,0) 停止
    都不可用或文件缺失：退回一次性蜂鸣
    """
    def __init__(self, path):
        self.path = path
        self.proc = None
        self.backend = None   # 'proc' | 'winsound' | 'beep' | None

    def play(self):
        self.stop()
        if not self.path or not os.path.exists(self.path):
            self.backend = 'beep'
            _beep_fallback()
            return
        sysname = platform.system()
        try:
            if sysname == "Darwin":  # macOS
                self.proc = subprocess.Popen(
                    ["afplay", self.path],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
                self.backend = 'proc'
            elif sysname == "Linux":
                player = shutil.which("paplay") or shutil.which("aplay") or shutil.which("ffplay")
                if player:
                    if os.path.basename(player) == "ffplay":
                        self.proc = subprocess.Popen(
                            [player, "-nodisp", "-autoexit", self.path],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                        )
                    else:
                        self.proc = subprocess.Popen(
                            [player, self.path],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                        )
                    self.backend = 'proc'
                else:
                    self.backend = 'beep'
                    _beep_fallback()
            elif sysname == "Windows":
                import winsound
                winsound.PlaySound(self.path, winsound.SND_FILENAME | winsound.SND_ASYNC)
                self.backend = 'winsound'
            else:
                self.backend = 'beep'
                _beep_fallback()
        except Exception:
            self.backend = 'beep'
            _beep_fallback()

    def stop(self):
        try:
            if self.backend == 'proc' and self.proc and self.proc.poll() is None:
                self.proc.terminate()
            elif self.backend == 'winsound':
                import winsound
                winsound.PlaySound(None, 0)  # 停止异步播放
        except Exception:
            pass
        finally:
            self.proc = None
            self.backend = None

AUDIO = AudioController(END_AUDIO_PATH)

# ---------- 计算 zoom/subsample 实现放大/缩小 ----------
def pick_zoom_subsample(orig_w, orig_h, SCALE, MAX_GIF_SIZE):
    """
    返回 (zoom, subsample) 两个整数因子，最终缩放比例 = zoom / subsample
    规则：
      - 若 SCALE 是数值：
          * SCALE >= 1 表示“缩小为 1/SCALE”（兼容旧逻辑）
          * SCALE  < 1 表示“放大为 1/SCALE”（例如 0.5 => 放大 2x）
      - 否则按 MAX_GIF_SIZE 自动缩放，使最长边尽量接近该值（四舍五入，不会缩过头）
    """
    z, s = 1, 1
    if SCALE is not None:
        SCALE = float(SCALE)
        if SCALE < 1:
            z = max(1, int(round(1.0 / SCALE)))
        else:
            s = max(1, int(round(SCALE)))
        return z, s

    if MAX_GIF_SIZE and MAX_GIF_SIZE > 0 and orig_w and orig_h:
        longest = max(orig_w, orig_h)
        ratio = MAX_GIF_SIZE / float(longest)
        if ratio > 1:    # 放大（四舍五入）
            z = max(1, int(round(ratio)))
        elif ratio < 1:  # 缩小（四舍五入）
            s = max(1, int(round(1.0 / ratio)))
    return z, s

# ---------- 结束弹窗：循环播放 GIF（含缩放）；关闭即停止音频 ----------
def show_end_gif_popup(root):
    top = Toplevel(root)
    top.title("Time's up!")
    top.resizable(False, False)
    try: top.attributes("-topmost", True)
    except Exception: pass

    # 载入所有帧（支持放大/缩小）
    frames, w, h = [], 420, 420
    try:
        first_raw = tk.PhotoImage(file=END_GIF_PATH, format="gif -index 0")
        orig_w, orig_h = first_raw.width(), first_raw.height()
        z, s = pick_zoom_subsample(orig_w, orig_h, SCALE, MAX_GIF_SIZE)

        def apply_scale(img):
            if z > 1: img = img.zoom(z)
            if s > 1: img = img.subsample(s)
            return img

        first = apply_scale(first_raw)
        w, h = first.width(), first.height()
        frames.append(first)

        idx = 1
        while True:
            frm_raw = tk.PhotoImage(file=END_GIF_PATH, format=f"gif -index {idx}")
            frames.append(apply_scale(frm_raw))
            idx += 1
    except Exception:
        pass

    # 居中
    sw, sh = top.winfo_screenwidth(), top.winfo_screenheight()
    x, y = (sw - w) // 2, (sh - h) // 3
    top.geometry(f"+{x}+{y}")

    lbl = tk.Label(top)
    lbl.pack()

    def animate(i=0):
        if not frames:
            lbl.config(text="(未找到 GIF: %s)" % END_GIF_PATH)
        else:
            lbl.configure(image=frames[i])
            top.after(ANIM_INTERVAL_MS, animate, (i + 1) % len(frames))
    animate()

    # 播放音频
    AUDIO.play()

    # 关闭时：先停音频再销毁
    def close(_=None):
        try: AUDIO.stop()
        finally:
            try: top.destroy()
            except Exception: pass

    top.bind("<Escape>", close)
    #top.bind("<Button-1>", close)
    top.protocol("WM_DELETE_WINDOW", close)

# ================== 主 App ==================
class TimerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Panda Pomodoro")
        self.root.resizable(False, False)

        # 计时状态
        self.total_seconds = 0
        self.remaining = 0
        self.running = False
        self._tick_job = None

        # 番茄钟状态
        self.is_pomo = False
        self.focus_minutes = 25
        self.short_break = 5
        self.long_break = 15
        self.cycles_before_long = 4
        self.current_cycle = 0
        self.phase = "Idle"   # "Focus" | "ShortBreak" | "LongBreak" | "Idle"
        self.auto_loop = tk.BooleanVar(value=True)

        # 顶部：熊猫内嵌 GIF + 时间输入
        top = tk.Frame(root, padx=10, pady=8)
        top.pack(fill="x")

        self.gif_label = tk.Label(top)
        self.gif_label.grid(row=0, column=0, rowspan=2, padx=(0, 8))
        self._load_embedded_gif(PANDA_GIF_B64)

        tk.Label(top, text="Minutes").grid(row=0, column=1, sticky="e")
        self.entry_min = tk.Entry(top, width=5, justify="right"); self.entry_min.insert(0, "0")
        self.entry_min.grid(row=0, column=2, padx=(4, 10))

        tk.Label(top, text="Seconds").grid(row=0, column=3, sticky="e")
        self.entry_sec = tk.Entry(top, width=5, justify="right"); self.entry_sec.insert(0, "30")
        self.entry_sec.grid(row=0, column=4, padx=(4, 0))

        # 显示
        self.time_label = tk.Label(root, text="00:30", font=("Helvetica", 36), pady=6)
        self.time_label.pack()
        self.phase_label = tk.Label(root, text="Idle", font=("Helvetica", 12))
        self.phase_label.pack()

        # 控制按钮
        btn_frame = tk.Frame(root, padx=10, pady=4); btn_frame.pack()
        self.btn_start = tk.Button(btn_frame, text="Start", width=8, command=self.start)
        self.btn_pause = tk.Button(btn_frame, text="Pause", width=8, command=self.pause, state="disabled")
        self.btn_reset = tk.Button(btn_frame, text="Reset", width=8, command=self.reset, state="disabled")
        self.btn_start.grid(row=0, column=0, padx=4)
        self.btn_pause.grid(row=0, column=1, padx=4)
        self.btn_reset.grid(row=0, column=2, padx=4)

        # 选项（保留额外蜂鸣开关，默认 False 以免和音频重复）
        opt = tk.Frame(root, padx=10, pady=2); opt.pack()
        self.sound_var = tk.BooleanVar(value=False)
        tk.Checkbutton(opt, text="Extra beep", variable=self.sound_var).grid(row=0, column=0, padx=4)

        # 分割线
        tk.Label(root, text="— Pomodoro —").pack(pady=(6, 2))

        # 番茄参数
        pomo = tk.Frame(root, padx=10, pady=4); pomo.pack()
        tk.Label(pomo, text="Focus").grid(row=0, column=0, sticky="e")
        self.e_focus = tk.Entry(pomo, width=4, justify="right"); self.e_focus.insert(0, str(self.focus_minutes))
        self.e_focus.grid(row=0, column=1, padx=(4,10))

        tk.Label(pomo, text="Short").grid(row=0, column=2, sticky="e")
        self.e_short = tk.Entry(pomo, width=4, justify="right"); self.e_short.insert(0, str(self.short_break))
        self.e_short.grid(row=0, column=3, padx=(4,10))

        tk.Label(pomo, text="Long").grid(row=0, column=4, sticky="e")
        self.e_long = tk.Entry(pomo, width=4, justify="right"); self.e_long.insert(0, str(self.long_break))
        self.e_long.grid(row=0, column=5, padx=(4,10))

        tk.Label(pomo, text="Cycles").grid(row=0, column=6, sticky="e")
        self.e_cycles = tk.Entry(pomo, width=4, justify="right"); self.e_cycles.insert(0, str(self.cycles_before_long))
        self.e_cycles.grid(row=0, column=7, padx=(4,10))

        tk.Checkbutton(pomo, text="Auto loop", variable=self.auto_loop).grid(row=0, column=8, padx=(0,8))

        # 番茄按钮
        pomo_btns = tk.Frame(root, padx=10, pady=2); pomo_btns.pack()
        self.btn_pomo_start = tk.Button(pomo_btns, text="Start Pomodoro", width=14, command=self.start_pomodoro)
        self.btn_pomo_skip  = tk.Button(pomo_btns, text="Skip Phase", width=10, command=self.skip_phase, state="disabled")
        self.btn_pomo_stop  = tk.Button(pomo_btns, text="Stop Pomodoro", width=12, command=self.stop_pomodoro, state="disabled")
        self.btn_pomo_start.grid(row=0, column=0, padx=4)
        self.btn_pomo_skip.grid(row=0, column=1, padx=4)
        self.btn_pomo_stop.grid(row=0, column=2, padx=4)

        # 快捷键
        root.bind("<space>", self._toggle_pause)

        # 托盘（可选）
        self.tray = None
        self._init_tray()

        # 关闭按钮：隐藏到托盘（若托盘不可用则退出）
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_to_tray)

        # 初始显示
        self._update_display(30)

    # ------- 内嵌 GIF（页眉小熊猫；与结束弹窗无关） -------
    def _load_embedded_gif(self, b64string):
        self.gif_frames, self.gif_index, self._gif_job = [], 0, None
        b64_clean = (b64string or "").strip()
        def _try(data):
            i = 0
            while True:
                try:
                    frm = tk.PhotoImage(data=data, format=f"gif -index {i}")
                    self.gif_frames.append(frm); i += 1
                except Exception:
                    break
        _try(b64_clean)
        if not self.gif_frames:
            try:
                import base64 as _b64
                _try(_b64.b64decode(b64_clean))
            except Exception:
                pass
        if self.gif_frames:
            self._animate_gif()
        else:
            self.gif_label.config(text="🐼", font=("Helvetica", 20))

    def _animate_gif(self):
        if not self.gif_frames: return
        self.gif_label.config(image=self.gif_frames[self.gif_index])
        self.gif_index = (self.gif_index + 1) % len(self.gif_frames)
        self._gif_job = self.root.after(100, self._animate_gif)

    # ------- 基础计时 -------
    def _parse_input(self):
        try:
            mins = int(self.entry_min.get() or 0)
            secs = int(self.entry_sec.get() or 0)
            if mins < 0 or secs < 0 or secs >= 60: raise ValueError
            total = mins * 60 + secs
            if total == 0: raise ValueError
            return total
        except ValueError:
            messagebox.showerror("Invalid time", "请输入有效时间（秒 0-59，总时长>0）。")
            return None

    def _update_display(self, seconds):
        m, s = divmod(max(0, int(seconds)), 60)
        self.time_label.config(text=f"{m:02d}:{s:02d}")

    def _set_phase(self, name):
        self.phase = name
        self.phase_label.config(text=name)

    def start(self):
        if self.running and not self.is_pomo: return
        if self.is_pomo: return
        if self.remaining == 0:
            total = self._parse_input()
            if total is None: return
            self.total_seconds = total
            self.remaining = total
        self._set_phase("Manual")
        self.running = True
        self._schedule_tick(); self._refresh_buttons()

    def pause(self):
        if not self.running: return
        self.running = False
        if self._tick_job:
            self.root.after_cancel(self._tick_job); self._tick_job = None
        self._refresh_buttons()

    def reset(self):
        self.running = False
        if self._tick_job:
            self.root.after_cancel(self._tick_job); self._tick_job = None
        self.is_pomo = False
        self._set_phase("Idle")
        self.remaining = 0
        try:
            total = (int(self.entry_min.get() or 0) * 60 + int(self.entry_sec.get() or 0))
        except ValueError:
            total = 0
        self._update_display(total); self._refresh_buttons()

    def _schedule_tick(self):
        self._update_display(self.remaining)
        if not self.running: return
        if self.remaining <= 0:
            self.running = False; self._refresh_buttons()
            self.time_label.config(text="00:00")
            # —— 结束动作：弹窗 GIF + 播放音频（关闭即停）
            show_end_gif_popup(self.root)
            if self.sound_var.get(): _beep_fallback()  # 可选额外“哔”
            self._on_phase_finished(); return
        self._tick_job = self.root.after(1000, self._tick)

    def _tick(self): self.remaining -= 1; self._schedule_tick()

    def _refresh_buttons(self):
        if self.is_pomo:
            self.btn_start.config(state="disabled")
            self.btn_pause.config(state="normal" if self.running else "disabled", text="Pause")
            self.btn_reset.config(state="disabled")
            self.btn_pomo_start.config(state="disabled" if self.running else "normal")
            self.btn_pomo_skip.config(state="normal" if self.running else "disabled")
            self.btn_pomo_stop.config(state="normal")
        else:
            self.btn_start.config(state="disabled" if self.running else "normal")
            self.btn_pause.config(state="normal" if self.running else "disabled")
            self.btn_reset.config(state="normal" if self.remaining > 0 or self.phase != "Idle" else "disabled")
            self.btn_pomo_start.config(state="normal")
            self.btn_pomo_skip.config(state="disabled")
            self.btn_pomo_stop.config(state="disabled")

    def _toggle_pause(self, _=None):
        if self.running: self.pause()
        else:
            if self.is_pomo:
                self.running = True; self._schedule_tick(); self._refresh_buttons()
            else:
                self.start()

    # ------- 番茄钟 -------
    def _apply_pomo_settings(self):
        try:
            self.focus_minutes = max(1, int(self.e_focus.get()))
            self.short_break   = max(1, int(self.e_short.get()))
            self.long_break    = max(1, int(self.e_long.get()))
            self.cycles_before_long = max(1, int(self.e_cycles.get()))
        except ValueError:
            messagebox.showerror("Invalid Pomodoro", "番茄钟参数请输入整数。")
            return False
        return True

    def start_pomodoro(self):
        if not self._apply_pomo_settings(): return
        self.is_pomo = True; self.current_cycle = 0
        self._start_focus(); self._refresh_buttons()

    def stop_pomodoro(self):
        self.is_pomo = False; self.pause()
        self._set_phase("Idle"); self.remaining = 0
        self._update_display(0); self._refresh_buttons()

    def skip_phase(self): self.remaining = 0; self._schedule_tick()

    def _start_focus(self):
        self._set_phase("Focus"); self.remaining = self.focus_minutes * 60
        self.running = True; self._schedule_tick()

    def _start_short_break(self):
        self._set_phase("ShortBreak"); self.remaining = self.short_break * 60
        self.running = True; self._schedule_tick()

    def _start_long_break(self):
        self._set_phase("LongBreak"); self.remaining = self.long_break * 60
        self.running = True; self._schedule_tick()

    def _on_phase_finished(self):
        if not self.is_pomo: return
        if self.phase == "Focus":
            self.current_cycle += 1
            if self.current_cycle % self.cycles_before_long == 0:
                self._start_long_break()
            else:
                self._start_short_break()
        elif self.phase in ("ShortBreak", "LongBreak"):
            if self.auto_loop.get(): self._start_focus()
            else:
                self.running = False; self._set_phase("Idle"); self._refresh_buttons()

    # ------- 托盘（可选） -------
    def _init_tray(self):
        try:
            import pystray
            from PIL import Image
        except Exception:
            self.tray = None; return

        img_bytes = base64.b64decode(TRAY_ICON_PNG_B64)
        try:
            img = Image.open(io.BytesIO(img_bytes))
        except Exception:
            self.tray = None; return

        def on_show(icon, item=None): self.root.after(0, self._show_window)
        def on_hide(icon, item=None): self.root.after(0, self._hide_window)
        def on_start_pomo(icon, item=None): self.root.after(0, self.start_pomodoro)
        def on_pause_resume(icon, item=None):
            self.root.after(0, (self.pause if self.running else self._toggle_pause))
        def on_stop(icon, item=None): self.root.after(0, self.stop_pomodoro)
        def on_quit(icon, item=None): self.root.after(0, self._quit_all)

        import pystray
        menu = pystray.Menu(
            pystray.MenuItem("Show Window", on_show),
            pystray.MenuItem("Hide Window", on_hide),
            pystray.MenuItem("Start Pomodoro", on_start_pomo),
            pystray.MenuItem("Pause/Resume", on_pause_resume),
            pystray.MenuItem("Stop Pomodoro", on_stop),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", on_quit)
        )
        self.tray = pystray.Icon("PandaPomodoro", img, "Panda Pomodoro", menu)
        threading.Thread(target=lambda: self.tray.run(), daemon=True).start()

    def _show_window(self):
        self.root.deiconify()
        self.root.after(50, self.root.lift)

    def _hide_window(self): self.root.withdraw()

    def _on_close_to_tray(self):
        if self.tray: self._hide_window()
        else: self._quit_all()

    def _quit_all(self):
        try:
            if self.tray: self.tray.stop()
        except Exception:
            pass
        self.root.destroy()

# ================== 入口 ==================
if __name__ == "__main__":
    root = tk.Tk()
    app = TimerApp(root)
    root.mainloop()
