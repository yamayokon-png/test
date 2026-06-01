#!/usr/bin/env python3
"""
Motion Extractor
----------------
TrackerがエクスポートしたCSVから「マーカーが動いている区間」を自動検出し、
その区間だけ抜き出したCSVと散布図を出力する。

Usage: python extract_motion.py [CSVファイルまたはフォルダ]
"""

import sys
import os
import glob
import csv
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


# -----------------------------------------------------------------------
# 動き区間検出
# -----------------------------------------------------------------------

def detect_motion_range(times, xs, ys,
                         speed_threshold=0.005,   # m/s 以下は静止とみなす
                         min_duration_sec=0.5):    # 最低この秒数動いていないと除外
    """
    速度が speed_threshold を超えている連続区間を返す。
    Returns: list of (start_idx, end_idx)
    """
    if len(times) < 3:
        return [(0, len(times)-1)]

    # フレーム間速度
    speeds = [0.0]
    for i in range(1, len(times)):
        dt = times[i] - times[i-1]
        if dt <= 0:
            speeds.append(0.0)
            continue
        dx = xs[i] - xs[i-1]
        dy = ys[i] - ys[i-1]
        speeds.append(((dx**2 + dy**2)**0.5) / dt)

    speeds = np.array(speeds)

    # 移動平均でノイズ除去
    kernel = np.ones(5) / 5
    speeds_smooth = np.convolve(speeds, kernel, mode='same')

    moving = speeds_smooth > speed_threshold

    # 連続区間を探す
    segments = []
    in_seg = False
    start = 0
    for i, m in enumerate(moving):
        if m and not in_seg:
            start = i
            in_seg = True
        elif not m and in_seg:
            in_seg = False
            dur = times[i-1] - times[start]
            if dur >= min_duration_sec:
                segments.append((start, i-1))
    if in_seg:
        dur = times[-1] - times[start]
        if dur >= min_duration_sec:
            segments.append((start, len(times)-1))

    # 区間が見つからなければ全体を返す
    if not segments:
        return [(0, len(times)-1)]

    # 全区間を1つにまとめる（最初の動き始め〜最後の動き終わり）
    return [(segments[0][0], segments[-1][1])]


# -----------------------------------------------------------------------
# CSV処理
# -----------------------------------------------------------------------

def process_csv(csv_path: str):
    """
    TrackerエクスポートCSVを読み込み、動き区間を検出して
    抜き出しCSVと散布図を保存する。
    """
    rows = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = None
        for row in reader:
            if not row:
                continue
            # ヘッダー行を探す（"t" または "time" を含む行）
            if header is None:
                low = [c.lower().strip() for c in row]
                if any("t" == c or "time" in c for c in low):
                    header = row
                continue
            rows.append(row)

    if not header or not rows:
        return False, "CSVの形式を認識できませんでした。"

    # 列インデックスを特定
    def find_col(keywords):
        for i, h in enumerate(header):
            for kw in keywords:
                if kw in h.lower():
                    return i
        return None

    t_idx = find_col(["t"])
    x_idx = find_col(["x"])
    y_idx = find_col(["y"])

    if None in (t_idx, x_idx, y_idx):
        return False, f"t/x/y 列が見つかりません。ヘッダー: {header}"

    times, xs, ys = [], [], []
    for row in rows:
        try:
            times.append(float(row[t_idx]))
            xs.append(float(row[x_idx]))
            ys.append(float(row[y_idx]))
        except (ValueError, IndexError):
            continue

    if len(times) < 5:
        return False, "データ点が少なすぎます。"

    # 動き区間検出
    segs = detect_motion_range(times, xs, ys)
    s, e = segs[0]

    t_cut  = times[s:e+1]
    x_cut  = xs[s:e+1]
    y_cut  = ys[s:e+1]

    base = Path(csv_path).with_suffix("")

    # 抜き出しCSV保存
    out_csv = str(base) + "_motion.csv"
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["time_sec", "x_m", "y_m"])
        for t, x, y in zip(t_cut, x_cut, y_cut):
            w.writerow([t, x, y])

    # 散布図保存
    out_png = str(base) + "_scatter.png"
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    sc = axes[0].scatter(x_cut, y_cut, c=t_cut, cmap="viridis", s=15, alpha=0.8)
    axes[0].plot(x_cut, y_cut, color="gray", linewidth=0.5, alpha=0.4)
    axes[0].set_xlabel("X (m)")
    axes[0].set_ylabel("Y (m)")
    axes[0].set_title("XY軌跡（動き区間）")
    axes[0].set_aspect("equal")
    fig.colorbar(sc, ax=axes[0], label="Time (sec)")

    axes[1].plot(t_cut, x_cut, label="X", color="tab:blue")
    axes[1].plot(t_cut, y_cut, label="Y", color="tab:orange")
    axes[1].set_xlabel("Time (sec)")
    axes[1].set_ylabel("位置 (m)")
    axes[1].set_title("X / Y の時系列")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    name = Path(csv_path).name
    fig.suptitle(f"{name}  [{times[s]:.2f}s 〜 {times[e]:.2f}s]", fontsize=11)
    plt.tight_layout()
    plt.savefig(out_png, dpi=150)
    plt.close(fig)

    msg = (f"動き区間: {times[s]:.2f}s 〜 {times[e]:.2f}s "
           f"（{len(t_cut)} フレーム）\n"
           f"→ {Path(out_csv).name}\n"
           f"→ {Path(out_png).name}")
    return True, msg


# -----------------------------------------------------------------------
# GUI
# -----------------------------------------------------------------------

class ExtractApp(tk.Tk):
    def __init__(self, target=None):
        super().__init__()
        self.title("動き区間 自動抽出")
        self.resizable(False, False)
        self._build_ui()
        if target:
            self.after(100, lambda: self._run(target))

    def _build_ui(self):
        pad = dict(padx=10, pady=6)
        ttk.Label(self, text="TrackerエクスポートCSV → 動き区間を自動抽出",
                  font=("", 11)).pack(**pad)

        btn = ttk.Frame(self)
        btn.pack(**pad)
        ttk.Button(btn, text="CSVファイルを選択", command=self._pick_file).pack(side="left", padx=4)
        ttk.Button(btn, text="フォルダを一括処理", command=self._pick_folder).pack(side="left", padx=4)

        self.txt = tk.Text(self, width=70, height=15, state="disabled")
        self.txt.pack(**pad)

    def _log(self, msg):
        self.txt.config(state="normal")
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")
        self.txt.config(state="disabled")

    def _pick_file(self):
        p = filedialog.askopenfilename(
            title="CSVを選択",
            filetypes=[("CSV", "*.csv"), ("すべて", "*.*")])
        if p:
            self._run(p)

    def _pick_folder(self):
        d = filedialog.askdirectory(title="CSVが入っているフォルダを選択")
        if d:
            self._run(d)

    def _run(self, target):
        if os.path.isdir(target):
            files = sorted(glob.glob(os.path.join(target, "*.csv")))
            # _motion.csv は除外
            files = [f for f in files if "_motion" not in f]
            if not files:
                self._log("CSVファイルが見つかりませんでした。")
                return
            self._log(f"{len(files)} 件処理します...\n")
            for f in files:
                ok, msg = process_csv(f)
                status = "✓" if ok else "✗"
                self._log(f"{status} {Path(f).name}\n  {msg}\n")
        else:
            ok, msg = process_csv(target)
            status = "✓" if ok else "✗"
            self._log(f"{status} {Path(target).name}\n  {msg}\n")


# -----------------------------------------------------------------------

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    app = ExtractApp(target=target)
    app.mainloop()
