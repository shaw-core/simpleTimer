#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import messagebox
import platform, subprocess, shutil, os, threading, base64, io

# ========= 内嵌 GIF（示例小动图；后续直接替换这里的 base64 即可） =========
# 替换方法：
#   python - <<'PY'
#   import base64; print(base64.b64encode(open("your_panda.gif","rb").read()).decode())
#   PY
# 把输出粘到三引号里（保持 """ ... """）
PANDA_GIF_B64 = """
R0lGODlhIAAgAKECAAAAAP///wAAAMLCwgAAACH5BAEKAAIALAAAAAAgACAAAALheLrc/jDKSau9OOvNu/9gKI5kaZ5oqq5s674vq9wFADs=
"""

# ========= 托盘图标（16x16 PNG，简易占位；可替换为base64 PNG） =========
TRAY_ICON_PNG_B64 = """
iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAMAAAAoLQ9TAAAAXVBMVEUAAAD/////////////////////////////////////////////////////////////
///////////////////////////8AAABlPj8mAAAAGnRSTlMAAQIDBAUGBwgJCgsMDQ4PEBESExQVFhcYGRs9X7mPAAAAQElEQVQY02NgQAZGJmBkYGBg
YJgBAMaBExgYpIhEwQEGwYQmQGAAkQbCkQZBgQjB8DgkQwEGgY1gQkGgYwYF0gJgZkGAAAPwQm3w5qf2sAAAAASUVORK5CYII=
"""

