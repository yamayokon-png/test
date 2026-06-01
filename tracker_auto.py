#!/usr/bin/env python3
"""
Tracker 半自動ツール（テンプレート方式）
-----------------------------------------
既存のTRKファイルをテンプレートとして使い、
動画パス・フレーム情報・マーカー位置・キャリブレーションだけ書き換える。

Usage: python tracker_auto.py [動画フォルダ]
"""

import os, sys, re, glob, subprocess, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageTk

CALIBRATION_LENGTH_M = 0.10   # マーカー間 10cm
PREVIEW_W, PREVIEW_H = 800, 450
MARKER_COLORS_BGR = [
    (0,0,255),(0,200,0),(255,0,0),(0,150,200),
    (200,0,150),(180,180,0),(0,100,255),(80,80,80)
]
MARKER_COLORS_RGB = [(r,g,b) for (b,g,r) in MARKER_COLORS_BGR]

# -----------------------------------------------------------------------
# TRK 生成（テンプレート書き換え方式）
# -----------------------------------------------------------------------

def build_pointmass_xml(idx, x, y, color_rgb):
    r, g, b = color_rgb
    name = chr(65 + idx)
    return f"""        <property name="item" type="object">
        <object class="org.opensourcephysics.cabrillo.tracker.PointMass">
            <property name="mass" type="double">1.0</property>
            <property name="name" type="string">質量 {name}</property>
            <property name="color" type="object">
            <object class="java.awt.Color">
                <property name="red" type="int">{r}</property>
                <property name="green" type="int">{g}</property>
                <property name="blue" type="int">{b}</property>
                <property name="alpha" type="int">255</property>
            </object>
            </property>
            <property name="footprint" type="string">Footprint.Diamond</property>
            <property name="visible" type="boolean">true</property>
            <property name="trail" type="boolean">true</property>
            <property name="framedata" type="array" class="[Lorg.opensourcephysics.cabrillo.tracker.PointMass$FrameData;">
                <property name="[0]" type="object">
                <object class="org.opensourcephysics.cabrillo.tracker.PointMass$FrameData">
                    <property name="x" type="double">{float(x)}</property>
                    <property name="y" type="double">{float(y)}</property>
                </object>
                </property>
            </property>
        </object>
        </property>"""


