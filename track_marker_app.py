#!/usr/bin/env python3
"""
Marker Tracker App — GUI version for Windows
Double-click track_marker_app.exe to launch.
"""

import sys
import csv
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

import cv2
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image, ImageTk


# --------------------------------------------------------------------------- #
# Tracking logic
# --------------------------------------------------------------------------- #

def build_hsv_mask(frame, point, hue_tol=15, sat_min=80, val_min=80, radius=10):
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    x, y = point
    patch = hsv[max(0, y - radius):y + radius + 1,
                max(0, x - radius):x + radius + 1]
    mean_h = float(np.median(patch[:, :, 0]))
    mean_s = float(np.median(patch[:, :, 1]))
    mean_v = float(np.median(patch[:, :, 2]))
    s_lo = max(sat_min, int(mean_s * 0.5))
    v_lo = max(val_min, int(mean_v * 0.5))
    h_lo = (mean_h - hue_tol) % 180
    h_hi = (mean_h + hue_tol) % 180
    if h_lo <= h_hi:
        mask = cv2.inRange(hsv,
                           np.array([h_lo, s_lo, v_lo]),
                           np.array([h_hi, 255, 255]))
    else:
        m1 = cv2.inRange(hsv, np.array([h_lo, s_lo, v_lo]), np.array([179, 255, 255]))
        m2 = cv2.inRange(hsv, np.array([0, s_lo, v_lo]), np.array([h_hi, 255, 255]))
        mask = cv2.bitwise_or(m1, m2)
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def find_closest_centroid(mask, ref):
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best, best_dist = None, float("inf")
    rx, ry = ref
    for cnt in contours:
        if cv2.contourArea(cnt) < 50:
            continue
        M = cv2.moments(cnt)
        if M["m00"] == 0:
            continue
        cx, cy = int(M["m10"] / M["m00"]), int(M["m01"] / M["m00"])
        d = (cx - rx) ** 2 + (cy - ry) ** 2
        if d < best_dist:
            best_dist, best = d, (cx, cy)
    return best


def track_video(video_path, initial_point, progress_cb=None):
    cap = cv2.VideoCapture(video_path)
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    coords, prev = [], initial_point
    for i in range(total):
        ret, frame = cap.read()
        if not ret:
            break
        mask = build_hsv_mask(frame, prev)
        result = find_closest_centroid(mask, prev)
        if result:
            cx, cy = result
            prev = (cx, cy)
            coords.append((i, cx, height - cy, i / fps if fps > 0 else i))
        if progress_cb and i % 10 == 0:
            progress_cb(i, total)
    cap.release()
    if progress_cb:
        progress_cb(total, total)
    return coords


def save_csv(coords, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["frame", "x", "y", "time_sec"])
        w.writerows(coords)


def make_plot(coords, video_path):
    xs = [c[1] for c in coords]
    ys = [c[2] for c in coords]
    times = [c[3] for c in coords]
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    sc = axes[0].scatter(xs, ys, c=times, cmap="viridis", s=10, alpha=0.7)
    axes[0].plot(xs, ys, color="gray", linewidth=0.5, alpha=0.4)
    axes[0].set_xlabel("X (px)")
    axes[0].set_ylabel("Y (px)")
    axes[0].set_title("Marker XY Trajectory")
    axes[0].set_aspect("equal")
    fig.colorbar(sc, ax=axes[0], label="Time (sec)")
    axes[1].plot(times, xs, label="X", color="tab:blue")
    axes[1].plot(times, ys, label="Y", color="tab:orange")
    axes[1].set_xlabel("Time (sec)")
    axes[1].set_ylabel("Position (px)")
    axes[1].set_title("X / Y over Time")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)
    fig.suptitle(f"Marker Tracking — {Path(video_path).name}", fontsize=11)
    plt.tight_layout()
    return fig


# --------------------------------------------------------------------------- #
# GUI
# --------------------------------------------------------------------------- #