# ========= 结束提示音 =========
def play_sound():
    system = platform.system()
    if system == "Windows":
        try:
            import winsound
            winsound.Beep(1000, 500)
            return
        except Exception:
            pass
    if system == "Darwin" and shutil.which("afplay"):
        for sound in [
            "/System/Library/Sounds/Glass.aiff",
            "/System/Library/Sounds/Ping.aiff",
            "/System/Library/Sounds/Pop.aiff",
            "/System/Library/Sounds/Funk.aiff",
        ]:
            try:
                subprocess.run(["afplay", sound], check=True,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
            except Exception:
                continue
    print('\a', end='', flush=True)  # 兜底：终端铃声

class TimerApp:
    def __init__(self, root: tk.Tk):
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
        self.phase = "Idle"             # "Focus" | "ShortBreak" | "LongBreak" | "Idle"
        self.auto_loop = tk.BooleanVar(value=True)

        # 顶部栏：GIF + 输入
        top = tk.Frame(root, padx=10, pady=8)
        top.pack(fill="x")

        self.gif_label = tk.Label(top)
        self.gif_label.grid(row=0, column=0, rowspan=2, padx=(0, 8))
        self._load_embedded_gif(PANDA_GIF_B64)

        tk.Label(top, text="Minutes").grid(row=0, column=1, sticky="e")
        self.entry_min = tk.Entry(top, width=5, justify="right")
        self.entry_min.insert(0, "0")
        self.entry_min.grid(row=0, column=2, padx=(4, 10))

        tk.Label(top, text="Seconds").grid(row=0, column=3, sticky="e")
        self.entry_sec = tk.Entry(top, width=5, justify="right")
        self.entry_sec.insert(0, "30")
        self.entry_sec.grid(row=0, column=4, padx=(4, 0))

        # 时间显示 + 阶段标签
        self.time_label = tk.Label(root, text="00:30", font=("Helvetica", 36), pady=6)
        self.time_label.pack()
        self.phase_label = tk.Label(root, text="Idle", font=("Helvetica", 12))
        self.phase_label.pack()

        # 控制按钮（手动计时）
        btn_frame = tk.Frame(root, padx=10, pady=4)
        btn_frame.pack()
        self.btn_start = tk.Button(btn_frame, text="Start", width=8, command=self.start)
        self.btn_pause = tk.Button(btn_frame, text="Pause", width=8, command=self.pause, state="disabled")
        self.btn_reset = tk.Button(btn_frame, text="Reset", width=8, command=self.reset, state="disabled")
        self.btn_start.grid(row=0, column=0, padx=4)
        self.btn_pause.grid(row=0, column=1, padx=4)
        self.btn_reset.grid(row=0, column=2, padx=4)

        # 选项
        opt = tk.Frame(root, padx=10, pady=2)
        opt.pack()
        self.sound_var = tk.BooleanVar(value=True)
        tk.Checkbutton(opt, text="Beep when done", variable=self.sound_var).grid(row=0, column=0, padx=4)

        # 分割线
        tk.Label(root, text="— Pomodoro —").pack(pady=(6, 2))

        # 番茄钟控件
        pomo = tk.Frame(root, padx=10, pady=4)
        pomo.pack()

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

        # 番茄钟按钮
        pomo_btns = tk.Frame(root, padx=10, pady=2)
        pomo_btns.pack()
        self.btn_pomo_start = tk.Button(pomo_btns, text="Start Pomodoro", width=14, command=self.start_pomodoro)
        self.btn_pomo_skip  = tk.Button(pomo_btns, text="Skip Phase", width=10, command=self.skip_phase, state="disabled")
        self.btn_pomo_stop  = tk.Button(pomo_btns, text="Stop Pomodoro", width=12, command=self.stop_pomodoro, state="disabled")
        self.btn_pomo_start.grid(row=0, column=0, padx=4)
        self.btn_pomo_skip.grid(row=0, column=1, padx=4)
        self.btn_pomo_stop.grid(row=0, column=2, padx=4)

        # 空格键：暂停/继续
        root.bind("<space>", self._toggle_pause)

        # 托盘（可选）
        self.tray = None
        self._init_tray()

        # 关窗：隐藏到托盘（若托盘不可用则退出）
        self.root.protocol("WM_DELETE_WINDOW", self._on_close_to_tray)

        # 初始显示
        self._update_display(30)

    # ========= GIF 加载与播放 =========
    def _load_embedded_gif(self, b64string: str):
        self.gif_frames = []
        self.gif_index = 0
        self._gif_job = None

        b64_clean = (b64string or "").strip()

        def _try_load(data):
            i = 0
            while True:
                try:
                    frm = tk.PhotoImage(data=data, format=f"gif -index {i}")
                    self.gif_frames.append(frm)
                    i += 1
                except Exception:
                    break

        # 先尝试直接把 base64 字符串交给 PhotoImage
        _try_load(b64_clean)
        if not self.gif_frames:
            # 再尝试解码后的 bytes
            try:
                raw = base64.b64decode(b64_clean)
                _try_load(raw)
            except Exception:
                pass

        if self.gif_frames:
            self._animate_gif()
        else:
            # 占位显示（防止空白）
            self.gif_label.config(text="🐼", font=("Helvetica", 20))

    def _animate_gif(self):
        if not self.gif_frames:
            return
        self.gif_label.config(image=self.gif_frames[self.gif_index])
        self.gif_index = (self.gif_index + 1) % len(self.gif_frames)
        self._gif_job = self.root.after(100, self._animate_gif)  # 固定 100ms/帧

    # ========= 基础计时逻辑 =========
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
        if self.running and not self.is_pomo:
            return
        if self.is_pomo:
            return
        if self.remaining == 0:
            total = self._parse_input()
            if total is None:
                return
            self.total_seconds = total
            self.remaining = total
        self._set_phase("Manual")
        self.running = True
        self._schedule_tick()
        self._refresh_buttons()

    def pause(self):
        if not self.running:
            return
        self.running = False
        if self._tick_job:
            self.root.after_cancel(self._tick_job)
            self._tick_job = None
        self._refresh_buttons()

    def reset(self):
        self.running = False
        if self._tick_job:
            self.root.after_cancel(self._tick_job)
            self._tick_job = None
        self.is_pomo = False
        self._set_phase("Idle")
        self.remaining = 0
        try:
            total = (int(self.entry_min.get() or 0) * 60 + int(self.entry_sec.get() or 0))
        except ValueError:
            total = 0
        self._update_display(total)
        self._refresh_buttons()

    def _schedule_tick(self):
        self._update_display(self.remaining)
        if not self.running:
            return
        if self.remaining <= 0:
            self.running = False
            self._refresh_buttons()
            self.time_label.config(text="00:00")
            if self.sound_var.get():
                play_sound()
            self._on_phase_finished()
            return
        self._tick_job = self.root.after(1000, self._tick)

    def _tick(self):
        self.remaining -= 1
        self._schedule_tick()

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
        if self.running:
            self.pause()
        else:
            if self.is_pomo:
                self.running = True
                self._schedule_tick()
                self._refresh_buttons()
            else:
                self.start()

    # ========= 番茄钟 =========
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
        if not self._apply_pomo_settings():
            return
        self.is_pomo = True
        self.current_cycle = 0
        self._start_focus()
        self._refresh_buttons()

    def stop_pomodoro(self):
        self.is_pomo = False
        self.pause()
        self._set_phase("Idle")
        self.remaining = 0
        self._update_display(0)
        self._refresh_buttons()

    def skip_phase(self):
        self.remaining = 0
        self._schedule_tick()

    def _start_focus(self):
        self._set_phase("Focus")
        self.remaining = self.focus_minutes * 60
        self.running = True
        self._schedule_tick()

    def _start_short_break(self):
        self._set_phase("ShortBreak")
        self.remaining = self.short_break * 60
        self.running = True
        self._schedule_tick()

    def _start_long_break(self):
        self._set_phase("LongBreak")
        self.remaining = self.long_break * 60
        self.running = True
        self._schedule_tick()

    def _on_phase_finished(self):
        if not self.is_pomo:
            messagebox.showinfo("Done", "Time's out!")
            return
        if self.phase == "Focus":
            self.current_cycle += 1
            if self.current_cycle % self.cycles_before_long == 0:
                next_phase = "Long break"
                self._start_long_break()
            else:
                next_phase = "Short break"
                self._start_short_break()
            if self.sound_var.get():
                play_sound()
            messagebox.showinfo("Pomodoro", f"专注完成！进入 {next_phase}。")
        elif self.phase in ("ShortBreak", "LongBreak"):
            if self.auto_loop.get():
                next_msg = "开始下一轮专注！"
                self._start_focus()
            else:
                self.running = False
                self._set_phase("Idle")
                self._refresh_buttons()
                next_msg = "休息结束。"
            if self.sound_var.get():
                play_sound()
            messagebox.showinfo("Pomodoro", next_msg)

    # ========= 托盘（可选） =========
    def _init_tray(self):
        try:
            import pystray
            from PIL import Image
        except Exception:
            self.tray = None
            return

        img_bytes = base64.b64decode(TRAY_ICON_PNG_B64)
        try:
            img = Image.open(io.BytesIO(img_bytes))
        except Exception:
            self.tray = None
            return

        def on_show(icon, item=None):
            self.root.after(0, self._show_window)

        def on_hide(icon, item=None):
            self.root.after(0, self._hide_window)

        def on_start_pomo(icon, item=None):
            self.root.after(0, self.start_pomodoro)

        def on_pause_resume(icon, item=None):
            self.root.after(0, (self.pause if self.running else self._toggle_pause))

        def on_stop(icon, item=None):
            self.root.after(0, self.stop_pomodoro)

        def on_quit(icon, item=None):
            self.root.after(0, self._quit_all)

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

        def run_tray():
            try:
                self.tray.run()
            except Exception:
                pass

        t = threading.Thread(target=run_tray, daemon=True)
        t.start()

    def _show_window(self):
        self.root.deiconify()
        self.root.after(50, self.root.lift)

    def _hide_window(self):
        self.root.withdraw()

    def _on_close_to_tray(self):
        if self.tray:
            self._hide_window()
        else:
            self._quit_all()

    def _quit_all(self):
        try:
            if self.tray:
                self.tray.stop()
        except Exception:
            pass
        self.root.destroy()

# ========= 入口 =========
if __name__ == "__main__":
    root = tk.Tk()
    app = TimerApp(root)
    root.mainloop()
