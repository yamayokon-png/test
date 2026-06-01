#!/usr/bin/env python3
"""
Tracker Semi-Auto Tool
----------------------
動画を順番に表示し、マーカー8個＋基準2点をクリックするだけで
TRKファイルを自動生成してTrackerを起動する。

Usage: python tracker_auto.py [動画フォルダ]
"""

import os
import sys
import glob
import subprocess
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import xml.etree.ElementTree as ET
import xml.dom.minidom
import csv

import cv2
import numpy as np
from PIL import Image, ImageTk

# ---- Tracker の場所 ----
TRACKER_JAR = r"C:\Program Files\Tracker\tracker-6.3.4.jar"
JAVA_EXE    = r"C:\Program Files\Tracker\OpenJDK-21.0.5.jre\bin\java.exe"
CALIBRATION_LENGTH_M = 0.10   # マーカー間 10cm = 0.10m

PREVIEW_W = 800
PREVIEW_H = 450

# -----------------------------------------------------------------------
# TRK XML 生成
# -----------------------------------------------------------------------

def make_trk(video_path: str,
             markers: list,        # [(x,y), ...] 8点 pixel座標
             calib_p1: tuple,      # (x,y) pixel
             calib_p2: tuple,      # (x,y) pixel
             frame_count: int,
             fps: float,
             width: int,
             height: int) -> str:
    """TRK XML文字列を返す"""

    # ---- スケール計算 ----
    # Tracker の xscale = pixels_per_meter
    dx = calib_p2[0] - calib_p1[0]
    dy = calib_p2[1] - calib_p1[1]
    calib_px = (dx**2 + dy**2) ** 0.5
    pixels_per_meter = calib_px / CALIBRATION_LENGTH_M

    # ---- 原点 = 1番目のマーカー ----
    origin_x = float(markers[0][0])
    origin_y = float(height - markers[0][1])   # Tracker はY軸反転

    # ---- frame_times ----
    times = [i * (1000.0 / fps) for i in range(frame_count)]
    times_str = "{" + ",".join(f"{t:.3f}" for t in times) + "}"

    lines = []
    lines.append('<?xml version="1.0" encoding="UTF-8"?>')
    lines.append('<object class="org.opensourcephysics.cabrillo.tracker.TrackerPanel">')
    lines.append(f'  <property name="semantic_version" type="string">6.3.4</property>')
    lines.append(f'  <property name="width" type="double">{width}.0</property>')
    lines.append(f'  <property name="height" type="double">{height}.0</property>')

    # videoclip
    lines.append('  <property name="videoclip" type="object">')
    lines.append('  <object class="org.opensourcephysics.media.core.VideoClip">')
    lines.append('    <property name="video" type="object">')
    lines.append('    <object class="org.opensourcephysics.media.xuggle.XuggleVideo">')
    lines.append(f'      <property name="path" type="string">{Path(video_path).name}</property>')
    lines.append('      <property name="start_times" type="array" class="[D">')
    lines.append(f'        <property name="array" type="string">{times_str}</property>')
    lines.append('      </property>')
    lines.append(f'      <property name="duration" type="double">{frame_count/fps:.3f}</property>')
    lines.append(f'      <property name="frame_count" type="int">{frame_count}</property>')
    lines.append(f'      <property name="frame_rate" type="int">{int(fps)}</property>')
    lines.append('      <property name="platform" type="string">Java</property>')
    lines.append('    </object>')
    lines.append('    </property>')
    lines.append(f'    <property name="video_framecount" type="int">{frame_count}</property>')
    lines.append('    <property name="startframe" type="int">0</property>')
    lines.append('    <property name="stepsize" type="int">1</property>')
    lines.append(f'    <property name="stepcount" type="int">{frame_count}</property>')
    lines.append('    <property name="starttime" type="double">0.0</property>')
    lines.append('    <property name="readout" type="string">frame</property>')
    lines.append('    <property name="playallsteps" type="boolean">true</property>')
    lines.append('  </object>')
    lines.append('  </property>')

    # coords
    lines.append('  <property name="coords" type="object">')
    lines.append('  <object class="org.opensourcephysics.media.core.ImageCoordSystem">')
    lines.append('    <property name="fixedorigin" type="boolean">true</property>')
    lines.append('    <property name="fixedangle" type="boolean">true</property>')
    lines.append('    <property name="fixedscale" type="boolean">true</property>')
    lines.append('    <property name="locked" type="boolean">false</property>')
    lines.append('    <property name="framedata" type="array" class="[Lorg.opensourcephysics.media.core.ImageCoordSystem$FrameData;">')
    lines.append('      <property name="[0]" type="object">')
    lines.append('      <object class="org.opensourcephysics.media.core.ImageCoordSystem$FrameData">')
    lines.append(f'        <property name="xorigin" type="double">{origin_x}</property>')
    lines.append(f'        <property name="yorigin" type="double">{height - origin_y}</property>')
    lines.append('        <property name="angle" type="double">0.0</property>')
    lines.append(f'        <property name="xscale" type="double">{pixels_per_meter}</property>')
    lines.append(f'        <property name="yscale" type="double">{pixels_per_meter}</property>')
    lines.append('      </object>')
    lines.append('      </property>')
    lines.append('    </property>')
    lines.append('  </object>')
    lines.append('  </property>')

    lines.append('  <property name="length_unit" type="string">m</property>')
    lines.append('  <property name="mass_unit" type="string">kg</property>')
    lines.append('  <property name="units_visible" type="boolean">true</property>')
    lines.append('  <property name="tracks" type="collection" class="java.util.ArrayList">')

    # 座標軸
    lines.append('    <property name="item" type="object">')
    lines.append('    <object class="org.opensourcephysics.cabrillo.tracker.CoordAxes">')
    lines.append('      <property name="name" type="string">軸</property>')
    lines.append('      <property name="visible" type="boolean">true</property>')
    lines.append('    </object>')
    lines.append('    </property>')

    # キャリブレーションスティック
    cx1, cy1 = float(calib_p1[0]), float(height - calib_p1[1])
    cx2, cy2 = float(calib_p2[0]), float(height - calib_p2[1])
    lines.append('    <property name="item" type="object">')
    lines.append('    <object class="org.opensourcephysics.cabrillo.tracker.TapeMeasure">')
    lines.append('      <property name="name" type="string">キャリブレーションスティック A</property>')
    lines.append('      <property name="footprint" type="string">Footprint.BoldDoubleTarget</property>')
    lines.append('      <property name="visible" type="boolean">true</property>')
    lines.append('      <property name="fixedtape" type="boolean">true</property>')
    lines.append('      <property name="fixedlength" type="boolean">true</property>')
    lines.append('      <property name="stickmode" type="boolean">true</property>')
    lines.append('      <property name="framedata" type="array" class="[Lorg.opensourcephysics.cabrillo.tracker.TapeMeasure$FrameData;">')
    lines.append('        <property name="[0]" type="object">')
    lines.append('        <object class="org.opensourcephysics.cabrillo.tracker.TapeMeasure$FrameData">')
    lines.append(f'          <property name="x1" type="double">{cx1}</property>')
    lines.append(f'          <property name="y1" type="double">{cy1}</property>')
    lines.append(f'          <property name="x2" type="double">{cx2}</property>')
    lines.append(f'          <property name="y2" type="double">{cy2}</property>')
    lines.append('        </object>')
    lines.append('        </property>')
    lines.append('      </property>')
    lines.append(f'      <property name="worldlengths" type="array" class="[Ljava.lang.Double;">')
    lines.append(f'        <property name="[0]" type="double">{CALIBRATION_LENGTH_M}</property>')
    lines.append('      </property>')
    lines.append('    </object>')
    lines.append('    </property>')

    # マーカー 8個
    colors = [
        (255,0,0),(0,200,0),(0,0,255),(200,150,0),
        (150,0,200),(0,180,180),(255,100,0),(100,100,100)
    ]
    for i, (mx, my) in enumerate(markers):
        r, g, b = colors[i % len(colors)]
        tx = float(mx)
        ty = float(height - my)   # Y反転
        lines.append('    <property name="item" type="object">')
        lines.append('    <object class="org.opensourcephysics.cabrillo.tracker.PointMass">')
        lines.append('      <property name="mass" type="double">1.0</property>')
        lines.append(f'      <property name="name" type="string">質量 {chr(65+i)}</property>')
        lines.append('      <property name="color" type="object">')
        lines.append('      <object class="java.awt.Color">')
        lines.append(f'        <property name="red" type="int">{r}</property>')
        lines.append(f'        <property name="green" type="int">{g}</property>')
        lines.append(f'        <property name="blue" type="int">{b}</property>')
        lines.append('        <property name="alpha" type="int">255</property>')
        lines.append('      </object>')
        lines.append('      </property>')
        lines.append('      <property name="footprint" type="string">Footprint.Diamond</property>')
        lines.append('      <property name="visible" type="boolean">true</property>')
        lines.append('      <property name="trail" type="boolean">true</property>')
        lines.append('      <property name="framedata" type="array" class="[Lorg.opensourcephysics.cabrillo.tracker.PointMass$FrameData;">')
        lines.append('        <property name="[0]" type="object">')
        lines.append('        <object class="org.opensourcephysics.cabrillo.tracker.PointMass$FrameData">')
        lines.append(f'          <property name="x" type="double">{tx}</property>')
        lines.append(f'          <property name="y" type="double">{ty}</property>')
        lines.append('        </object>')
        lines.append('        </property>')
        lines.append('      </property>')
        lines.append('    </object>')
        lines.append('    </property>')

    lines.append('  </property>')
    lines.append('</object>')
    return "\n".join(lines)

