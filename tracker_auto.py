#!/usr/bin/env python3
"""
Tracker 半自動ツール
動画ごとにマーカー8個＋基準2点をクリックするだけでTRKを生成してTrackerを起動する。
"""

import os, sys, glob, subprocess, tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import cv2
import numpy as np
from PIL import Image, ImageTk

CALIBRATION_LENGTH_M = 0.10
PREVIEW_W, PREVIEW_H = 800, 450
COLORS_BGR = [
    (0,0,255),(0,200,0),(255,0,0),(0,150,200),
    (200,0,150),(180,180,0),(0,100,255),(80,80,80)
]
COLORS_RGB = [(r,g,b) for (b,g,r) in COLORS_BGR]

TRACKER_EXE = r"C:\Program Files\Tracker\Tracker.exe"
JAVA_EXE    = r"C:\Program Files\Tracker\OpenJDK-21.0.5.jre\bin\java.exe"
TRACKER_JAR = r"C:\Program Files\Tracker\tracker-6.3.4.jar"

# -----------------------------------------------------------------------
# TRK 生成
# -----------------------------------------------------------------------

def make_trk(video_path, markers, calib_p1, calib_p2,
             frame_count, fps, width, height):

    dx = calib_p2[0] - calib_p1[0]
    dy = calib_p2[1] - calib_p1[1]
    ppm = ((dx**2 + dy**2) ** 0.5) / CALIBRATION_LENGTH_M

    # frame times (ms)
    times = ",".join(str(round(i * 1000.0 / fps, 3)) for i in range(frame_count))
    times_str = "{" + times + "}"

    # 座標系原点 = マーカー1番目（スクリーン座標そのまま）
    ox, oy = float(markers[0][0]), float(markers[0][1])

    # キャリブレーション（スクリーン座標そのまま）
    cx1, cy1 = float(calib_p1[0]), float(calib_p1[1])
    cx2, cy2 = float(calib_p2[0]), float(calib_p2[1])

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<object class="org.opensourcephysics.cabrillo.tracker.TrackerPanel">',
        f'  <property name="semantic_version" type="string">6.3.4</property>',
        f'  <property name="width" type="double">{width}.0</property>',
        f'  <property name="height" type="double">{height}.0</property>',
        '  <property name="videoclip" type="object">',
        '  <object class="org.opensourcephysics.media.core.VideoClip">',
        '    <property name="video" type="object">',
        '    <object class="org.opensourcephysics.media.xuggle.XuggleVideo">',
        f'      <property name="path" type="string">{Path(video_path).name}</property>',
        '      <property name="start_times" type="array" class="[D">',
        f'        <property name="array" type="string">{times_str}</property>',
        '      </property>',
        f'      <property name="duration" type="double">{frame_count/fps:.3f}</property>',
        f'      <property name="frame_count" type="int">{frame_count}</property>',
        f'      <property name="frame_rate" type="int">{int(round(fps))}</property>',
        '      <property name="platform" type="string">Java</property>',
        '    </object>',
        '    </property>',
        f'    <property name="video_framecount" type="int">{frame_count}</property>',
        '    <property name="startframe" type="int">0</property>',
        '    <property name="stepsize" type="int">1</property>',
        f'    <property name="stepcount" type="int">{frame_count}</property>',
        '    <property name="starttime" type="double">0.0</property>',
        '    <property name="readout" type="string">frame</property>',
        '    <property name="playallsteps" type="boolean">true</property>',
        '  </object>',
        '  </property>',
        '  <property name="clipcontrol" type="object">',
        '  <object class="org.opensourcephysics.media.core.StepperClipControl">',
        '    <property name="rate" type="double">1.0</property>',
        f'    <property name="delta_t" type="double">{1000.0/fps}</property>',
        f'    <property name="frame" type="int">{frame_count-1}</property>',
        '  </object>',
        '  </property>',
        '  <property name="coords" type="object">',
        '  <object class="org.opensourcephysics.media.core.ImageCoordSystem">',
        '    <property name="fixedorigin" type="boolean">true</property>',
        '    <property name="fixedangle" type="boolean">true</property>',
        '    <property name="fixedscale" type="boolean">true</property>',
        '    <property name="locked" type="boolean">false</property>',
        '    <property name="framedata" type="array" class="[Lorg.opensourcephysics.media.core.ImageCoordSystem$FrameData;">',
        '      <property name="[0]" type="object">',
        '      <object class="org.opensourcephysics.media.core.ImageCoordSystem$FrameData">',
        f'        <property name="xorigin" type="double">{ox}</property>',
        f'        <property name="yorigin" type="double">{oy}</property>',
        '        <property name="angle" type="double">0.0</property>',
        f'        <property name="xscale" type="double">{ppm}</property>',
        f'        <property name="yscale" type="double">{ppm}</property>',
        '      </object>',
        '      </property>',
        '    </property>',
        '  </object>',
        '  </property>',
        '  <property name="length_unit" type="string">m</property>',
        '  <property name="mass_unit" type="string">kg</property>',
        '  <property name="units_visible" type="boolean">true</property>',
        '  <property name="tracks" type="collection" class="java.util.ArrayList">',
        # 座標軸
        '    <property name="item" type="object">',
        '    <object class="org.opensourcephysics.cabrillo.tracker.CoordAxes">',
        '      <property name="name" type="string">軸</property>',
        '      <property name="visible" type="boolean">true</property>',
        '    </object>',
        '    </property>',
        # キャリブレーションスティック
        '    <property name="item" type="object">',
        '    <object class="org.opensourcephysics.cabrillo.tracker.TapeMeasure">',
        '      <property name="name" type="string">キャリブレーションスティック A</property>',
        '      <property name="footprint" type="string">Footprint.BoldDoubleTarget</property>',
        '      <property name="visible" type="boolean">true</property>',
        '      <property name="fixedtape" type="boolean">true</property>',
        '      <property name="fixedlength" type="boolean">true</property>',
        '      <property name="stickmode" type="boolean">true</property>',
        '      <property name="framedata" type="array" class="[Lorg.opensourcephysics.cabrillo.tracker.TapeMeasure$FrameData;">',
        '        <property name="[0]" type="object">',
        '        <object class="org.opensourcephysics.cabrillo.tracker.TapeMeasure$FrameData">',
        f'          <property name="x1" type="double">{cx1}</property>',
        f'          <property name="y1" type="double">{cy1}</property>',
        f'          <property name="x2" type="double">{cx2}</property>',
        f'          <property name="y2" type="double">{cy2}</property>',
        '        </object>',
        '        </property>',
        '      </property>',
        '      <property name="worldlengths" type="array" class="[Ljava.lang.Double;">',
        f'        <property name="[0]" type="double">{CALIBRATION_LENGTH_M}</property>',
        '      </property>',
        '    </object>',
        '    </property>',
    ]

    # マーカー 8個
    for i, (mx, my) in enumerate(markers):
        r, g, b = COLORS_RGB[i]
        lines += [
            '    <property name="item" type="object">',
            '    <object class="org.opensourcephysics.cabrillo.tracker.PointMass">',
            '      <property name="mass" type="double">1.0</property>',
            f'      <property name="name" type="string">質量 {chr(65+i)}</property>',
            '      <property name="color" type="object">',
            '      <object class="java.awt.Color">',
            f'        <property name="red" type="int">{r}</property>',
            f'        <property name="green" type="int">{g}</property>',
            f'        <property name="blue" type="int">{b}</property>',
            '        <property name="alpha" type="int">255</property>',
            '      </object>',
            '      </property>',
            '      <property name="footprint" type="string">Footprint.Diamond</property>',
            '      <property name="visible" type="boolean">true</property>',
            '      <property name="trail" type="boolean">true</property>',
            '      <property name="framedata" type="array" class="[Lorg.opensourcephysics.cabrillo.tracker.PointMass$FrameData;">',
            '        <property name="[0]" type="object">',
            '        <object class="org.opensourcephysics.cabrillo.tracker.PointMass$FrameData">',
            f'          <property name="x" type="double">{float(mx)}</property>',
            f'          <property name="y" type="double">{float(my)}</property>',
            '        </object>',
            '        </property>',
            '      </property>',
            '    </object>',
            '    </property>',
        ]

    lines += ['  </property>', '</object>']
    return "\n".join(lines)


