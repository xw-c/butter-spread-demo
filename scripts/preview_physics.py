"""Plot actual MPM particles at selected times; no surface reconstruction."""

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation, FFMpegWriter
import numpy as np


ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument("--state", type=Path, default=ROOT / "outputs" / "mpm-state.npz")
parser.add_argument("--output", type=Path, default=ROOT / "outputs" / "physics-preview.png")
parser.add_argument("--video", type=Path, help="optional top/side particle diagnostic MP4")
args = parser.parse_args()

with np.load(args.state) as data:
    particles = data["particles"]
    knife = data["knife_positions"]
    times = data["time_s"]
    blade_size = data["knife_size"]
    bread_size = data["bread_size"]
    fps = int(data["fps"])
metadata = json.loads(args.state.with_suffix(".json").read_text(encoding="utf-8"))
blade_x_offset, blade_y_offset = metadata.get("knife_collider_xy_offset_m", [0, 0])

indices = np.unique(np.linspace(0, len(particles) - 1, 6).round().astype(int))
fig, axes = plt.subplots(2, len(indices), figsize=(3.4 * len(indices), 6), dpi=150)
for column, frame in enumerate(indices):
    q, pose = particles[frame], knife[frame]
    ax = axes[0, column]
    ax.scatter(q[:, 0] * 1000, q[:, 1] * 1000, s=0.45, c="#e4a72d", alpha=0.75)
    half_bread_x, half_bread_y = bread_size[:2] * 500
    ax.plot([-half_bread_x, half_bread_x, half_bread_x, -half_bread_x, -half_bread_x],
            [-half_bread_y, -half_bread_y, half_bread_y, half_bread_y, -half_bread_y],
            color="#9b683d")
    ax.add_patch(plt.Rectangle(((pose[0] + blade_x_offset - blade_size[0] / 2) * 1000,
                                (blade_y_offset - blade_size[1] / 2) * 1000),
                               blade_size[0] * 1000, blade_size[1] * 1000,
                               color="#596d80", alpha=0.4))
    ax.set(xlim=(-85, 85), ylim=(-65, 65), aspect="equal", title=f"{times[frame]:.2f} s")
    if column == 0:
        ax.set_ylabel("top / y (mm)")
    ax = axes[1, column]
    ax.scatter(q[:, 0] * 1000, q[:, 2] * 1000, s=0.45, c="#e4a72d", alpha=0.75)
    ax.axhline(26, color="#9b683d", lw=2)
    ax.add_patch(plt.Rectangle(((pose[0] + blade_x_offset - blade_size[0] / 2) * 1000,
                                (pose[2] - blade_size[2] / 2) * 1000),
                               blade_size[0] * 1000, blade_size[2] * 1000,
                               color="#596d80", alpha=0.7))
    ax.set(xlim=(-85, 85), ylim=(21, 66), aspect="auto")
    if column == 0:
        ax.set_ylabel("side / z (mm)")
for ax in axes.ravel():
    ax.grid(alpha=0.15)
    ax.set_xlabel("x (mm)")
fig.tight_layout()
args.output.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(args.output)
print(f"Saved {args.output}")
plt.close(fig)

if args.video is not None:
    import imageio_ffmpeg

    matplotlib.rcParams["animation.ffmpeg_path"] = imageio_ffmpeg.get_ffmpeg_exe()
    fig, (top, side) = plt.subplots(1, 2, figsize=(10, 4), dpi=120)
    for ax in (top, side):
        ax.set_xlim(-85, 85)
        ax.grid(alpha=0.15)
        ax.set_xlabel("x (mm)")
    top.set(ylim=(-65, 65), ylabel="y (mm)", title="Top view")
    half_bread_x, half_bread_y = bread_size[:2] * 500
    top.plot([-half_bread_x, half_bread_x, half_bread_x, -half_bread_x, -half_bread_x],
             [-half_bread_y, -half_bread_y, half_bread_y, half_bread_y, -half_bread_y],
             color="#9b683d")
    side.set(ylim=(21, 66), ylabel="z (mm)", title="Side view")
    side.axhline(26, color="#9b683d", lw=2)
    top_points = top.scatter([], [], s=1.3, c="#e4a72d")
    side_points = side.scatter([], [], s=1.3, c="#e4a72d")
    top_blade = plt.Rectangle((0, 0), blade_size[0] * 1000, blade_size[1] * 1000,
                              color="#596d80", alpha=0.35)
    side_blade = plt.Rectangle((0, 0), blade_size[0] * 1000, blade_size[2] * 1000,
                               color="#596d80", alpha=0.7)
    top.add_patch(top_blade)
    side.add_patch(side_blade)
    clock = fig.suptitle("")

    def draw(frame):
        q, pose = particles[frame], knife[frame]
        top_points.set_offsets(q[:, :2] * 1000)
        side_points.set_offsets(q[:, [0, 2]] * 1000)
        top_blade.set_xy(((pose[0] + blade_x_offset - blade_size[0] / 2) * 1000,
                          (blade_y_offset - blade_size[1] / 2) * 1000))
        side_blade.set_xy(((pose[0] + blade_x_offset - blade_size[0] / 2) * 1000,
                           (pose[2] - blade_size[2] / 2) * 1000))
        clock.set_text(f"Genesis MPM particles | {times[frame]:.2f} s")
        return top_points, side_points, top_blade, side_blade, clock

    movie = FuncAnimation(fig, draw, frames=len(particles), blit=True)
    args.video.parent.mkdir(parents=True, exist_ok=True)
    movie.save(args.video, writer=FFMpegWriter(fps=fps, codec="libx264", bitrate=2400))
    plt.close(fig)
    print(f"Saved {args.video}")
