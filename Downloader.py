import os
import re
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
import yt_dlp


class ToolTip:
    """Simple tooltip widget for tkinter elements."""
    
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tipwindow = None
        widget.bind("<Enter>", self.show_tip)
        widget.bind("<Leave>", self.hide_tip)
    
    def show_tip(self, event=None):
        if self.tipwindow or not self.text:
            return
        x, y, cx, cy = self.widget.bbox("insert")
        x = x + self.widget.winfo_rootx() + 25
        y = y + self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT,
                        background="#ffffe0", relief=tk.SOLID, borderwidth=1,
                        font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)
    
    def hide_tip(self, event=None):
        tw = self.tipwindow
        self.tipwindow = None
        if tw:
            tw.destroy()


class YTDlpLogger:
    """Custom logger for yt-dlp that writes to GUI output."""
    
    def __init__(self, output_widget, video_counter=None, progress_label_var=None, total_videos=None, audio_only=False):
        self.output_widget = output_widget
        self.video_counter = video_counter
        self.progress_label_var = progress_label_var
        self.total_videos = total_videos
        self.audio_only = audio_only

    def _write_to_output(self, msg, tag='info'):
        self.output_widget.configure(state='normal')
        self.output_widget.insert(tk.END, msg + '\n', tag)
        self.output_widget.see(tk.END)
        self.output_widget.configure(state='disabled')
        # For video downloads, increment progress when merger line is seen
        if (not self.audio_only and self.video_counter is not None and self.progress_label_var is not None and self.total_videos is not None):
            if msg.startswith('[Merger] Merging formats into'):
                self.video_counter['current'] += 1
                self.progress_label_var.set(f"Progress: {self.video_counter['current']}/{self.total_videos}")

    def debug(self, msg):
        if msg.strip():
            if '[Merger] Merging formats into' in msg:
                self._write_to_output(msg, 'info')
            elif '[download]' in msg:
                self._write_to_output(msg, 'progress')
            else:
                self._write_to_output(msg, 'info')
    
    def warning(self, msg):
        if msg.strip():
            self._write_to_output('[warning] ' + msg, 'warning')
    
    def error(self, msg):
        if msg.strip():
            self._write_to_output('[error] ' + msg, 'error')


