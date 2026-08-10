#!/usr/bin/env python3

"""
X11 / NVIDIA / mpv Video Player
Two mpv instances:
    - Main: exclusive video output on a separate HDMI output
    - Preview: separate mpv window on the control monitor
"""

import tkinter as tk
from tkinter import filedialog, messagebox
import subprocess
import socket
import json
import os
import re
import time
import threading
from dataclasses import dataclass
from fractions import Fraction


VIDEO_OUTPUT = None
PREVIEW_WIDTH = 480
PREVIEW_HEIGHT = 270
PREVIEW_MARGIN = 20


@dataclass
class DisplayMode:
    output: str
    width: int
    height: int
    refresh: float
    x: int = 0
    y: int = 0

    @property
    def mode(self):
        return f"{self.width}x{self.height}"


@dataclass
class VideoInfo:
    filename: str
    width: int
    height: int
    fps: float
    fps_fraction: Fraction


class VideoOutputManager:
    def __init__(self, video_output=None):
        self.video_output = video_output
        self.original_mode = None
        self.video_mode = None

    @staticmethod
    def run(command):
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        return result.stdout

    def xrandr(self):
        return self.run(["xrandr", "--query"])

    def get_outputs(self):
        outputs = []
        for line in self.xrandr().splitlines():
            match = re.match(r"^(\S+)\s+connected", line)
            if match:
                outputs.append(match.group(1))
        return outputs

    def get_primary_output(self):
        for line in self.xrandr().splitlines():
            match = re.match(r"^(\S+)\s+connected\s+primary", line)
            if match:
                return match.group(1)
        return None

    def get_output_geometry(self, output_name):
        pattern = (
            rf"^{re.escape(output_name)}\s+connected(?:\s+primary)?\s+"
            r"(\d+)x(\d+)\+(-?\d+)\+(-?\d+)"
        )
        for line in self.xrandr().splitlines():
            match = re.match(pattern, line)
            if match:
                return tuple(map(int, match.groups()))
        return None

    def select_video_output(self, preferred=None):
        outputs = self.get_outputs()
        if not outputs:
            raise RuntimeError("Keine angeschlossenen X11-Ausgänge gefunden.")

        if preferred:
            if preferred not in outputs:
                raise RuntimeError(f"Ausgang {preferred} ist nicht angeschlossen.")
            self.video_output = preferred
            return preferred

        if self.video_output:
            if self.video_output not in outputs:
                raise RuntimeError(f"Ausgang {self.video_output} ist nicht angeschlossen.")
            return self.video_output

        primary = self.get_primary_output()
        for output in outputs:
            if output != primary:
                self.video_output = output
                return output

        self.video_output = outputs[0]
        return self.video_output

    def get_modes(self, output_name):
        modes = []
        inside = False
        for line in self.xrandr().splitlines():
            if re.match(r"^\S+\s+connected", line):
                inside = line.startswith(output_name + " ")
                continue
            if not inside:
                continue

            match = re.match(r"^\s*(\d+)x(\d+)\s+(.+)$", line)
            if not match:
                continue

            width = int(match.group(1))
            height = int(match.group(2))

            for rate in match.group(3).split():
                rate = rate.replace("*", "").replace("+", "")
                try:
                    refresh = float(rate)
                except ValueError:
                    continue
                modes.append(DisplayMode(output_name, width, height, refresh))
        return modes

    def get_current_mode(self, output_name):
        lines = self.xrandr().splitlines()
        width = height = x = y = None
        inside = False

        for line in lines:
            if line.startswith(output_name + " "):
                inside = True
                match = re.search(
                    r"connected.*?(\d+)x(\d+)\+(-?\d+)\+(-?\d+)", line
                )
                if match:
                    width, height, x, y = map(int, match.groups())
                continue

            if inside and re.match(r"^\S+\s+", line):
                if not line.startswith(" "):
                    break

            if not inside or width is None or height is None:
                continue

            match = re.match(rf"\s*{width}x{height}\s+(.+)", line)
            if not match:
                continue

            for rate in match.group(1).split():
                if "*" not in rate:
                    continue
                rate = rate.replace("*", "").replace("+", "")
                try:
                    refresh = float(rate)
                    return DisplayMode(output_name, width, height, refresh, x, y)
                except ValueError:
                    pass
        return None

    def get_video_info(self, filename):
        result = subprocess.run(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0",
                "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate",
                "-of", "json", filename
            ],
            capture_output=True, text=True, check=True
        )
        stream = json.loads(result.stdout)["streams"][0]
        width = int(stream["width"])
        height = int(stream["height"])
        rate = stream.get("avg_frame_rate")
        if not rate or rate == "0/0":
            rate = stream["r_frame_rate"]
        fps_fraction = Fraction(rate)
        return VideoInfo(filename, width, height, float(fps_fraction), fps_fraction)

    @staticmethod
    def refresh_score(fps, refresh):
        if abs(fps - refresh) < 0.03:
            return abs(fps - refresh)

        best = float("inf")
        for multiplier in range(1, 5):
            expected = fps * multiplier
            relative_error = abs(expected - refresh) / fps
            if relative_error < 0.01:
                score = relative_error + multiplier * 0.0001
                best = min(best, score)

        if best != float("inf"):
            return best
        return 10 + abs(refresh - fps) / fps

    def find_best_mode(self, video):
        modes = self.get_modes(self.video_output)
        if not modes:
            return None

        exact = [
            m for m in modes
            if m.width == video.width and m.height == video.height
        ]

        if exact:
            modes = exact
        else:
            aspect = video.width / video.height
            modes.sort(key=lambda m: abs(m.width / m.height - aspect))
            best = modes[0]
            best_error = abs(best.width / best.height - aspect)
            modes = [
                m for m in modes
                if abs(m.width / m.height - aspect) <= best_error + 0.01
            ]

        modes.sort(key=lambda m: self.refresh_score(video.fps, m.refresh))
        return modes[0]

    def set_mode(self, mode):
        if self.original_mode is None:
            self.original_mode = self.get_current_mode(mode.output)

        subprocess.run(
            [
                "xrandr", "--output", mode.output,
                "--mode", mode.mode,
                "--rate", f"{mode.refresh:.6f}"
            ],
            check=True
        )

        geometry = self.get_output_geometry(mode.output)
        if geometry:
            mode.x = geometry[2]
            mode.y = geometry[3]

        self.video_mode = mode

    def prepare_for_video(self, filename):
        if not self.video_output:
            self.select_video_output()

        video = self.get_video_info(filename)
        mode = self.find_best_mode(video)
        if mode is None:
            raise RuntimeError("Kein geeigneter Display-Modus gefunden.")

        self.set_mode(mode)
        return video, mode

    def get_mpv_geometry(self):
        if not self.video_mode:
            raise RuntimeError("Kein Video-Modus gesetzt.")
        m = self.video_mode
        return f"{m.width}x{m.height}+{m.x}+{m.y}"

    def get_mpv_arguments(self):
        return [
            "--no-border",
            "--fullscreen=no",
            "--keepaspect=yes",
            "--video-sync=display-resample",
            "--hwdec=auto-safe",
            "--vo=gpu-next",
            "--force-window=yes",
            f"--geometry={self.get_mpv_geometry()}",
        ]

    def restore_original_mode(self):
        if not self.original_mode:
            return

        mode = self.original_mode
        try:
            subprocess.run(
                [
                    "xrandr", "--output", mode.output,
                    "--mode", mode.mode,
                    "--rate", f"{mode.refresh:.6f}"
                ],
                check=True
            )
        except Exception as e:
            print("Fehler beim Wiederherstellen:", e)

        self.original_mode = None
        self.video_mode = None


