# X11 MPV Video Player

Two-instance mpv video player for X11/NVIDIA.

## Features

- Main mpv instance for dedicated HDMI video output
- Second mpv instance for preview
- XRandR display mode switching
- Automatic video FPS detection with ffprobe
- Selects a matching display refresh rate
- `--geometry` for exact video window placement
- Tkinter control GUI
- Play/pause, stop, seek and volume
- Restores the original display mode on exit

## Install

```bash
sudo apt install mpv ffmpeg x11-xserver-utils python3-tk
```

## Run

```bash
python3 video_player.py
```

Set `VIDEO_OUTPUT` in `video_player.py` if you want to force a specific X11 output, for example:

```python
VIDEO_OUTPUT = "HDMI-1"
```

With `None`, the program automatically prefers the non-primary output.