class App(tk.Tk):
    PREVIEW_W = 640
    PREVIEW_H = 360

    def __init__(self):
        super().__init__()
        self.title("Marker Tracker")
        self.resizable(False, False)
        self.video_path = None
        self.first_frame = None       # BGR numpy array
        self.initial_point = None
        self.coords = []
        self._build_ui()

    # ------------------------------------------------------------------ UI --

    def _build_ui(self):
        pad = dict(padx=8, pady=4)

        # -- Top bar --
        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Button(top, text="動画を開く", command=self._open_video).pack(side="left")
        self.lbl_file = ttk.Label(top, text="ファイル未選択", foreground="gray")
        self.lbl_file.pack(side="left", padx=8)

        # -- Preview canvas --
        self.canvas = tk.Canvas(self, width=self.PREVIEW_W, height=self.PREVIEW_H,
                                bg="black", cursor="crosshair")
        self.canvas.pack(**pad)
        self.canvas.bind("<ButtonPress-1>", self._on_click)
        self._canvas_img = None

        self.lbl_hint = ttk.Label(self,
            text="動画を開いてから、追跡したいシールをクリックしてください。",
            foreground="gray")
        self.lbl_hint.pack()

        # -- Run button --
        btn_frame = ttk.Frame(self)
        btn_frame.pack(**pad)
        self.btn_run = ttk.Button(btn_frame, text="追跡を開始", command=self._run,
                                  state="disabled")
        self.btn_run.pack(side="left", padx=4)
        ttk.Button(btn_frame, text="散布図を保存", command=self._save_plot).pack(side="left", padx=4)
        ttk.Button(btn_frame, text="CSVを保存", command=self._save_csv).pack(side="left", padx=4)

        # -- Progress --
        self.progress = ttk.Progressbar(self, length=640, mode="determinate")
        self.progress.pack(**pad)
        self.lbl_status = ttk.Label(self, text="")
        self.lbl_status.pack()

    # --------------------------------------------------------- Video open --

    def _open_video(self):
        path = filedialog.askopenfilename(
            title="動画ファイルを選択",
            filetypes=[("動画ファイル", "*.mp4 *.avi *.mov *.mkv *.wmv"), ("すべて", "*.*")])
        if not path:
            return
        cap = cv2.VideoCapture(path)
        ret, frame = cap.read()
        cap.release()
        if not ret:
            messagebox.showerror("エラー", "動画を読み込めませんでした。")
            return
        self.video_path = path
        self.first_frame = frame
        self.initial_point = None
        self.coords = []
        self.lbl_file.config(text=Path(path).name, foreground="black")
        self._show_frame(frame)
        self.lbl_hint.config(
            text="追跡したいシールをクリックして位置を指定してください。",
            foreground="black")
        self.btn_run.config(state="disabled")
        self.lbl_status.config(text="")
        self.progress["value"] = 0

    # ---------------------------------------------------- Canvas helpers --

    def _show_frame(self, frame, mark=None):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        scale = min(self.PREVIEW_W / w, self.PREVIEW_H / h)
        nw, nh = int(w * scale), int(h * scale)
        self._scale = scale
        rgb = cv2.resize(rgb, (nw, nh))
        if mark:
            mx = int(mark[0] * scale)
            my = int(mark[1] * scale)
            cv2.drawMarker(rgb, (mx, my), (0, 255, 0), cv2.MARKER_CROSS, 20, 2)
        img = ImageTk.PhotoImage(Image.fromarray(rgb))
        self.canvas.create_image(self.PREVIEW_W // 2, self.PREVIEW_H // 2,
                                 anchor="center", image=img)
        self._canvas_img = img  # keep reference

    def _on_click(self, event):
        if self.first_frame is None:
            return
        # Convert canvas coords → original frame coords
        h, w = self.first_frame.shape[:2]
        scale = min(self.PREVIEW_W / w, self.PREVIEW_H / h)
        nw, nh = int(w * scale), int(h * scale)
        ox = (self.PREVIEW_W - nw) // 2
        oy = (self.PREVIEW_H - nh) // 2
        fx = int((event.x - ox) / scale)
        fy = int((event.y - oy) / scale)
        fx = max(0, min(w - 1, fx))
        fy = max(0, min(h - 1, fy))
        self.initial_point = (fx, fy)
        self._show_frame(self.first_frame, mark=(fx, fy))
        self.lbl_hint.config(
            text=f"初期位置: ({fx}, {fy})  ← 「追跡を開始」ボタンを押してください。",
            foreground="green")
        self.btn_run.config(state="normal")

    # ------------------------------------------------------- Run tracking --

    def _run(self):
        if not self.video_path or not self.initial_point:
            return
        self.btn_run.config(state="disabled")
        self.lbl_status.config(text="解析中...")
        self.progress["value"] = 0

        def worker():
            def on_progress(cur, total):
                pct = cur / total * 100 if total else 0
                self.progress["value"] = pct
                self.lbl_status.config(text=f"{cur}/{total} フレーム処理中...")

            self.coords = track_video(self.video_path, self.initial_point, on_progress)
            self.after(0, self._on_done)

        threading.Thread(target=worker, daemon=True).start()

    def _on_done(self):
        n = len(self.coords)
        self.lbl_status.config(text=f"完了！ {n} フレームでマーカーを検出しました。")
        self.btn_run.config(state="normal")
        if n == 0:
            messagebox.showwarning("検出なし",
                "マーカーが検出できませんでした。\n"
                "クリック位置やシールの色を確認して再試行してください。")
            return
        # Auto-save to same folder as video
        base = Path(self.video_path).with_suffix("")
        plot_path = str(base) + "_scatter.png"
        csv_path = str(base) + "_coords.csv"
        fig = make_plot(self.coords, self.video_path)
        fig.savefig(plot_path, dpi=150)
        plt.close(fig)
        save_csv(self.coords, csv_path)
        self.lbl_status.config(
            text=f"完了！ {n} 点検出 → {Path(plot_path).name} / {Path(csv_path).name} に保存")

    # -------------------------------------------------------- Manual save --

    def _save_plot(self):
        if not self.coords:
            messagebox.showinfo("情報", "先に追跡を実行してください。")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG画像", "*.png"), ("すべて", "*.*")])
        if not path:
            return
        fig = make_plot(self.coords, self.video_path)
        fig.savefig(path, dpi=150)
        plt.close(fig)
        messagebox.showinfo("保存完了", f"散布図を保存しました:\n{path}")

    def _save_csv(self):
        if not self.coords:
            messagebox.showinfo("情報", "先に追跡を実行してください。")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSVファイル", "*.csv"), ("すべて", "*.*")])
        if not path:
            return
        save_csv(self.coords, path)
        messagebox.showinfo("保存完了", f"CSVを保存しました:\n{path}")


# --------------------------------------------------------------------------- #

if __name__ == "__main__":
    app = App()
    app.mainloop()