class MPVController:
    def __init__(self, name):
        self.name = name
        self.socket_path = f"/tmp/mpv_{name}_{os.getpid()}.sock"
        self.process = None
        self.socket = None
        self.running = False
        self.callbacks = []
        self.reader_thread = None

    def start(self, arguments):
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass

        command = ["mpv"] + list(arguments) + [
            "--idle=yes",
            "--input-ipc-server=" + self.socket_path,
            "--terminal=no",
        ]

        self.process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        for _ in range(100):
            if os.path.exists(self.socket_path):
                break
            time.sleep(0.05)

        if not os.path.exists(self.socket_path):
            raise RuntimeError(
                f"IPC-Socket von mpv {self.name} wurde nicht erzeugt."
            )

        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.connect(self.socket_path)
        self.running = True

        self.reader_thread = threading.Thread(
            target=self._reader, daemon=True
        )
        self.reader_thread.start()

    def _reader(self):
        buffer = b""
        while self.running:
            try:
                data = self.socket.recv(4096)
                if not data:
                    break
                buffer += data

                while b"\n" in buffer:
                    line, buffer = buffer.split(b"\n", 1)
                    if not line:
                        continue
                    try:
                        message = json.loads(line.decode())
                    except Exception:
                        continue

                    for callback in self.callbacks:
                        try:
                            callback(self, message)
                        except Exception:
                            pass
            except Exception:
                break

    def add_callback(self, callback):
        self.callbacks.append(callback)

    def command(self, *args):
        if not self.socket:
            return

        data = (json.dumps({"command": list(args)}) + "\n").encode()
        try:
            self.socket.sendall(data)
        except Exception:
            pass

    def observe(self, property_name, observer_id):
        self.command("observe_property", observer_id, property_name)

    def load_file(self, filename):
        self.command("loadfile", filename, "replace")

    def play_pause(self):
        self.command("cycle", "pause")

    def set_pause(self, value):
        self.command("set_property", "pause", bool(value))

    def stop(self):
        self.command("stop")

    def seek(self, seconds):
        self.command("seek", seconds, "relative")

    def set_position(self, position):
        self.command("set_property", "time-pos", float(position))

    def set_volume(self, volume):
        self.command("set_property", "volume", float(volume))

    def quit(self):
        self.running = False

        try:
            self.command("quit")
        except Exception:
            pass

        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None

        if self.process:
            try:
                self.process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self.process.kill()
            self.process = None

        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass


class VideoPlayerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("X11 MPV Video Player")
        self.root.geometry("800x600")

        self.output_manager = VideoOutputManager(VIDEO_OUTPUT)
        self.main_mpv = MPVController("main")
        self.preview_mpv = MPVController("preview")

        self.current_file = None
        self.duration = 0.0
        self.position = 0.0
        self.main_pause = False
        self.dragging = False

        self.create_gui()

        self.main_mpv.add_callback(self.main_mpv_event)

        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.update_gui()

    def create_gui(self):
        top = tk.Frame(self.root)
        top.pack(fill="x", padx=10, pady=10)

        tk.Button(
            top, text="Datei öffnen", command=self.open_file
        ).pack(side="left")

        self.file_label = tk.Label(
            top, text="Keine Datei", anchor="w"
        )
        self.file_label.pack(side="left", padx=10, fill="x", expand=True)

        info = tk.Frame(self.root)
        info.pack(fill="x", padx=10)

        self.video_info_label = tk.Label(info, text="Video: -", anchor="w")
        self.video_info_label.pack(side="left")

        self.display_info_label = tk.Label(info, text="Display: -", anchor="e")
        self.display_info_label.pack(side="right")

        preview_info = tk.Frame(self.root, background="black")
        preview_info.pack(fill="both", expand=True, padx=10, pady=10)

        tk.Label(
            preview_info,
            text="Vorschau läuft in einem separaten mpv-Fenster",
            foreground="white",
            background="black",
            font=("Arial", 16),
        ).pack(expand=True)

        self.position_scale = tk.Scale(
            self.root, from_=0, to=100, orient="horizontal",
            showvalue=False, resolution=0.1
        )
        self.position_scale.pack(fill="x", padx=10)
        self.position_scale.bind("<ButtonPress-1>", self.start_seek)
        self.position_scale.bind("<ButtonRelease-1>", self.end_seek)

        self.time_label = tk.Label(self.root, text="00:00 / 00:00")
        self.time_label.pack()

        controls = tk.Frame(self.root)
        controls.pack(pady=8)

        tk.Button(
            controls, text="⏪ -10 s", width=9,
            command=lambda: self.seek(-10)
        ).pack(side="left", padx=3)

        tk.Button(
            controls, text="▶ / ❚❚", width=12,
            command=self.play_pause
        ).pack(side="left", padx=3)

        tk.Button(
            controls, text="■ Stop", width=9,
            command=self.stop
        ).pack(side="left", padx=3)

        tk.Button(
            controls, text="+10 s ⏩", width=9,
            command=lambda: self.seek(10)
        ).pack(side="left", padx=3)

        volume_frame = tk.Frame(self.root)
        volume_frame.pack(fill="x", padx=20)

        tk.Label(volume_frame, text="Lautstärke").pack(side="left")

        self.volume = tk.Scale(
            volume_frame, from_=0, to=100,
            orient="horizontal", command=self.volume_changed
        )
        self.volume.set(100)
        self.volume.pack(side="left", fill="x", expand=True)

        self.status = tk.Label(
            self.root, text="Bereit", anchor="w"
        )
        self.status.pack(fill="x", padx=10, pady=5)

    def get_preview_geometry(self):
        primary = self.output_manager.get_primary_output()

        if not primary:
            return (
                f"{PREVIEW_WIDTH}x{PREVIEW_HEIGHT}"
                f"+{PREVIEW_MARGIN}+{PREVIEW_MARGIN}"
            )

        geometry = self.output_manager.get_output_geometry(primary)

        if not geometry:
            return (
                f"{PREVIEW_WIDTH}x{PREVIEW_HEIGHT}"
                f"+{PREVIEW_MARGIN}+{PREVIEW_MARGIN}"
            )

        width, height, x, y = geometry

        preview_x = x + width - PREVIEW_WIDTH - PREVIEW_MARGIN
        preview_y = y + PREVIEW_MARGIN

        return (
            f"{PREVIEW_WIDTH}x{PREVIEW_HEIGHT}"
            f"+{preview_x}+{preview_y}"
        )

    def start_preview(self):
        if self.preview_mpv.process:
            return

        arguments = [
            "--no-border",
            "--fullscreen=no",
            f"--geometry={self.get_preview_geometry()}",
            f"--autofit={PREVIEW_WIDTH}x{PREVIEW_HEIGHT}",
            "--keepaspect=yes",
            "--hwdec=auto-safe",
            "--vo=gpu-next",
            "--force-window=yes",
            "--title=MPV Vorschau",
        ]

        self.preview_mpv.start(arguments)
        self.preview_mpv.set_volume(0)

    def open_file(self):
        filename = filedialog.askopenfilename(
            title="Videodatei öffnen",
            filetypes=[
                (
                    "Videodateien",
                    "*.mp4 *.mkv *.mov *.avi *.webm *.m2ts *.ts"
                ),
                ("Alle Dateien", "*.*"),
            ],
        )
        if filename:
            self.play_file(filename)

    def play_file(self, filename):
        try:
            self.status.config(text="Analysiere Video ...")
            self.root.update_idletasks()

            video, mode = self.output_manager.prepare_for_video(filename)

            if not self.main_mpv.process:
                self.main_mpv.start(
                    self.output_manager.get_mpv_arguments()
                )

            self.start_preview()

            self.main_mpv.load_file(filename)
            self.preview_mpv.load_file(filename)

            self.current_file = filename
            self.duration = 0
            self.position = 0

            self.file_label.config(
                text=os.path.basename(filename)
            )

            self.video_info_label.config(
                text=(
                    f"Video: {video.width}×{video.height} "
                    f"{video.fps:.3f} fps"
                )
            )

            self.display_info_label.config(
                text=(
                    f"Display: {mode.width}×{mode.height} "
                    f"{mode.refresh:.3f} Hz"
                )
            )

            self.status.config(
                text=f"Wiedergabe: {mode.refresh:.3f} Hz"
            )

        except Exception as e:
            messagebox.showerror("Fehler", str(e))
            self.status.config(text="Fehler")

    def play_pause(self):
        self.main_mpv.play_pause()
        self.preview_mpv.play_pause()

    def seek(self, seconds):
        self.main_mpv.seek(seconds)
        self.preview_mpv.seek(seconds)

    def stop(self):
        self.main_mpv.stop()
        self.preview_mpv.stop()
        self.status.config(text="Gestoppt")

    def volume_changed(self, value):
        self.main_mpv.set_volume(float(value))
        self.preview_mpv.set_volume(0)

    def start_seek(self, event):
        self.dragging = True

    def end_seek(self, event):
        self.dragging = False

        if self.duration <= 0:
            return

        position = self.position_scale.get() / 100 * self.duration
        self.main_mpv.set_position(position)
        self.preview_mpv.set_position(position)

    def main_mpv_event(self, mpv, message):
        if message.get("event") != "property-change":
            return

        name = message.get("name")
        value = message.get("data")

        if name == "time-pos" and value is not None:
            self.position = float(value)

        elif name == "duration" and value is not None:
            self.duration = float(value)

        elif name == "pause" and value is not None:
            self.main_pause = bool(value)

    def synchronize_preview(self):
        if not self.preview_mpv.process or not self.main_mpv.process:
            return

        if self.duration > 0:
            self.preview_mpv.set_position(self.position)
            self.preview_mpv.set_pause(self.main_pause)

    @staticmethod
    def format_time(seconds):
        if seconds is None:
            return "00:00"

        seconds = max(0, int(seconds))
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        seconds %= 60

        if hours:
            return f"{hours:02}:{minutes:02}:{seconds:02}"

        return f"{minutes:02}:{seconds:02}"

    def update_gui(self):
        if self.duration > 0 and not self.dragging:
            percentage = self.position / self.duration * 100
            percentage = max(0, min(100, percentage))
            self.position_scale.set(percentage)

        self.time_label.config(
            text=(
                self.format_time(self.position)
                + " / "
                + self.format_time(self.duration)
            )
        )

        self.synchronize_preview()
        self.root.after(500, self.update_gui)

    def close(self):
        try:
            self.preview_mpv.quit()
            self.main_mpv.quit()
        finally:
            self.output_manager.restore_original_mode()
            self.root.destroy()


def main():
    root = tk.Tk()
    VideoPlayerGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
