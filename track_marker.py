#!/usr/bin/env python3
"""
Track a red sticker/marker in a video and output XY coordinates as a scatter plot.
Usage: python track_marker.py <video_file> [--output result.png] [--csv coords.csv]
"""

import argparse
import sys
import csv
import cv2
import numpy as np
import matplotlib.pyplot as plt


def detect_red_marker(frame):
    """Detect red marker in frame using HSV color space. Returns (cx, cy) or None."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Red appears at both ends of hue spectrum in HSV
    lower_red1 = np.array([0, 100, 100])
    upper_red1 = np.array([10, 255, 255])
    lower_red2 = np.array([160, 100, 100])
    upper_red2 = np.array([180, 255, 255])

    mask1 = cv2.inRange(hsv, lower_red1, upper_red1)
    mask2 = cv2.inRange(hsv, lower_red2, upper_red2)
    mask = cv2.bitwise_or(mask1, mask2)

    # Remove noise
    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None

    # Pick the largest contour
    largest = max(contours, key=cv2.contourArea)
    if cv2.contourArea(largest) < 50:  # ignore tiny noise
        return None

    M = cv2.moments(largest)
    if M["m00"] == 0:
        return None

    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])
    return (cx, cy)


def track_video(video_path):
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        print(f"Error: Cannot open video file: {video_path}", file=sys.stderr)
        sys.exit(1)

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = cap.get(cv2.CAP_PROP_FPS)
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    coords = []  # list of (frame, x, y, time_sec)
    frame_idx = 0

    print(f"Processing video: {video_path}")
    print(f"Total frames: {total_frames}, FPS: {fps:.1f}")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        result = detect_red_marker(frame)
        if result:
            cx, cy = result
            # Flip Y so origin is bottom-left (like standard XY plot)
            cy_flipped = height - cy
            time_sec = frame_idx / fps if fps > 0 else frame_idx
            coords.append((frame_idx, cx, cy_flipped, time_sec))

        frame_idx += 1
        if frame_idx % 100 == 0:
            print(f"  Processed {frame_idx}/{total_frames} frames, detected: {len(coords)} points")

    cap.release()
    print(f"Done. Detected marker in {len(coords)} frames out of {frame_idx}.")
    return coords, height


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

    frames = [c[0] for c in coords]
    xs = [c[1] for c in coords]
    ys = [c[2] for c in coords]
    times = [c[3] for c in coords]

    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    # --- Scatter plot: XY position colored by time ---
    sc = axes[0].scatter(xs, ys, c=times, cmap="viridis", s=10, alpha=0.7)
    axes[0].plot(xs, ys, color="gray", linewidth=0.5, alpha=0.4)
    axes[0].set_xlabel("X (px)")
    axes[0].set_ylabel("Y (px, bottom-origin)")
    axes[0].set_title("Marker XY Trajectory")
    axes[0].set_aspect("equal")
    fig.colorbar(sc, ax=axes[0], label="Time (sec)")

    # --- Time series: X and Y over time ---
    axes[1].plot(times, xs, label="X", color="tab:blue")
    axes[1].plot(times, ys, label="Y", color="tab:orange")
    axes[1].set_xlabel("Time (sec)")
    axes[1].set_ylabel("Position (px)")
    axes[1].set_title("X / Y over Time")
    axes[1].legend()
    axes[1].grid(True, alpha=0.3)

    fig.suptitle(f"Red Marker Tracking — {video_path}", fontsize=11)
    plt.tight_layout()
    plt.savefig(output_path, dpi=150)
    print(f"Scatter plot saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Track red marker in video and plot XY scatter.")
    parser.add_argument("video", help="Path to input video file")
    parser.add_argument("--output", default="marker_scatter.png", help="Output scatter plot image (default: marker_scatter.png)")
    parser.add_argument("--csv", default="marker_coords.csv", help="Output CSV file (default: marker_coords.csv)")
    parser.add_argument("--no-csv", action="store_true", help="Skip CSV output")
    args = parser.parse_args()

    coords, height = track_video(args.video)

    if not args.no_csv:
        save_csv(coords, args.csv)

    plot_scatter(coords, args.output, args.video)


if __name__ == "__main__":
    main()