class PlaylistDownloader:
    """Handles YouTube playlist and individual video downloading functionality."""
    
    def __init__(self):
        self.ffmpeg_path = self._get_ffmpeg_path()
    
    def _get_ffmpeg_path(self):
        """Get the path to ffmpeg executable."""
        script_dir = os.path.dirname(os.path.abspath(__file__))
        return os.path.join(script_dir, 'ffmpeg-master-latest-win32-gpl', 'bin', 'ffmpeg.exe')
    
    def sanitize_filename(self, filename):
        """Remove invalid characters from filename."""
        return re.sub(r'[<>:"/\\|?*]', '', filename)
    
    def is_playlist_url(self, url):
        """Check if URL is a playlist or individual video."""
        return 'playlist' in url.lower() or 'list=' in url.lower()
    
    def is_valid_youtube_url(self, url):
        """Check if URL is a valid YouTube URL."""
        youtube_patterns = [
            r'youtube\.com/watch\?v=',
            r'youtube\.com/playlist\?list=',
            r'youtu\.be/',
            r'youtube\.com/.*[?&]list=',
            r'm\.youtube\.com/'
        ]
        return any(re.search(pattern, url.lower()) for pattern in youtube_patterns)
    
    def download_content(self, url, output_dir, audio_only, gui_callbacks):
        """Download YouTube content (playlist or individual video)."""
        def run():
            try:
                # Add this download to active downloads list
                current_thread = threading.current_thread()
                gui_callbacks['gui_instance'].active_downloads.append(current_thread)
                
                if self.is_playlist_url(url):
                    self._download_playlist_process(url, output_dir, audio_only, gui_callbacks)
                else:
                    self._download_video_process(url, output_dir, audio_only, gui_callbacks)
            except Exception as e:
                print(f"Error: {str(e)}")
                gui_callbacks['status_var'].set(f"Error: {str(e)}")
            finally:
                # Remove from active downloads list
                current_thread = threading.current_thread()
                if current_thread in gui_callbacks['gui_instance'].active_downloads:
                    gui_callbacks['gui_instance'].active_downloads.remove(current_thread)
                
                gui_callbacks['button'].config(state=tk.NORMAL)
                gui_callbacks['progress_var'].set(0)
        
        download_thread = threading.Thread(target=run, daemon=True)
        download_thread.start()
        return download_thread
    
    def _download_playlist_process(self, playlist_url, output_dir, audio_only, callbacks):
        """Main playlist download process."""
        # Ensure output directory exists
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Get playlist info first
        ydl_info = yt_dlp.YoutubeDL({'quiet': True, 'extract_flat': True})
        info = ydl_info.extract_info(playlist_url, download=False)
        entries = info.get('entries', [])
        total_videos = len(entries)
        video_counter = {'current': 0}
        callbacks['progress_label_var'].set(f"Progress: 0/{total_videos}")
        # Now initialize logger with correct counters
        ydl_logger = YTDlpLogger(callbacks['output_text'], video_counter, callbacks['progress_label_var'], total_videos, audio_only)
        
        # Log playlist info
        ydl_logger._write_to_output(f"Downloading playlist: {info.get('title', 'Unknown')}", 'info')
        ydl_logger._write_to_output(f"Total videos in playlist: {total_videos}", 'info')
        
        # Set up progress hook
        def progress_hook(d):
            if callbacks['stop_flag']['stop']:
                raise Exception("Download stopped by user.")
            
            if d['status'] == 'downloading' and 'downloaded_bytes' in d and 'total_bytes' in d and d['total_bytes']:
                self._handle_download_progress(d, callbacks)
            elif d['status'] == 'finished':
                self._handle_download_finished(d, callbacks, audio_only, video_counter, total_videos)
        
        # Configure yt-dlp options
        ydl_opts = self._get_ydl_options(output_dir, audio_only, progress_hook, ydl_logger)
        
        # Download playlist
        with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
            ydl2.download([playlist_url])
        
        print(f"Playlist download completed! Files saved in: {os.path.abspath(output_dir)}")
        callbacks['status_var'].set("Playlist download completed!")
        callbacks['progress_label_var'].set(f"Progress: {video_counter['current']}/{total_videos}")
    
    def _download_video_process(self, video_url, output_dir, audio_only, callbacks):
        """Main individual video download process."""
        # Ensure output directory exists
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
        
        # Get video info first
        ydl_info = yt_dlp.YoutubeDL({'quiet': True})
        info = ydl_info.extract_info(video_url, download=False)
        video_title = info.get('title', 'Unknown Video')
        total_videos = 1
        video_counter = {'current': 0}
        callbacks['progress_label_var'].set(f"Progress: 0/{total_videos}")
        # Now initialize logger with correct counters
        ydl_logger = YTDlpLogger(callbacks['output_text'], video_counter, callbacks['progress_label_var'], total_videos, audio_only)
        
        # Log video info
        ydl_logger._write_to_output(f"Downloading video: {video_title}", 'info')
        ydl_logger._write_to_output(f"Duration: {info.get('duration', 'Unknown')} seconds", 'info')
        
        # Set up progress hook
        def progress_hook(d):
            if callbacks['stop_flag']['stop']:
                raise Exception("Download stopped by user.")
            
            if d['status'] == 'downloading' and 'downloaded_bytes' in d and 'total_bytes' in d and d['total_bytes']:
                self._handle_download_progress(d, callbacks)
            elif d['status'] == 'finished':
                self._handle_download_finished(d, callbacks, audio_only, video_counter, total_videos)
        
        # Configure yt-dlp options
        ydl_opts = self._get_ydl_options(output_dir, audio_only, progress_hook, ydl_logger)
        
        # Download video
        with yt_dlp.YoutubeDL(ydl_opts) as ydl2:
            ydl2.download([video_url])
        
        print(f"Video download completed! File saved in: {os.path.abspath(output_dir)}")
        callbacks['status_var'].set("Video download completed!")
        callbacks['progress_label_var'].set(f"Progress: {video_counter['current']}/{total_videos}")
    
    def _handle_download_progress(self, d, callbacks):
        """Handle download progress updates."""
        percent = d['downloaded_bytes'] / d['total_bytes'] * 100
        callbacks['progress_var'].set(percent)
        
        size_mb = d['total_bytes'] / 1024 / 1024 if d['total_bytes'] else 0
        downloaded_mb = d['downloaded_bytes'] / 1024 / 1024 if d['downloaded_bytes'] else 0
        speed = d.get('speed', 0)
        speed_str = f"{speed/1024/1024:.2f}MiB/s" if speed else "?"
        
        eta = d.get('eta', None)
        eta_str = f"{int(eta//60):02d}:{int(eta%60):02d}" if eta else "?"
        
        # Fragment info
        frag_str = ""
        if 'fragments' in d and 'fragment_index' in d:
            frag_str = f"(frag {d['fragment_index']}/{d['fragments']})"
        elif 'fragment_index' in d and 'total_fragments' in d:
            frag_str = f"(frag {d['fragment_index']}/{d['total_fragments']})"
        
        progress_line = (f"[download]  {percent:5.1f}% of ~ {size_mb:7.2f}MiB at {speed_str} ETA {eta_str} {frag_str}")
        
        callbacks['output_text'].configure(state='normal')
        callbacks['output_text'].insert(tk.END, f"{progress_line}\n", 'progress')
        callbacks['output_text'].see(tk.END)
        callbacks['output_text'].configure(state='disabled')
    
    def _handle_download_finished(self, d, callbacks, audio_only, video_counter, total_videos):
        """Handle download completion."""
        callbacks['progress_var'].set(100)
        callbacks['output_text'].configure(state='normal')
        callbacks['output_text'].insert(tk.END, "Status: Finished\n", 'info')
        callbacks['output_text'].see(tk.END)
        callbacks['output_text'].configure(state='disabled')
        # Only increment for audio-only here
        if audio_only:
            video_counter['current'] += 1
            callbacks['progress_label_var'].set(f"Progress: {video_counter['current']}/{total_videos}")
    
    def _get_ydl_options(self, output_dir, audio_only, progress_hook, logger):
        """Get yt-dlp options based on format choice."""
        base_opts = {
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'ignoreerrors': True,
            'noplaylist': False,
            'quiet': False,
            'ffmpeg_location': self.ffmpeg_path,
            'progress_hooks': [progress_hook],
            'logger': logger,
            'force_overwrites': True,
            'no_part': True,
            'geo_bypass': True,
        }
        
        if audio_only:
            base_opts.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                }],
            })
        else:
            base_opts.update({
                'format': 'bestvideo+bestaudio/best',
                'merge_output_format': 'mp4',
            })
        
        return base_opts


