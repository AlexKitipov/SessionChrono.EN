#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import time
import zipfile
import threading
import shutil
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog

import pyperclip

try:
    import win32clipboard
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

try:
    import winsound
    HAS_WINSOUND = True
except ImportError:
    HAS_WINSOUND = False

# --------- BASE PATHS ---------
if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

SOUNDS_DIR = os.path.join(BASE_DIR, "sounds")

SOUND_FILES = {
    "start":  "start.wav",
    "copy":   "copy.wav",
    "error":  "error.wav",
    "pause":  "pause.wav",
    "resume": "resume.wav",
    "save":   "save.wav",
    "open":   "open.wav",
}

BEEP_PATTERNS = {
    "start":  (900, 120),
    "copy":   (1200, 120),
    "error":  (400, 250),
    "pause":  (700, 120),
    "resume": (900, 180),
    "save":   (800, 120),
    "open":   (1000, 100),
}

class SoundManager:
    def __init__(self, root: tk.Tk):
        self.root = root

    def play(self, event: str):
        if event not in BEEP_PATTERNS:
            return

        if HAS_WINSOUND:
            wav_name = SOUND_FILES.get(event)
            if wav_name:
                wav_path = os.path.join(SOUNDS_DIR, wav_name)
                if os.path.exists(wav_path):
                    try:
                        winsound.PlaySound(
                            wav_path,
                            winsound.SND_FILENAME | winsound.SND_ASYNC
                        )
                        return
                    except Exception:
                        pass

            freq, dur = BEEP_PATTERNS[event]
            try:
                winsound.Beep(freq, dur)
                return
            except Exception:
                pass

        try:
            self.root.bell()
        except Exception:
            pass

# --------- PATHS & CONFIG ---------
LOG_ROOT = os.path.join(BASE_DIR, "ChronoNotes")
os.makedirs(LOG_ROOT, exist_ok=True)

# --------- TEXT CLASSIFICATION ---------
def classify_text(text: str) -> str:
    t = text.strip().lower()
    if any(x in t for x in ("http://", "https://", "www.")):
        return "URL"
    if any(x in t for x in ("exception", "traceback", "error", "stack trace")):
        return "LOG"
    if any(x in t for x in ("def ", "class ", "{", "};", "console.log", "function ")):
        return "CODE"
    if any(x in t for x in ("todo", "must", "fix ", "task", "to do")):
        return "TODO"
    if any(x in t for x in ("copilot", "chatgpt", "assistant", "ai", "model")):
        return "CHAT"
    return "NOTE"

def make_short_title(text: str, max_len: int = 30) -> str:
    lines = text.strip().splitlines()
    line = lines[0] if lines else "empty"
    line = line.replace("\t", " ").strip()
    if len(line) > max_len:
        line = line[:max_len].rsplit(" ", 1)[0] or line[:max_len]
    bad = '<>:"/\\|?*'
    for ch in bad:
        line = line.replace(ch, "_")
    return line or "note"

def build_filename(text: str):
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H-%M-%S")

    category = classify_text(text)
    short = make_short_title(text)

    folder = os.path.join(LOG_ROOT, date_str, category)
    os.makedirs(folder, exist_ok=True)

    filename = f"{category}_{short}_{date_str}_{time_str}.txt"
    full_path = os.path.join(folder, filename)
    return full_path, folder, short, category

# --------- SAFE CLIPBOARD ACCESS ---------
def safe_clipboard_text() -> str:
    if HAS_WIN32:
        try:
            win32clipboard.OpenClipboard()
            data = win32clipboard.GetClipboardData()
            win32clipboard.CloseClipboard()
            if isinstance(data, str):
                return data
            else:
                return str(data)
        except Exception:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass

    try:
        return pyperclip.paste()
    except Exception:
        return ""