# -----------------------------------------------------------------------
# GUI
# -----------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self, video_dir=None):
        super().__init__()
        self.title("Tracker 半自動ツール")
        self.resizable(False, False)
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
        ttk.Button(top, text="動画フォルダを開く", command=self._choose_folder).pack(side="left")
        self.lbl_file = ttk.Label(top, text="未選択", foreground="gray")
        self.lbl_file.pack(side="left", padx=6)
        self.lbl_prog = ttk.Label(top, text="")
        self.lbl_prog.pack(side="right")

        self.canvas = tk.Canvas(self, width=PREVIEW_W, height=PREVIEW_H,
                                bg="black", cursor="crosshair")
        self.canvas.pack(**pad)
        self.canvas.bind("<ButtonPress-1>", self._on_click)

        self.lbl_hint = ttk.Label(self, text="動画フォルダを選択してください。",
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

    def _choose_folder(self):
        d = filedialog.askdirectory(title="動画フォルダを選択")
        if d:
            self._load_folder(d)

    def _load_folder(self, d):
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

    def _canvas_to_frame(self, cx, cy):
        scale = min(PREVIEW_W/self.frame_w, PREVIEW_H/self.frame_h)
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
                text=f"マーカー {n+1}/8 をクリック（残り {8-n} 個）", foreground="black")
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
            c = COLORS_BGR[i % len(COLORS_BGR)]
            cv2.drawMarker(frame, (mx, my), c, cv2.MARKER_CROSS, 20, 2)
            cv2.putText(frame, chr(65+i), (mx+8, my-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, c, 2)
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
            xml = make_trk(video_path, self.markers,
                           self.calib_pts[0], self.calib_pts[1],
                           self.frame_count, self.fps, self.frame_w, self.frame_h)
            with open(trk_path, "w", encoding="utf-8") as f:
                f.write(xml)
        except Exception as e:
            messagebox.showerror("生成エラー", str(e))
            return

        self.lbl_status.config(text=f"TRK生成: {Path(trk_path).name} → Tracker起動中...")
        try:
            if os.path.exists(TRACKER_EXE):
                subprocess.Popen([TRACKER_EXE, trk_path])
            elif os.path.exists(JAVA_EXE) and os.path.exists(TRACKER_JAR):
                subprocess.Popen([JAVA_EXE, "-jar", TRACKER_JAR, trk_path])
            else:
                messagebox.showwarning("Tracker未検出",
                    f"TRKは生成しました:\n{trk_path}\n手動で開いてください。")
        except Exception as e:
            messagebox.showerror("起動エラー", str(e))

        self.video_idx += 1
        self.after(1500, self._load_current_video)


if __name__ == "__main__":
    folder = sys.argv[1] if len(sys.argv) > 1 else None
    app = App(video_dir=folder)
    app.mainloop()
