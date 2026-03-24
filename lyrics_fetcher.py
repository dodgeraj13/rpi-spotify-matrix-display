#!/usr/bin/env python3
"""Lyrics fetching module."""
import time
import threading
from typing import Optional

from librelyrics import LibreLyrics
from librelyrics.exceptions import RateLimitError, LyricsNotFound


class LyricsFetcher:
    def __init__(self, config):
        self.config = config
        self.ll: Optional[LibreLyrics] = None
        self.last_track_id: Optional[str] = None
        self.last_lyrics: Optional[dict] = None
        self.rate_limit_until = 0.0
        self._fetching_lyrics_id: Optional[str] = None
        
        self._setup_librelyrics()

    def _setup_librelyrics(self):
        sp_dc = self.config.get('Spotify', 'sp_dc', fallback=None)
        if sp_dc:
            try:
                self.ll = LibreLyrics(config={'plugins': {'spotify': {'sp_dc': sp_dc}}})
                print("LibreLyrics initialized successfully")
            except Exception as e:
                print(f"LibreLyrics setup failed: {e}")
                import traceback
                traceback.print_exc()
                self.ll = None

    def get_lyrics(self, track_id: str) -> Optional[dict]:
        if not self.ll or not track_id:
            return None
            
        if track_id != self.last_track_id:
            if self._fetching_lyrics_id == track_id or time.time() < self.rate_limit_until:
                return None
            
            self._fetching_lyrics_id = track_id
            
            def fetch_thread():
                try:
                    res = self.ll.fetch(f"https://open.spotify.com/track/{track_id}")
                    lines = []
                    for line in res.lyrics:
                        lines.append({
                            'startTimeMs': line.start_ms if line.start_ms is not None else 0,
                            'words': line.text
                        })
                    is_synced = any(line.start_ms is not None for line in res.lyrics)
                    self.last_lyrics = {
                        'lyrics': {
                            'lines': lines,
                            'syncType': 'LINE_SYNCED' if is_synced else 'UNSYNCED'
                        }
                    }
                    self.last_track_id = track_id
                except RateLimitError as e:
                    retry = getattr(e, 'retry_after', 30) or 30
                    self.rate_limit_until = time.time() + retry
                    print(f"fetch_lyrics rate limited for {track_id} (retry in {retry}s): {e}")
                    self.last_lyrics = None
                    self.last_track_id = track_id
                except LyricsNotFound:
                    self.last_lyrics = None
                    self.last_track_id = track_id
                except Exception as e:
                    print(f"fetch_lyrics failed for {track_id}: {e}")
                    self.last_lyrics = None
                    self.last_track_id = track_id
                finally:
                    self._fetching_lyrics_id = None
            
            threading.Thread(target=fetch_thread, daemon=True).start()
            return None
            
        return self.last_lyrics
