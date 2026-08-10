# Cinema Player

The Cinema Player is designed to play videos on a projector in a small private cinema. It uses two outputs (HDMI, DVI, or DisplayPort) from a dedicated graphics card to separate the video output from the control interface.

The aim is to provide the audience a perfect high quality cinema experience, with no distracting text or OSD elements on the big screen, while offering the projectionist an intuitive but powerful user interface.

The video output displays only the video image. When no playback is active, the screen remains black. The control screen displays a playlist with the program containing videos and images and controls for playback. A preview window allows the projectionist to monitor the video being played, preview videos and edit the playlist.

# Function
## Controller

The control window is split into three parts:

- A status area at the top shows the playback and beamer status.
- Below on the left side are the playback controls with a progress bar and time displays and the playlist with functions for loading media files, sorting them, and saving and loading playlists.
- On the right side is the preview window with a video player and an edit area for the settings.

### Playlist

The playlist is the central user interface for the player. It shows a scrollable list of the video files in the order to be played. Videos or complete directories can be added to the list. By dragging an entry the position in the list can be changed.

#### Global settings

- **Projection zoom** - When the zoom of the projector is changed between 16:9 and 21:9 this checkbox ist set. When the zoom has to be altered, a popup window indicates the projectionist when to do so. The playback starts when the successful zoom change is confirmed. 
  When 16:9 images are displayed in the 21:9 zoom mode, the are scaled to fit the vertical resolution. 
 - **Autoplay delay** - The seconds to wait, when the next video is automatically started.
 - **idle screen media** - an image or video loop to be shown instead of a black screen, when no video is played.
 
 #### Playback Controls

- **Play** – Start or resume playback.
- **Pause** – Pause playback and retain the current position. The video output is rendered black.
- **Still** - Like pause, but a still image of the current video position is shown.
- **Stop** – Stop playback and set the position to the next entry in the list.

**Pause**, **Still** and **Stop** must be confirmed before the action is performed.

#### Time displays

When a video is playing four times are shown: 

- **Total** - The length of the video
- **Elapsed** - The time already shown
- **Remaining** - The time still to show
- **End** - The absolute time, when the video will end.

 #### Program and Playback

The playlist is started by pushing the **Play** button. The program status in the status bar changes from **OFF** (red) to **PROGRAM** (blue) and the **Play** button changes to **Resume** to indicate, that the program is running. The playlist is now processed.

With **Resume** the first video is started and the status changes to **PLAYING** (green). When a video has ended, the status changes to **PROGRAM** (blue) and the next entry in the list can be started with the **Resume** bottom.

If the autoplay option is selected for an entry, the playback is automatically resumed with the next video. The autoplay delay in the timeline settings determine, how many seconds of black are shown, before the next video starts.

In the program mode, **Stop** only ends the playback of a video not the execution of the timeline. Pushing **Stop** a second time ends the timeline processing and the program status changes back to **OFF**.

The playback position in the playlist can be changed by clicking on a video. However, the change must be confirmed before it takes effect to avoid confusion in the playback order. This option is disabled during video playback.

A cursor on the left side of the list shows the current position in the program. If the current video is playing, the entry is highlighted in the colour of the program status.

Already played videos are greyed out.

If a video needs attention, like a change in aspect ratio (if projection zoom is activated) or a different resolution or pixel aspect, a popup window reminds the projectionist of possible actions to be set. The affected data in the playlist entries are marked red. The program only can be resumed by confirming these informations.

#### Media entries

An entry in the playlist shows the filename, additional informations and the individual settings.

If no entry is selected by the projectionist, the preview window shows the data of the current entry. The preview status in the right upper corner of the preview area is set to **Live** (program colour).

When selecting an entry by clicking in the playlist, it is highlighted in dark yellow, the data is displayed in the preview and the preview status changes to **Preview** (dark yellow).

The displayed metadata are: 

- Length
- Container format
- Framerate
- Resolution
- Video codec / Datarate
- Audio codec / Datarate
- Aspect ratio
- Pixel aspect ratio

Settings (allways)

- Autoplay checkbox

Settings (video only)

- Audio track
- Subtitle track 
- Start position
- End position

Settings (image only) 
- Play time

#### Entry settings

In the playlist different options can be selected for each entry in the list. 

- If multiple audio tracks are available, the track to be used can be selected
- If subtitles are embedded, the desired one can be selected
- A checkbox overrides the auto stop behavior but automatically start playback of the next entry.

#### Images

Images can also be integrated in the list. They behave a little different from videos due to the lack of a running time. In the settings a display time can be set. After this time, it stops or starts the next item, depending on the settings. If no time is set, the display must be stopped with the play controls and the focus jumps to the next entry.

Playlists with all options can be saved for later use.

### Preview

The preview displays a video in a window within the control panel. The source can be switched between the live video output being sent to the projector (**Live**) and a video from the playlist (**Preview**) by clicking the preview status.

When a playlist entry is selected, the playback position can be selected using a progress bar. A start point and an end point can be defined to determine where the video starts and ends when it goes on air. This option is disabled, when the video is on air.

# Technique

## Architecture

The computer runs Linux, and the application is written in Python. The open-source video player MPV provides the high-quality video and audio output for the projector. FFprobe is used to read all metadata from the video files.

For good performance, the graphics card must support hardware decoding of both the H.264 and H.265 codecs.

## Framerate

To achieve smooth, flicker-free playback, the graphics card's refresh rate must be adapted before video playback starts.

1. The video's metadata is read.
2. The refresh rates supported by the projector are checked.
3. The graphics card is set to the video's frame rate or an integer multiple of it.

If the process is successful, the beamer status shows **OK** (green).

If no matching refresh rate is found, the status goes to **Mismatch** (red) and the incorrect settings are highlighted in red. In this case, the video still can be displayed, but there could occur frame dropping artefacts.

This check is performed when videos are added to the playlist and when a playlist is loaded. Each entry indicates whether the video can be played correctly.

## Audio

The audio track of the video is streamed via the HDMI output for the beamer. When watching a video in the preview, the sound is not only provided on the second HDMI output but can also be routed to a dedicated audio output.