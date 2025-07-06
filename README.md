# YouTube Playlist & Video Downloader

A modern, user-friendly GUI application for downloading YouTube playlists and individual videos as either MP4 (video) or MP3 (audio). Built with Python, Tkinter, [yt-dlp](https://github.com/yt-dlp/yt-dlp), and [ffmpeg](https://ffmpeg.org/).

## Features
- Download entire playlists or single videos from YouTube
- Choose between video (mp4) or audio (mp3) formats
- Modern, responsive GUI with progress tracking and logs
- Pause/stop downloads and clear logs
- Output folder selection

## How it works
- **yt-dlp**: Handles all YouTube extraction, downloading, and format conversion. This project is a GUI wrapper around yt-dlp, so all the heavy lifting is done by yt-dlp.
- **ffmpeg**: Used by yt-dlp for media conversion (e.g., extracting audio to mp3, merging video/audio streams). You must have `ffmpeg.exe` in the project directory or update the path in the code.

## Requirements
- Python 3.7+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [ffmpeg](https://ffmpeg.org/) (Windows binary included or download from official site)
- See `requirements.txt` for Python dependencies

## Installation
1. Clone this repository:
   ```sh
   git clone <your-repo-url>
   cd PLAYLIST DOWNLOADER
   ```
2. Install Python dependencies:
   ```sh
   pip install -r requirements.txt
   ```
3. Ensure `ffmpeg.exe` is present in the project directory (or update the path in `Downloader.py`).

## Usage
Run the application:
```sh
python Downloader.py
```

- Paste a YouTube playlist or video URL
- Choose output folder and format
- Click "Download Content"

## Notes
- This project is for educational/personal use. Respect YouTube's Terms of Service.
- All download/conversion logic is handled by yt-dlp and ffmpeg; this app is a GUI wrapper.

## License
MIT License
