#!/usr/bin/env python3
"""
Track a marker in a video and output XY coordinates as a scatter plot.

Usage:
  python track_marker.py <video_file> [--output result.png] [--csv coords.csv]

On startup, the first frame is shown. Click the marker to set the initial
position. The color at that point is sampled automatically and used for
tracking. Press Enter or Space to confirm, Esc to cancel.
"""

import argparse
import sys
import csv
import cv2
import numpy as np
import matplotlib.pyplot as plt


# --------------------------------------------------------------------------- #
# Interactive initial-position picker
# --------------------------------------------------------------------------- #

_click_point = None
_preview_frame = None


def _mouse_callback(event, x, y, flags, param):
    global _click_point, _preview_frame
    if event == cv2.EVENT_LBUTTONDOWN:
        _click_point = (x, y)
        # Draw crosshair on preview
        _preview_frame = param["frame"].copy()
        cv2.drawMarker(_preview_frame, (x, y), (0, 255, 0),
                       cv2.MARKER_CROSS, 20, 2)
        cv2.imshow(param["win"], _preview_frame)


def pick_initial_position(first_frame):
    """Show first frame and let the user click the marker. Returns (x, y)."""
    global _click_point, _preview_frame

    win = "Click the marker, then press Enter/Space (Esc to quit)"
    _preview_frame = first_frame.copy()
    _click_point = None

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win, _mouse_callback, {"frame": first_frame, "win": win})
    cv2.imshow(win, _preview_frame)
    print(">> Click on the marker in the window, then press Enter or Space.")

    while True:
        key = cv2.waitKey(20) & 0xFF
        if key in (13, 32):  # Enter or Space
            if _click_point is None:
                print("   No point selected yet — please click the marker first.")
                continue
            break
        if key == 27:  # Esc
            cv2.destroyAllWindows()
            print("Cancelled by user.")
            sys.exit(0)

    cv2.destroyAllWindows()
    print(f"Initial position set to: {_click_point}")
    return _click_point


# --------------------------------------------------------------------------- #
# Color-range detector (built from sampled pixel)
# --------------------------------------------------------------------------- #