# -----------------------------------------------------------------------
# GUI
# -----------------------------------------------------------------------

MARKER_COLORS_BGR = [
    (0,0,255),(0,200,0),(255,0,0),(0,150,200),
    (200,0,150),(180,180,0),(0,100,255),(100,100,100)
]

class App(tk.Tk):
    def __init__(self, video_dir=None):
        super().__init__()
        self.title("Tracker 半自動ツール")
        self.resizable(False, False)

        self.videos = []
        self.video_idx = 0
        self.cap = None
        self.first_frame = None
        self.frame_w = self.frame_h = 0
        self.fps = 30.0
        self.frame_count = 0
        self._scale = 1.0

        # クリックで集めるポイント
        # フェーズ: "markers"(8個) → "calib"(2個)
        self.phase = "markers"
        self.markers = []    # pixel座標
        self.calib_pts = []  # pixel座標

        self._build_ui()

        if video_dir:
            self._load_folder(video_dir)

    # ------------------------------------------------------------------ UI --

    def _build_ui(self):
        pad = dict(padx=6, pady=4)

        top = ttk.Frame(self)
        top.pack(fill="x", **pad)
        ttk.Button(top, text="フォルダを開く", command=self._choose_folder).pack(side="left")
        self.lbl_file = ttk.Label(top, text="フォルダ未選択", foreground="gray")
        self.lbl_file.pack(side="left", padx=8)
        self.lbl_prog = ttk.Label(top, text="")
        self.lbl_prog.pack(side="right")

        self.canvas = tk.Canvas(self, width=PREVIEW_W, height=PREVIEW_H,
                                bg="black", cursor="crosshair")
        self.canvas.pack(**pad)
        self.canvas.bind("<ButtonPress-1>", self._on_click)
        self._cimg = None

        self.lbl_hint = ttk.Label(self, text="フォルダを選択してください。",
                                  foreground="gray", font=("", 10))
        self.lbl_hint.pack()

        btn = ttk.Frame(self)
        btn.pack(**pad)
        self.btn_undo  = ttk.Button(btn, text="↩ 1つ戻す",   command=self._undo,   state="disabled")
        self.btn_reset = ttk.Button(btn, text="リセット",     command=self._reset,  state="disabled")
        self.btn_skip  = ttk.Button(btn, text="この動画をスキップ", command=self._skip, state="disabled")
        self.btn_undo.pack(side="left", padx=4)
        self.btn_reset.pack(side="left", padx=4)
        self.btn_skip.pack(side="left", padx=4)

        self.lbl_status = ttk.Label(self, text="", foreground="blue")
        self.lbl_status.pack()

    # -------------------------------------------------------- folder / load --

    def _choose_folder(self):
        d = filedialog.askdirectory(title="動画が入っているフォルダを選択")
        if d:
            self._load_folder(d)

    def _load_folder(self, d):
        exts = ("*.mp4","*.MP4","*.mov","*.MOV","*.avi","*.AVI","*.mkv","*.MKV")
        vids = []
        for e in exts:
            vids.extend(glob.glob(os.path.join(d, e)))
        vids.sort()
        if not vids:
            messagebox.showwarning("動画なし", f"{d} に動画ファイルが見つかりませんでした。")
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
        if self.cap:
            self.cap.release()
        self.cap = cv2.VideoCapture(path)
        ret, frame = self.cap.read()
        if not ret:
            messagebox.showerror("エラー", f"動画を読み込めません:\n{path}")
            return

        self.first_frame = frame
        self.frame_h, self.frame_w = frame.shape[:2]
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))

        self._reset()
        total = len(self.videos)
        self.lbl_prog.config(text=f"{self.video_idx+1} / {total}")
        self.btn_skip.config(state="normal")
        self._update_hint()
        self._redraw()

    # --------------------------------------------------------- click logic --

    def _canvas_to_frame(self, cx, cy):
        scale = min(PREVIEW_W / self.frame_w, PREVIEW_H / self.frame_h)
        nw = int(self.frame_w * scale)
        nh = int(self.frame_h * scale)
        ox = (PREVIEW_W - nw) // 2
        oy = (PREVIEW_H - nh) // 2
        fx = int((cx - ox) / scale)
        fy = int((cy - oy) / scale)
        fx = max(0, min(self.frame_w - 1, fx))
        fy = max(0, min(self.frame_h - 1, fy))
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
        n = len(self.markers)
        if self.phase == "markers":
            self.lbl_hint.config(
                text=f"マーカー {n+1}/8 をクリック　（残り {8-n} 個）",
                foreground="black")
        elif self.phase == "calib":
            c = len(self.calib_pts)
            self.lbl_hint.config(
                text=f"基準点 {c+1}/2 をクリック　（隣り合う2つのマーカーを選択→10cm基準）",
                foreground="darkblue")
        else:
            self.lbl_hint.config(text="生成完了！　Trackerが起動します。", foreground="green")

    # ------------------------------------------------------------ redraw --

    def _redraw(self):
        if self.first_frame is None:
            return
        frame = self.first_frame.copy()
        scale = min(PREVIEW_W / self.frame_w, PREVIEW_H / self.frame_h)
        nw = int(self.frame_w * scale)
        nh = int(self.frame_h * scale)

        # マーカー描画
        for i, (mx, my) in enumerate(self.markers):
            color = MARKER_COLORS_BGR[i % len(MARKER_COLORS_BGR)]
            cv2.drawMarker(frame, (mx, my), color, cv2.MARKER_CROSS, 20, 2)
            cv2.putText(frame, chr(65+i), (mx+8, my-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # キャリブ描画
        for i, (px, py) in enumerate(self.calib_pts):
            cv2.circle(frame, (px, py), 8, (0, 255, 255), 2)
            cv2.putText(frame, f"C{i+1}", (px+10, py-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0,255,255), 2)
        if len(self.calib_pts) == 2:
            cv2.line(frame, self.calib_pts[0], self.calib_pts[1], (0,255,255), 1)

        rgb = cv2.cvtColor(cv2.resize(frame, (nw, nh)), cv2.COLOR_BGR2RGB)
        canvas_img = Image.fromarray(rgb)
        full = Image.new("RGB", (PREVIEW_W, PREVIEW_H), (0,0,0))
        full.paste(canvas_img, ((PREVIEW_W-nw)//2, (PREVIEW_H-nh)//2))
        self._cimg = ImageTk.PhotoImage(full)
        self.canvas.create_image(0, 0, anchor="nw", image=self._cimg)

    # ------------------------------------------------------- undo / reset --

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

    # -------------------------------------------------- generate & launch --

    def _generate_and_launch(self):
        video_path = self.videos[self.video_idx]
        trk_path = str(Path(video_path).with_suffix(".trk"))

        xml_str = make_trk(
            video_path=video_path,
            markers=self.markers,
            calib_p1=self.calib_pts[0],
            calib_p2=self.calib_pts[1],
            frame_count=self.frame_count,
            fps=self.fps,
            width=self.frame_w,
            height=self.frame_h,
        )
        with open(trk_path, "w", encoding="utf-8") as f:
            f.write(xml_str)

        self.lbl_status.config(text=f"TRK生成: {Path(trk_path).name}  →  Tracker起動中...")

        # Tracker を起動
        if os.path.exists(JAVA_EXE) and os.path.exists(TRACKER_JAR):
            subprocess.Popen([JAVA_EXE, "-jar", TRACKER_JAR, trk_path])
        elif os.path.exists(r"C:\Program Files\Tracker\Tracker.exe"):
            subprocess.Popen([r"C:\Program Files\Tracker\Tracker.exe", trk_path])
        else:
            messagebox.showwarning("Tracker未検出",
                f"Trackerが見つかりませんでした。\n手動で以下を開いてください:\n{trk_path}")

        # 次の動画へ
        self.video_idx += 1
        self.after(1500, self._load_current_video)


# -----------------------------------------------------------------------

if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else None
    app = App(video_dir=folder)
    app.mainloop()