# --------- LISTBOX TOOLTIP ---------
class ListboxTooltip:
    def __init__(self, widget):
        self.widget = widget
        self.tipwindow = None
        widget.bind("<Motion>", self.on_motion)
        widget.bind("<Leave>", self.on_leave)

    def on_motion(self, event):
        index = self.widget.nearest(event.y)
        if index < 0:
            self.hidetip()
            return
        data = self.widget.get(index)
        if not data:
            self.hidetip()
            return
        self.showtip(data, event.x_root + 10, event.y_root + 10)

    def on_leave(self, _event):
        self.hidetip()

    def showtip(self, text, x, y):
        if self.tipwindow:
            self.hidetip()
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(
            tw,
            text=text,
            justify=tk.LEFT,
            background="#333333",
            foreground="white",
            relief=tk.SOLID,
            borderwidth=1,
            font=("Segoe UI", 9),
            padx=4,
            pady=2,
        )
        label.pack()

    def hidetip(self):
        tw = self.tipwindow
        if tw:
            tw.destroy()
        self.tipwindow = None

# --------- RIGHT CLICK MENU ---------
class RightClickMenu:
    def __init__(self, widget):
        self.widget = widget
        self.menu = tk.Menu(widget, tearoff=0, bg="#2d2d2d", fg="white")

        self.menu.add_command(label="Copy", command=self.copy)
        self.menu.add_command(label="Cut", command=self.cut)
        self.menu.add_command(label="Paste", command=self.paste)
        self.menu.add_separator()
        self.menu.add_command(label="Select All", command=self.select_all)
        self.menu.add_command(label="Clear", command=self.clear)

        widget.bind("<Button-3>", self.show_menu)

    def show_menu(self, event):
        try:
            self.menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.menu.grab_release()

    def copy(self):
        try:
            text = self.widget.get("sel.first", "sel.last")
            self.widget.clipboard_clear()
            self.widget.clipboard_append(text)
        except Exception:
            pass

    def cut(self):
        try:
            text = self.widget.get("sel.first", "sel.last")
            self.widget.clipboard_clear()
            self.widget.clipboard_append(text)
            self.widget.delete("sel.first", "sel.last")
        except Exception:
            pass

    def paste(self):
        try:
            text = self.widget.clipboard_get()
            self.widget.insert(tk.INSERT, text)
        except Exception:
            pass

    def select_all(self):
        self.widget.tag_add("sel", "1.0", "end")

    def clear(self):
        self.widget.delete("1.0", "end")