class PlaylistDownloaderGUI:
    """Main GUI class for the YouTube Playlist and Video Downloader."""
    
    def __init__(self):
        self.downloader = PlaylistDownloader()
        self.stop_flag = {'stop': False}
        self.active_downloads = []  # Track active download threads
        self.setup_gui()
    
    def setup_gui(self):
        """Initialize the GUI."""
        self.root = tk.Tk()
        self.root.title("YouTube Playlist & Video Downloader")
        self.root.geometry("600x500")
        self.root.minsize(500, 300)
        self.root.configure(bg='#f7f7f7')
        
        self.setup_styles()
        self.create_widgets()
        self.setup_event_handlers()
    
    def setup_styles(self):
        """Configure ttk styles."""
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        # Configure styles
        styles = {
            'TFrame': {'background': '#f7f7f7'},
            'TLabel': {'background': '#f7f7f7', 'font': ('Segoe UI', 10)},
            'Title.TLabel': {'font': ('Segoe UI', 18, 'bold'), 'background': '#f7f7f7', 'foreground': '#222'},
            'TButton': {'font': ('Segoe UI', 10), 'padding': 6},
            'Accent.TButton': {'font': ('Segoe UI', 11, 'bold'), 'background': '#4CAF50', 'foreground': 'white'},
            'Danger.TButton': {'font': ('Segoe UI', 10), 'background': '#f44336', 'foreground': 'white'},
            'TEntry': {'padding': 4},
            'TRadiobutton': {'background': '#f7f7f7', 'font': ('Segoe UI', 10)},
            'TProgressbar': {'thickness': 18, 'troughcolor': '#e0e0e0', 'background': '#4CAF50', 'bordercolor': '#e0e0e0'},
        }
        
        for style_name, config in styles.items():
            self.style.configure(style_name, **config)
        
        # Configure style mappings
        self.style.map('Accent.TButton', background=[('active', '#388E3C')])
        self.style.map('Danger.TButton', background=[('active', '#b71c1c')])
    
    def create_widgets(self):
        """Create all GUI widgets."""
        # Title
        title_label = ttk.Label(self.root, text="YouTube Playlist & Video Downloader", style='Title.TLabel')
        title_label.pack(pady=(18, 0))
        
        # URL input
        self.create_url_section()
        
        # Directory selection
        self.create_directory_section()
        
        # Format selection
        self.create_format_section()
        
        # Progress label
        self.create_progress_section()
        
        # Output log
        self.create_log_section()
        
        # Progress bar
        self.progress_var = tk.DoubleVar()
        self.progress_bar = ttk.Progressbar(self.root, variable=self.progress_var, maximum=100, style='TProgressbar')
        self.progress_bar.pack(fill="x", padx=28, pady=(0, 12))
        
        # Control buttons
        self.create_control_buttons()
        
        # Status bar
        self.create_status_bar()
    
    def create_url_section(self):
        """Create URL input section."""
        url_frame = ttk.Frame(self.root)
        ttk.Label(url_frame, text="YouTube URL:", style='TLabel').pack(side="left", padx=(0, 5))
        
        self.url_var = tk.StringVar()
        self.url_entry = ttk.Entry(url_frame, textvariable=self.url_var, width=55, style='TEntry')
        self.url_entry.pack(side="left", fill="x", expand=True)
        ToolTip(self.url_entry, "Paste a YouTube playlist URL or individual video URL here.")
        
        url_frame.pack(fill="x", padx=28, pady=(18, 0))
    
    def create_directory_section(self):
        """Create directory selection section."""
        dir_frame = ttk.Frame(self.root)
        ttk.Label(dir_frame, text="Download Folder:", style='TLabel').pack(side="left", padx=(0, 5))
        
        self.dir_var = tk.StringVar()
        self.dir_entry = ttk.Entry(dir_frame, textvariable=self.dir_var, width=40, style='TEntry')
        self.dir_entry.pack(side="left", fill="x", expand=True)
        ToolTip(self.dir_entry, "Choose where to save the downloaded files.")
        
        browse_btn = ttk.Button(dir_frame, text="Browse", command=self.browse_directory, style='TButton')
        browse_btn.pack(side="left", padx=(5, 0))
        ToolTip(browse_btn, "Browse for a folder.")
        
        dir_frame.pack(fill="x", padx=28, pady=(12, 0))
    
    def create_format_section(self):
        """Create format selection section."""
        format_frame = ttk.Frame(self.root)
        ttk.Label(format_frame, text="Format:", style='TLabel').pack(side="left", padx=(0, 5))
        
        self.audio_var = tk.IntVar(value=0)
        
        v_radio = ttk.Radiobutton(format_frame, text="Video (mp4)", variable=self.audio_var, value=0, style='TRadiobutton')
        v_radio.pack(side="left", padx=10)
        ToolTip(v_radio, "Download as video (mp4)")
        
        a_radio = ttk.Radiobutton(format_frame, text="Audio (mp3)", variable=self.audio_var, value=1, style='TRadiobutton')
        a_radio.pack(side="left", padx=10)
        ToolTip(a_radio, "Download as audio (mp3)")
        
        format_frame.pack(fill="x", padx=28, pady=(12, 0))
    
    def create_progress_section(self):
        """Create progress display section."""
        self.progress_label_var = tk.StringVar()
        self.progress_label = ttk.Label(self.root, textvariable=self.progress_label_var, 
                                       style='TLabel', anchor='w', font=('Segoe UI', 11, 'bold'))
        self.progress_label.pack(fill='x', padx=28, pady=(0, 2))
        self.progress_label_var.set('Progress: 0/0')
    
    def create_log_section(self):
        """Create output log section."""
        log_label = ttk.Label(self.root, text="Download Log:", style='TLabel')
        log_label.pack(anchor="w", padx=28, pady=(4, 0))
        
        log_frame = ttk.Frame(self.root)
        log_frame.pack(fill="both", expand=True, padx=28, pady=(0, 5))
        
        self.output_text = ScrolledText(log_frame, wrap=tk.WORD, height=2, state='disabled', 
                                       font=('Consolas', 11), bg='#f7f7f7', relief='flat', borderwidth=1)
        self.output_text.pack(side="left", fill="both", expand=True)
        
        # Setup log tags for color formatting
        color_tags = {
            'info': '#222',
            'warning': '#b58900',
            'error': '#d32f2f',
            'progress': '#1976d2'
        }
        for tag, color in color_tags.items():
            self.output_text.tag_configure(tag, foreground=color)
        
        # Clear log button
        clear_btn = ttk.Button(log_frame, text="Clear Log", command=self.clear_log, style='TButton')
        clear_btn.pack(side="right", padx=(5, 0), pady=2)
        ToolTip(clear_btn, "Clear the log output.")
    
    def create_control_buttons(self):
        """Create download and stop buttons."""
        self.download_btn = ttk.Button(self.root, text="Download Content", 
                                      style='Accent.TButton', state=tk.DISABLED, command=self.start_download)
        self.download_btn.pack(pady=8)
        ToolTip(self.download_btn, "Start downloading the playlist or video.")
        
        # Stop buttons frame for horizontal alignment
        stop_frame = ttk.Frame(self.root)
        stop_frame.pack(pady=(0, 10))
        
        stop_btn = ttk.Button(stop_frame, text="Stop Current", style='Danger.TButton', command=self.stop_download)
        stop_btn.pack(side="left", padx=(0, 5))
        ToolTip(stop_btn, "Stop the current download.")
        
        stop_all_btn = ttk.Button(stop_frame, text="Stop All", style='Danger.TButton', command=self.stop_all_downloads)
        stop_all_btn.pack(side="left", padx=(5, 0))
        ToolTip(stop_all_btn, "Stop all active downloads and clear queue.")
    
    def create_status_bar(self):
        """Create status bar."""
        self.status_var = tk.StringVar()
        status_bar = ttk.Label(self.root, textvariable=self.status_var, relief=tk.SUNKEN, anchor="w", style='TLabel')
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)
        self.status_var.set("Ready.")
    
    def setup_event_handlers(self):
        """Setup event handlers and validators."""
        self.url_var.trace_add('write', self.validate_url)
    
    def browse_directory(self):
        """Open directory browser dialog."""
        folder = filedialog.askdirectory()
        if folder:
            self.dir_var.set(folder)
    
    def clear_log(self):
        """Clear the output log."""
        self.output_text.configure(state='normal')
        self.output_text.delete(1.0, tk.END)
        self.output_text.configure(state='disabled')
        self.progress_var.set(0)
    
    def validate_url(self, *args):
        """Validate URL and enable/disable download button."""
        url = self.url_var.get().strip()
        if url and self.downloader.is_valid_youtube_url(url):
            self.download_btn.config(state=tk.NORMAL)
            if self.downloader.is_playlist_url(url):
                self.status_var.set("Ready to download playlist.")
            else:
                self.status_var.set("Ready to download video.")
        else:
            self.download_btn.config(state=tk.DISABLED)
            if url:
                self.status_var.set("Enter a valid YouTube URL.")
            else:
                self.status_var.set("Enter a YouTube playlist or video URL.")
    
    def start_download(self):
        """Start the download process."""
        url = self.url_var.get().strip()
        output_dir = self.dir_var.get().strip() or 'downloads'
        audio_only = self.audio_var.get() == 1
        
        if not url:
            messagebox.showerror("Error", "Please enter a YouTube URL.")
            return
        
        if not self.downloader.is_valid_youtube_url(url):
            messagebox.showerror("Error", "Please enter a valid YouTube URL.")
            return
        
        # Determine content type for user feedback
        content_type = "playlist" if self.downloader.is_playlist_url(url) else "video"
        print(f"Starting {content_type} download...")
        
        self.download_btn.config(state=tk.DISABLED)
        self.progress_var.set(0)
        self.status_var.set(f"Downloading {content_type}...")
        self.stop_flag['stop'] = False
        
        # Prepare callbacks for downloader
        gui_callbacks = {
            'button': self.download_btn,
            'progress_var': self.progress_var,
            'output_text': self.output_text,
            'stop_flag': self.stop_flag,
            'status_var': self.status_var,
            'progress_label_var': self.progress_label_var,
            'gui_instance': self  # Pass GUI instance for thread tracking
        }
        
        download_thread = self.downloader.download_content(url, output_dir, audio_only, gui_callbacks)
    
    def stop_download(self):
        """Stop the current download."""
        self.stop_flag['stop'] = True
        print("Stopping current download...")
        self.status_var.set("Stopping current download...")
    
    def stop_all_downloads(self):
        """Stop all active downloads."""
        self.stop_flag['stop'] = True
        
        # Stop all active download threads
        if self.active_downloads:
            print(f"Stopping {len(self.active_downloads)} active download(s)...")
            self.status_var.set(f"Stopping {len(self.active_downloads)} active download(s)...")
            
            # Set stop flag for all downloads
            for thread in self.active_downloads[:]:  # Use slice copy to avoid modification during iteration
                # The threads will check the stop_flag and terminate gracefully
                pass
            
            # Clear the active downloads list
            self.active_downloads.clear()
            
            # Reset UI state
            self.download_btn.config(state=tk.NORMAL)
            self.progress_var.set(0)
            self.progress_label_var.set('Progress: 0/0')
            
            print("All downloads stopped.")
            self.status_var.set("All downloads stopped.")
        else:
            print("No active downloads to stop.")
            self.status_var.set("No active downloads to stop.")
    
    def run(self):
        """Start the GUI main loop."""
        self.root.mainloop()


def main():
    """Main entry point."""
    app = PlaylistDownloaderGUI()
    app.run()


if __name__ == "__main__":
    main()