def make_trk_from_template(template_path, video_path,
                            markers, calib_p1, calib_p2,
                            frame_count, fps, width, height):
    with open(template_path, encoding="utf-8") as f:
        trk = f.read()

    # --- スケール計算（ピクセル/メートル）---
    dx = calib_p2[0] - calib_p1[0]
    dy = calib_p2[1] - calib_p1[1]
    calib_px = (dx**2 + dy**2) ** 0.5
    ppm = calib_px / CALIBRATION_LENGTH_M   # pixels per meter

    # --- frame times 文字列 ---
    times = [i * 1000.0 / fps for i in range(frame_count)]
    times_str = "{" + ",".join(f"{t:.3f}".rstrip('0').rstrip('.') for t in times) + "}"

    # --- 動画パス ---
    trk = re.sub(
        r'(<property name="path" type="string">)[^<]*(</property>)',
        r'\g<1>' + Path(video_path).name + r'\2',
        trk)

    # --- frame_times ---
    trk = re.sub(
        r'(<property name="array" type="string">)\{[^}]*\}(</property>)',
        r'\g<1>' + times_str + r'\2',
        trk)

    # --- duration ---
    trk = re.sub(
        r'(<property name="duration" type="double">)[^<]*(</property>)',
        r'\g<1>' + f'{frame_count/fps:.3f}' + r'\2',
        trk)

    # --- frame_count (XuggleVideo内) ---
    trk = re.sub(
        r'(<property name="frame_count" type="int">)[^<]*(</property>)',
        r'\g<1>' + str(frame_count) + r'\2',
        trk)

    # --- frame_rate ---
    trk = re.sub(
        r'(<property name="frame_rate" type="int">)[^<]*(</property>)',
        r'\g<1>' + str(int(round(fps))) + r'\2',
        trk)

    # --- video_framecount / stepcount ---
    trk = re.sub(
        r'(<property name="video_framecount" type="int">)[^<]*(</property>)',
        r'\g<1>' + str(frame_count) + r'\2',
        trk)
    trk = re.sub(
        r'(<property name="stepcount" type="int">)[^<]*(</property>)',
        r'\g<1>' + str(frame_count) + r'\2',
        trk)

    # --- clipcontrol delta_t & last frame ---
    trk = re.sub(
        r'(<property name="delta_t" type="double">)[^<]*(</property>)',
        r'\g<1>' + f'{1000.0/fps:.6f}' + r'\2',
        trk)
    trk = re.sub(
        r'(<property name="frame" type="int">)[^<]*(</property>)',
        r'\g<1>' + str(frame_count - 1) + r'\2',
        trk)

    # --- width / height ---
    trk = re.sub(
        r'(<property name="width" type="double">)[^<]*(</property>)',
        r'\g<1>' + f'{width}.0' + r'\2',
        trk)
    trk = re.sub(
        r'(<property name="height" type="double">)[^<]*(</property>)',
        r'\g<1>' + f'{height}.0' + r'\2',
        trk)

    # --- 座標系 origin（マーカー1番目 = 生ピクセル座標、Y下向きそのまま）---
    trk = re.sub(
        r'(<property name="xorigin" type="double">)[^<]*(</property>)',
        r'\g<1>' + f'{float(markers[0][0])}' + r'\2',
        trk)
    trk = re.sub(
        r'(<property name="yorigin" type="double">)[^<]*(</property>)',
        r'\g<1>' + f'{float(markers[0][1])}' + r'\2',
        trk)

    # --- スケール ---
    trk = re.sub(
        r'(<property name="xscale" type="double">)[^<]*(</property>)',
        r'\g<1>' + f'{ppm}' + r'\2',
        trk)
    trk = re.sub(
        r'(<property name="yscale" type="double">)[^<]*(</property>)',
        r'\g<1>' + f'{ppm}' + r'\2',
        trk)

    # --- キャリブレーションスティック座標（生ピクセル、Y下向きそのまま）---
    trk = re.sub(
        r'(<property name="x1" type="double">)[^<]*(</property>)',
        r'\g<1>' + f'{float(calib_p1[0])}' + r'\2',
        trk)
    trk = re.sub(
        r'(<property name="y1" type="double">)[^<]*(</property>)',
        r'\g<1>' + f'{float(calib_p1[1])}' + r'\2',
        trk)
    trk = re.sub(
        r'(<property name="x2" type="double">)[^<]*(</property>)',
        r'\g<1>' + f'{float(calib_p2[0])}' + r'\2',
        trk)
    trk = re.sub(
        r'(<property name="y2" type="double">)[^<]*(</property>)',
        r'\g<1>' + f'{float(calib_p2[1])}' + r'\2',
        trk)

    # --- キャリブレーション長さ ---
    trk = re.sub(
        r'(<property name="\[0\]" type="double">)[^<]*(</property>)',
        r'\g<1>' + f'{CALIBRATION_LENGTH_M}' + r'\2',
        trk)

    # --- 既存のPointMassを全部削除してから8個追加 ---
    trk = re.sub(
        r'\s*<property name="item" type="object">\s*<object class="org\.opensourcephysics\.cabrillo\.tracker\.PointMass">.*?</object>\s*</property>',
        '', trk, flags=re.DOTALL)

    new_masses = "\n".join(
        build_pointmass_xml(i, mx, my, MARKER_COLORS_RGB[i])
        for i, (mx, my) in enumerate(markers)
    )

    # </property> の直前（tracks コレクションの閉じタグ前）に挿入
    trk = trk.replace(
        '    </property>\n</object>',
        new_masses + '\n    </property>\n</object>',
        1)

    return trk