# --------- MAIN CLASS – APP ---------
class ChronoNotepadApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SessionChrono Notepad Smart Full Edition")
        self.geometry("1100x700")
        self.configure(bg="#2d2d2d")

        self.sound = SoundManager(self)
        self.status_var = tk.StringVar()
        self.last_record_path = None
        self.current_file_path = None
        self.last_clip_text = ""
        self.logging_active = True
        self.history = []  # {"title":..., "path":..., "text":...}

        self.daemon_stop = threading.Event()

        self._build_style()
        self._build_menu()
        self._build_layout()

        self.protocol("WM_DELETE_WINDOW", self.on_close)

        self.status_var.set("🔄 Starting monitoring service...")
        self.sound.play("start")

        self.start_clipboard_thread()

    # ---- UI BUILD ----
    def _build_style(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", background="#2d2d2d", foreground="#ffffff", font=("Segoe UI", 10))
        style.configure("TButton", background="#3e3e3e", foreground="#ffffff")
        style.map("TButton", background=[("active", "#505050")])
        style.configure("TLabel", background="#2d2d2d", foreground="#ffffff")

    def _build_menu(self):
        menubar = tk.Menu(self, bg="#2d2d2d", fg="#ffffff")

        file_menu = tk.Menu(menubar, tearoff=0, bg="#2d2d2d", fg="#ffffff")
        file_menu.add_command(label="New", command=self.new_file)
        file_menu.add_command(label="Open...", command=self.open_file)
        file_menu.add_command(label="Save", command=self.save_file)
        file_menu.add_command(label="Save As...", command=self.save_file_as)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0, bg="#2d2d2d", fg="#ffffff")
        tools_menu.add_command(label="Pause / Resume Monitoring", command=self.toggle_logging)
        tools_menu.add_command(label="Open Logs Folder", command=self.open_logs_folder)
        tools_menu.add_command(label="Open Last Saved Auto-Note", command=self.open_last_record)
        tools_menu.add_command(label="Create Backup ZIP of Today", command=self.create_today_zip)
        tools_menu.add_command(label="Search Inside Logs", command=self.search_in_logs)
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0, bg="#2d2d2d", fg="#ffffff")
        help_menu.add_command(label="About", command=self.show_about)
        menubar.add_cascade(label="Help", menu=help_menu)

        self.config(menu=menubar)

    def _build_layout(self):
        main_frame = ttk.Frame(self)
        main_frame.pack(fill="both", expand=True, padx=10, pady=10)

        main_frame.columnconfigure(0, weight=3)
        main_frame.columnconfigure(1, weight=2)
        main_frame.rowconfigure(0, weight=1)

        # Left – Text Editor
        left_frame = ttk.Frame(main_frame)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        self.editor = tk.Text(
            left_frame,
            wrap="word",
            font=("Consolas", 11),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
            undo=True,
        )
        editor_scroll = ttk.Scrollbar(left_frame, command=self.editor.yview)
        self.editor.configure(yscrollcommand=editor_scroll.set)
        self.editor.pack(side="left", fill="both", expand=True)
        editor_scroll.pack(side="right", fill="y")

        # ADD RIGHT CLICK MENU
        RightClickMenu(self.editor)

        # Right – Last Copied + History
        right_frame = ttk.Frame(main_frame)
        right_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 0))
        right_frame.rowconfigure(0, weight=1)
        right_frame.rowconfigure(1, weight=0)
        right_frame.rowconfigure(2, weight=2)
        right_frame.columnconfigure(0, weight=1)

        # Last Copied
        ttk.Label(
            right_frame,
            text="Last Copied:",
            font=("Segoe UI", 11, "bold")
        ).grid(row=0, column=0, sticky="w", pady=(0, 5))

        self.last_clip_box = tk.Text(
            right_frame,
            wrap="word",
            font=("Consolas", 10),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
            height=10,
        )
        clip_scroll = ttk.Scrollbar(right_frame, command=self.last_clip_box.yview)
        self.last_clip_box.configure(yscrollcommand=clip_scroll.set)
        self.last_clip_box.grid(row=0, column=0, sticky="nsew")
        clip_scroll.grid(row=0, column=1, sticky="ns")

        # ADD RIGHT CLICK MENU
        RightClickMenu(self.last_clip_box)

        # History label
        history_label = ttk.Label(
            right_frame,
            text="Clipboard History",
            font=("Segoe UI", 11, "bold"),
            anchor="center",
        )
        history_label.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(8, 4))

        # History frame
        hist_frame = ttk.Frame(right_frame)
        hist_frame.grid(row=2, column=0, columnspan=2, sticky="nsew")
        right_frame.rowconfigure(2, weight=1)

        self.history_listbox = tk.Listbox(
            hist_frame,
            bg="#1e1e1e",
            fg="#d4d4d4",
            activestyle="none",
            selectbackground="#264f78",
            selectforeground="#ffffff",
            font=("Consolas", 9),
        )
        hist_scroll = ttk.Scrollbar(hist_frame, command=self.history_listbox.yview)
        self.history_listbox.configure(yscrollcommand=hist_scroll.set)
        self.history_listbox.pack(side="left", fill="both", expand=True)
        hist_scroll.pack(side="right", fill="y")

        self.history_listbox.bind("<<ListboxSelect>>", self.on_history_select)
        ListboxTooltip(self.history_listbox)

        # Clear history button
        clear_btn = ttk.Button(
            right_frame,
            text="Clear Session History",
            command=self.clear_history
        )
        clear_btn.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))

        # Status bar
        status_frame = tk.Frame(self, bg="#007acc")
        status_frame.pack(side="bottom", fill="x")
        status_label = tk.Label(
            status_frame,
            textvariable=self.status_var,
            bg="#007acc",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            anchor="w",
            padx=5,
            pady=3,
        )
        status_label.pack(fill="x")

    # ---- CLIPBOARD LOGIC ----
    def start_clipboard_thread(self):
        t = threading.Thread(target=self.monitor_clipboard, daemon=True)
        t.start()

    def monitor_clipboard(self):
        self.last_clip_text = safe_clipboard_text()

        while not self.daemon_stop.is_set():
            if self.logging_active:
                try:
                    current_text = safe_clipboard_text()
                    if current_text and current_text != self.last_clip_text:
                        self.last_clip_text = current_text
                        self.after(0, self.handle_new_clipboard_item, current_text)
                except Exception:
                    self.after(0, self.report_error, "Clipboard monitoring error.")
            time.sleep(0.25)
    def handle_new_clipboard_item(self, text: str):
        try:
            path, folder, short, category = build_filename(text)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
            self.last_record_path = path

            item_title = f"[{category}] {short}"
            self.history.insert(0, {"title": item_title, "path": path, "text": text})
            self.history = self.history[:20]

            self.refresh_history_listbox()

            # Update last copied panel
            self.last_clip_box.config(state="normal")
            self.last_clip_box.delete("1.0", tk.END)
            self.last_clip_box.insert("1.0", text)
            self.last_clip_box.config(state="normal")

            self.status_var.set(f"✅ Saved clipboard as {item_title}")
            self.sound.play("copy")
        except Exception as e:
            self.report_error(f"Failed to save clipboard text: {e}")

    def refresh_history_listbox(self):
        self.history_listbox.delete(0, tk.END)
        for item in self.history:
            self.history_listbox.insert(tk.END, item["title"])

    # ---- HISTORY INTERACTION ----
    def on_history_select(self, _event):
        sel = self.history_listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx < 0 or idx >= len(self.history):
            return
        item = self.history[idx]
        try:
            with open(item["path"], "r", encoding="utf-8") as f:
                content = f.read()
            self.editor.delete("1.0", tk.END)
            self.editor.insert("1.0", content)
            self.current_file_path = item["path"]
            self.status_var.set(f"📂 Opened: {os.path.basename(item['path'])}")
            self.sound.play("open")
        except Exception as e:
            self.report_error(f"Failed to open file: {e}")

    def clear_history(self):
        self.history.clear()
        self.refresh_history_listbox()
        self.status_var.set("🧹 Session history cleared.")

    # ---- FILE OPERATIONS ----
    def new_file(self):
        self.editor.delete("1.0", tk.END)
        self.current_file_path = None
        self.status_var.set("📝 New file.")
        self.sound.play("open")

    def open_file(self):
        path = filedialog.askopenfilename(
            title="Open Text File",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.editor.delete("1.0", tk.END)
            self.editor.insert("1.0", content)
            self.current_file_path = path
            self.status_var.set(f"📂 Opened: {os.path.basename(path)}")
            self.sound.play("open")
        except Exception as e:
            self.report_error(f"Failed to open file: {e}")

    def save_file(self):
        if not self.current_file_path:
            return self.save_file_as()
        try:
            content = self.editor.get("1.0", tk.END)
            with open(self.current_file_path, "w", encoding="utf-8") as f:
                f.write(content)
            self.status_var.set(f"💾 Saved: {os.path.basename(self.current_file_path)}")
            self.sound.play("save")
        except Exception as e:
            self.report_error(f"Failed to save file: {e}")

    def save_file_as(self):
        path = filedialog.asksaveasfilename(
            title="Save As",
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")]
        )
        if not path:
            return
        try:
            content = self.editor.get("1.0", tk.END)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.current_file_path = path
            self.status_var.set(f"💾 Saved As: {os.path.basename(path)}")
            self.sound.play("save")
        except Exception as e:
            self.report_error(f"Failed to save file: {e}")

    # ---- TOOLS ----
    def toggle_logging(self):
        self.logging_active = not self.logging_active
        if self.logging_active:
            self.status_var.set("▶ Clipboard monitoring resumed.")
            self.sound.play("resume")
        else:
            self.status_var.set("⏸ Clipboard monitoring paused.")
            self.sound.play("pause")

    def open_logs_folder(self):
        try:
            if sys.platform.startswith("win"):
                os.startfile(LOG_ROOT)
            elif sys.platform == "darwin":
                os.system(f"open '{LOG_ROOT}'")
            else:
                os.system(f"xdg-open '{LOG_ROOT}'")
            self.status_var.set("📁 Opened logs folder.")
            self.sound.play("open")
        except Exception as e:
            self.report_error(f"Failed to open logs folder: {e}")

    def open_last_record(self):
        if not self.last_record_path or not os.path.exists(self.last_record_path):
            self.report_error("No last auto-note found.")
            return
        try:
            with open(self.last_record_path, "r", encoding="utf-8") as f:
                content = f.read()
            self.editor.delete("1.0", tk.END)
            self.editor.insert("1.0", content)
            self.current_file_path = self.last_record_path
            self.status_var.set(f"📂 Opened last auto-note: {os.path.basename(self.last_record_path)}")
            self.sound.play("open")
        except Exception as e:
            self.report_error(f"Failed to open last auto-note: {e}")

    def create_today_zip(self):
        today = datetime.now().strftime("%Y-%m-%d")
        day_folder = os.path.join(LOG_ROOT, today)
        if not os.path.exists(day_folder):
            self.report_error("No logs for today.")
            return

        zip_name = os.path.join(LOG_ROOT, f"{today}_ChronoNotes.zip")
        try:
            with zipfile.ZipFile(zip_name, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(day_folder):
                    for file in files:
                        full_path = os.path.join(root, file)
                        rel_path = os.path.relpath(full_path, LOG_ROOT)
                        zf.write(full_path, rel_path)
            self.status_var.set(f"📦 Created ZIP: {os.path.basename(zip_name)}")
            self.sound.play("save")
        except Exception as e:
            self.report_error(f"Failed to create ZIP: {e}")

    def search_in_logs(self):
        query = simpledialog.askstring("Search Logs", "Enter text to search:")
        if not query:
            return

        matches = []
        try:
            for root, dirs, files in os.walk(LOG_ROOT):
                for file in files:
                    if not file.lower().endswith(".txt"):
                        continue
                    full_path = os.path.join(root, file)
                    try:
                        with open(full_path, "r", encoding="utf-8") as f:
                            content = f.read()
                        if query.lower() in content.lower():
                            matches.append(full_path)
                    except Exception:
                        continue
        except Exception as e:
            self.report_error(f"Search failed: {e}")
            return

        if not matches:
            messagebox.showinfo("Search Logs", "No matches found.")
            return

        result_win = tk.Toplevel(self)
        result_win.title("Search Results")
        result_win.geometry("600x400")
        result_win.configure(bg="#2d2d2d")

        lb = tk.Listbox(
            result_win,
            bg="#1e1e1e",
            fg="#d4d4d4",
            selectbackground="#3e3e3e",
            font=("Segoe UI", 9)
        )
        lb.pack(fill="both", expand=True, padx=10, pady=10)

        for p in matches:
            lb.insert(tk.END, p)

        def open_selected(_event=None):
            sel = lb.curselection()
            if not sel:
                return
            path = lb.get(sel[0])
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                self.editor.delete("1.0", tk.END)
                self.editor.insert("1.0", content)
                self.current_file_path = path
                self.status_var.set(f"📂 Opened from search: {os.path.basename(path)}")
                self.sound.play("open")
                result_win.destroy()
            except Exception as e:
                self.report_error(f"Failed to open file: {e}")

        lb.bind("<Double-Button-1>", open_selected)

    # ---- HELP ----
    def show_about(self):
        messagebox.showinfo(
            "About SessionChrono",
            "SessionChrono – Smart clipboard-logging notepad\n"
            "Automatically saves copied text into categorized files with timestamps.\n"
            "Includes editor, history, search, ZIP archiving, and sound alerts."
        )

    # ---- ERROR HANDLING ----
    def report_error(self, msg: str):
        self.status_var.set(f"❌ {msg}")
        self.sound.play("error")

    # ---- CLOSE ----
    def on_close(self):
        self.daemon_stop.set()
        self.destroy()


def main():
    app = ChronoNotepadApp()
    app.mainloop()


if __name__ == "__main__":
    main()