def build_hsv_mask(frame, point, radius=10, hue_tol=15, sat_min=80, val_min=80):
    """
    Sample HSV around `point` and build a tight color mask for the whole frame.
    Returns the binary mask.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    x, y = point
    patch = hsv[max(0, y - radius):y + radius + 1,
                max(0, x - radius):x + radius + 1]

    mean_h = float(np.median(patch[:, :, 0]))
    mean_s = float(np.median(patch[:, :, 1]))
    mean_v = float(np.median(patch[:, :, 2]))

    # Clamp sat/val floors so we don't accidentally match grey areas
    s_lo = max(sat_min, int(mean_s * 0.5))
    v_lo = max(val_min, int(mean_v * 0.5))

    h_lo = (mean_h - hue_tol) % 180
    h_hi = (mean_h + hue_tol) % 180

    if h_lo <= h_hi:
        mask = cv2.inRange(hsv,
                           np.array([h_lo, s_lo, v_lo]),
                           np.array([h_hi, 255, 255]))
    else:
        # Hue wraps around 0/180 (e.g. red)
        mask1 = cv2.inRange(hsv,
                            np.array([h_lo, s_lo, v_lo]),
                            np.array([179, 255, 255]))
        mask2 = cv2.inRange(hsv,
                            np.array([0, s_lo, v_lo]),
                            np.array([h_hi, 255, 255]))
        mask = cv2.bitwise_or(mask1, mask2)

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def find_closest_centroid(mask, reference_point):
    """Find the contour centroid closest to reference_point."""
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    best = None
    best_dist = float("inf")
    rx, ry = reference_point

    for cnt in contours:
        if cv2.contourArea(cnt) < 50:
            continue
        M = cv2.moments(cnt)
        if M["m00"] == 0:
            continue
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        dist = (cx - rx) ** 2 + (cy - ry) ** 2
        if dist < best_dist:
            best_dist = dist
            best = (cx, cy)

    return best


# --------------------------------------------------------------------------- #
# Main tracking loop
# --------------------------------------------------------------------------- #

def track_video(video_path, initial_point):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Cannot open video file: {video_path}", file=sys.stderr)
        sys.exit(1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    # Sample color from the initial frame at the clicked point
    ret, first_frame = cap.read()
    if not ret:
        print("Error: Cannot read first frame.", file=sys.stderr)
        sys.exit(1)

    # Re-sample HSV params from first frame
    hsv_sample = cv2.cvtColor(first_frame, cv2.COLOR_BGR2HSV)
    x0, y0 = initial_point
    patch = hsv_sample[max(0, y0 - 10):y0 + 11, max(0, x0 - 10):x0 + 11]
    hue_tol = 15
    sat_min = 80
    val_min = 80

    coords = []
    prev_point = initial_point
    frame_idx = 0

    print(f"Processing video: {video_path}")
    print(f"Total frames: {total_frames}, FPS: {fps:.1f}")

    # Rewind to start
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        mask = build_hsv_mask(frame, prev_point, radius=10,
                               hue_tol=hue_tol, sat_min=sat_min, val_min=val_min)
        result = find_closest_centroid(mask, prev_point)

        if result:
            cx, cy = result
            prev_point = (cx, cy)
            cy_flipped = height - cy
            time_sec = frame_idx / fps if fps > 0 else frame_idx
            coords.append((frame_idx, cx, cy_flipped, time_sec))

        frame_idx += 1
        if frame_idx % 100 == 0:
            pct = frame_idx / total_frames * 100 if total_frames else 0
            print(f"  {frame_idx}/{total_frames} ({pct:.0f}%), detected: {len(coords)} pts")

    cap.release()
    print(f"Done. Marker detected in {len(coords)}/{frame_idx} frames.")
    return coords, height


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

def save_csv(coords, path):
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["frame", "x", "y", "time_sec"])
        writer.writerows(coords)
    print(f"Coordinates saved to: {path}")


def plot_scatter(coords, output_path, video_path):
    if not coords:
        print("No marker detected — cannot create scatter plot.", file=sys.stderr)
        sys.exit(1)

    xs = [c[1] for c in coords]
    ys = [c[2] for c in coords]
    times = [c[3] for c in coords]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    sc = axes[0].scatter(xs, ys, c=times, cmap="viridis", s=10, alpha=0.7)
    axes[0].plot(xs, ys, color="gray", linewidth=0.5, alpha=0.4)
    axes[0].set_xlabel("X (px)")
    axes[0].set_ylabel("Y (px, bottom-origin)")
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

    fig.suptitle(f"Marker Tracking — {video_path}", fontsize=11)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"Scatter plot saved to: {output_path}")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #

def main():
    parser = argparse.ArgumentParser(
        description="Track a marker in video by clicking its initial position.")
    parser.add_argument("video", help="Path to input video file")
    parser.add_argument("--output", default="marker_scatter.png",
                        help="Output scatter plot image (default: marker_scatter.png)")
    parser.add_argument("--csv", default="marker_coords.csv",
                        help="Output CSV file (default: marker_coords.csv)")
    parser.add_argument("--no-csv", action="store_true", help="Skip CSV output")
    parser.add_argument("--init", nargs=2, type=int, metavar=("X", "Y"),
                        help="Set initial position directly (skip interactive picker)")
    args = parser.parse_args()

    if args.init:
        initial_point = tuple(args.init)
        print(f"Initial position from argument: {initial_point}")
    else:
        # Show first frame for interactive picking
        cap = cv2.VideoCapture(args.video)
        if not cap.isOpened():
            print(f"Error: Cannot open {args.video}", file=sys.stderr)
            sys.exit(1)
        ret, first_frame = cap.read()
        cap.release()
        if not ret:
            print("Error: Cannot read first frame.", file=sys.stderr)
            sys.exit(1)
        initial_point = pick_initial_position(first_frame)

    coords, height = track_video(args.video, initial_point)

    if not args.no_csv:
        save_csv(coords, args.csv)

    plot_scatter(coords, args.output, args.video)


if __name__ == "__main__":
    main()