# -----------------------------------------------------------------------
# GUI
# -----------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self, video_dir=None):
        super().__init__()
        self.title("Tracker 半自動ツール")
        self.resizable(False, False)

        self.template_path = None
        self.videos = []
        self.video_idx = 0
        self.first_frame = None
        self.frame_w = self.frame_h = 0
        self.fps = 30.0
        self.frame_count = 0
        self.phase = "markers"
        self.markers = []
        self.calib_pts = []
        self._cimg = None

        self._build_ui()
        if video_dir:
            self._load_folder(video_dir)

    def _build_ui(self):
        pad = dict(padx=6, pady=3)

        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Button(top, text="テンプレートTRK", command=self._pick_template).pack(side="left")
        self.lbl_tmpl = ttk.Label(top, text="未選択", foreground="red")
        self.lbl_tmpl.pack(side="left", padx=6)
        ttk.Separator(top, orient="vertical").pack(side="left", fill="y", padx=6)
        ttk.Button(top, text="動画フォルダ", command=self._choose_folder).pack(side="left")
        self.lbl_file = ttk.Label(top, text="未選択", foreground="gray")
        self.lbl_file.pack(side="left", padx=6)
        self.lbl_prog = ttk.Label(top, text="")
        self.lbl_prog.pack(side="right")

        self.canvas = tk.Canvas(self, width=PREVIEW_W, height=PREVIEW_H,
                                bg="black", cursor="crosshair")
        self.canvas.pack(**pad)
        self.canvas.bind("<ButtonPress-1>", self._on_click)

        self.lbl_hint = ttk.Label(self, text="① テンプレートTRKを選択　② 動画フォルダを選択",
                                  foreground="gray", font=("", 10))
        self.lbl_hint.pack()

        btn = ttk.Frame(self)
        btn.pack(**pad)
        self.btn_undo  = ttk.Button(btn, text="↩ 1つ戻す", command=self._undo, state="disabled")
        self.btn_reset = ttk.Button(btn, text="リセット",   command=self._reset, state="disabled")
        self.btn_skip  = ttk.Button(btn, text="スキップ",   command=self._skip,  state="disabled")
        self.btn_undo.pack(side="left", padx=3)
        self.btn_reset.pack(side="left", padx=3)
        self.btn_skip.pack(side="left", padx=3)

        self.lbl_status = ttk.Label(self, text="", foreground="blue")
        self.lbl_status.pack()

    # ---- template ----
    def _pick_template(self):
        p = filedialog.askopenfilename(
            title="テンプレートにするTRKファイルを選択",
            filetypes=[("TRKファイル", "*.trk"), ("すべて", "*.*")])
        if p:
            self.template_path = p
            self.lbl_tmpl.config(text=Path(p).name, foreground="green")

    # ---- folder ----
    def _choose_folder(self):
        d = filedialog.askdirectory(title="動画フォルダを選択")
        if d:
            self._load_folder(d)

    def _load_folder(self, d):
        if not self.template_path:
            messagebox.showwarning("テンプレート未選択",
                "先にテンプレートTRKファイルを選択してください。")
            return
        exts = ("*.mp4","*.MP4","*.mov","*.MOV","*.avi","*.AVI","*.mkv","*.MKV")
        vids = []
        for e in exts:
            vids.extend(glob.glob(os.path.join(d, e)))
        vids.sort()
        if not vids:
            messagebox.showwarning("動画なし", "動画ファイルが見つかりません。")
            return
        self.videos = vids
        self.video_idx = 0
        self.lbl_file.config(text=Path(d).name, foreground="black")
        self._load_current_video()

    def _load_current_video(self):
        if self.video_idx >= len(self.videos):
            messagebox.showinfo("完了", "全ての動画を処理しました！")
            return
        path = self.videos[self.video_idx]
        cap = cv2.VideoCapture(path)
        ret, frame = cap.read()
        if not ret:
            messagebox.showerror("エラー", f"読み込めません:\n{path}")
            cap.release()
            return
        self.first_frame = frame
        self.frame_h, self.frame_w = frame.shape[:2]
        self.fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        self._reset()
        self.lbl_prog.config(text=f"{self.video_idx+1} / {len(self.videos)}")
        self.btn_skip.config(state="normal")
        self._update_hint()
        self._redraw()

    # ---- canvas ----
    def _canvas_to_frame(self, cx, cy):
        scale = min(PREVIEW_W / self.frame_w, PREVIEW_H / self.frame_h)
        nw, nh = int(self.frame_w*scale), int(self.frame_h*scale)
        ox, oy = (PREVIEW_W-nw)//2, (PREVIEW_H-nh)//2
        fx = max(0, min(self.frame_w-1, int((cx-ox)/scale)))
        fy = max(0, min(self.frame_h-1, int((cy-oy)/scale)))
        return fx, fy

    def _on_click(self, event):
        if self.first_frame is None:
            return
        fx, fy = self._canvas_to_frame(event.x, event.y)
        if self.phase == "markers":
            self.markers.append((fx, fy))
            self.btn_undo.config(state="normal")
            self.btn_reset.config(state="normal")
            if len(self.markers) == 8:
                self.phase = "calib"
        elif self.phase == "calib":
            self.calib_pts.append((fx, fy))
            if len(self.calib_pts) == 2:
                self.phase = "done"
                self._generate_and_launch()
        self._update_hint()
        self._redraw()

    def _update_hint(self):
        if self.first_frame is None:
            return
        if self.phase == "markers":
            n = len(self.markers)
            self.lbl_hint.config(
                text=f"マーカー {n+1}/8 をクリック（残り {8-n} 個）",
                foreground="black")
        elif self.phase == "calib":
            c = len(self.calib_pts)
            self.lbl_hint.config(
                text=f"基準点 {c+1}/2 をクリック（隣り合うマーカー2つ → 10cm基準）",
                foreground="darkblue")
        else:
            self.lbl_hint.config(text="生成完了！Trackerが起動します。", foreground="green")

    def _redraw(self):
        if self.first_frame is None:
            return
        frame = self.first_frame.copy()
        scale = min(PREVIEW_W/self.frame_w, PREVIEW_H/self.frame_h)
        nw, nh = int(self.frame_w*scale), int(self.frame_h*scale)
        for i, (mx, my) in enumerate(self.markers):
            color = MARKER_COLORS_BGR[i % len(MARKER_COLORS_BGR)]
            cv2.drawMarker(frame, (mx, my), color, cv2.MARKER_CROSS, 20, 2)
            cv2.putText(frame, chr(65+i), (mx+8, my-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        for i, (px, py) in enumerate(self.calib_pts):
            cv2.circle(frame, (px, py), 8, (0,255,255), 2)
            cv2.putText(frame, f"C{i+1}", (px+10, py-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)
        if len(self.calib_pts) == 2:
            cv2.line(frame, self.calib_pts[0], self.calib_pts[1], (0,255,255), 1)
        rgb = cv2.cvtColor(cv2.resize(frame, (nw, nh)), cv2.COLOR_BGR2RGB)
        full = Image.new("RGB", (PREVIEW_W, PREVIEW_H), (0,0,0))
        full.paste(Image.fromarray(rgb), ((PREVIEW_W-nw)//2, (PREVIEW_H-nh)//2))
        self._cimg = ImageTk.PhotoImage(full)
        self.canvas.create_image(0, 0, anchor="nw", image=self._cimg)

    def _undo(self):
        if self.phase == "done":
            self.phase = "calib"
        if self.phase == "calib" and self.calib_pts:
            self.calib_pts.pop()
            if not self.calib_pts:
                self.phase = "markers"
        elif self.phase == "markers" and self.markers:
            self.markers.pop()
        self._update_hint()
        self._redraw()

    def _reset(self):
        self.phase = "markers"
        self.markers = []
        self.calib_pts = []
        self.btn_undo.config(state="disabled")
        self._update_hint()
        self._redraw()

    def _skip(self):
        self.video_idx += 1
        self._load_current_video()

    def _generate_and_launch(self):
        video_path = self.videos[self.video_idx]
        trk_path = str(Path(video_path).with_suffix(".trk"))
        try:
            xml = make_trk_from_template(
                self.template_path, video_path,
                self.markers, self.calib_pts[0], self.calib_pts[1],
                self.frame_count, self.fps, self.frame_w, self.frame_h)
            with open(trk_path, "w", encoding="utf-8") as f:
                f.write(xml)
        except Exception as e:
            messagebox.showerror("生成エラー", str(e))
            return

        self.lbl_status.config(
            text=f"TRK生成: {Path(trk_path).name}  →  Tracker起動中...")

        tracker_exe = r"C:\Program Files\Tracker\Tracker.exe"
        java_exe    = r"C:\Program Files\Tracker\OpenJDK-21.0.5.jre\bin\java.exe"
        tracker_jar = r"C:\Program Files\Tracker\tracker-6.3.4.jar"
        if os.path.exists(tracker_exe):
            subprocess.Popen([tracker_exe, trk_path])
        elif os.path.exists(java_exe) and os.path.exists(tracker_jar):
            subprocess.Popen([java_exe, "-jar", tracker_jar, trk_path])
        else:
            messagebox.showwarning("Tracker未検出",
                f"Trackerが見つかりませんでした。\n手動で開いてください:\n{trk_path}")

        self.video_idx += 1
        self.after(1500, self._load_current_video)


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else None
    app = App(video_dir=folder)
    app.mainloop()
