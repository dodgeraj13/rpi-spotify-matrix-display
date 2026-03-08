#!/usr/bin/env python3
"""Spotify API integration."""
import os
import time
from dataclasses import dataclass
from queue import LifoQueue
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.exceptions import SpotifyException
from librelyrics import LibreLyrics


@dataclass
class PlaybackInfo:
    artist: Optional[str]
    title: Optional[str]
    art_url: Optional[str]
    is_playing: bool
    progress_ms: int
    duration_ms: int
    lyrics: Optional[dict] = None
    track_id: Optional[str] = None


class SpotifyModule:

    def __init__(self, config):
        self.config = config
        self.queue = LifoQueue()
        self.spotify: Optional[spotipy.Spotify] = None
        self.ll: Optional[LibreLyrics] = None
        self.last_track_id = None
        self.last_lyrics = None
        self.device_whitelist = self._parse_whitelist(config)
        self.rate_limit_until = 0.0
        
        self._setup_spotify()
        self._setup_librelyrics()

    def _setup_spotify(self):
        try:
            cfg = self.config['Spotify']
            os.environ["SPOTIPY_CLIENT_ID"] = cfg['client_id']
            os.environ["SPOTIPY_CLIENT_SECRET"] = cfg['client_secret']
            os.environ["SPOTIPY_REDIRECT_URI"] = cfg['redirect_uri']
            
            self.spotify = spotipy.Spotify(
                auth_manager=SpotifyOAuth(
                    scope="user-read-currently-playing, user-read-playback-state",
                    open_browser=False
                ),
                requests_timeout=10
            )
        except Exception as e:
            print(f"Spotify setup failed: {e}")

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

    def get_current_playback(self) -> Optional[PlaybackInfo]:
        if not self.spotify or time.time() < self.rate_limit_until:
            return None

        try:
            track = self.spotify.current_user_playing_track()
            if not track or not self._is_whitelisted_device():
                return None

            info = self._process_track(track)
            self.queue.put(info)
            return info

        except SpotifyException as e:
            self._handle_rate_limit(e)
            return None
        except Exception as e:
            # print(f"Error getting playback: {e}")
            return None

    def _process_track(self, track) -> PlaybackInfo:
        item = track['item']
        if not item:
             return PlaybackInfo(None, None, None, track['is_playing'], track.get('progress_ms', 0), 0)

        # Simplify: Assume proper song structure
        artists = item['artists']
        artist_text = artists[0]['name']
        if len(artists) > 1:
            artist_text += f", {artists[1]['name']}"
            
        images = item['album']['images']
        art_url = images[0]['url'] if images else None
        
        return PlaybackInfo(
            artist=artist_text,
            title=item['name'],
            art_url=art_url,
            is_playing=track['is_playing'],
            progress_ms=track.get('progress_ms', 0),
            duration_ms=item.get('duration_ms', 0),
            lyrics=self._get_lyrics(item['id']),
            track_id=item['id']
        )

    def _get_lyrics(self, track_id: str) -> Optional[dict]:
        if not self.ll or not track_id:
            return None
            
        if track_id != self.last_track_id:
            def fetch_lyrics() -> Optional[dict]:
                res = self.ll.fetch(f"https://open.spotify.com/track/{track_id}")
                lines = []
                for line in res.lyrics:
                    lines.append({
                        'startTimeMs': line.start_ms if line.start_ms is not None else 0,
                        'words': line.text
                    })
                is_synced = any(line.start_ms is not None for line in res.lyrics)
                return {
                    'lyrics': {
                        'lines': lines,
                        'syncType': 'LINE_SYNCED' if is_synced else 'UNSYNCED'
                    }
                }
                
            try:
                self.last_lyrics = fetch_lyrics()
            except Exception as e:
                print(f"fetch_lyrics failed for {track_id}: {e}")
                import traceback
                traceback.print_exc()
                self._setup_librelyrics()
                try:
                    self.last_lyrics = fetch_lyrics()
                except Exception as e2:
                    print(f"fetch_lyrics retry failed: {e2}")
                    self.last_lyrics = None
            self.last_track_id = track_id
            
        return self.last_lyrics

    def _is_whitelisted_device(self) -> bool:
        if not self.device_whitelist:
            return True
        try:
             devices = self.spotify.devices()
             for d in devices.get('devices', []):
                 if d.get('is_active') and d.get('name') in self.device_whitelist:
                     return True
             return False
        except Exception:
            return False

    def _parse_whitelist(self, config):
        if 'Spotify' not in config: return []
        if 'device_whitelist' not in config['Spotify']: return []
        wl = config['Spotify']['device_whitelist']
        return [x.strip().strip("'") for x in wl.strip("[]").split(',')] if isinstance(wl, str) else wl

    def _handle_rate_limit(self, e: SpotifyException):
        if e.http_status == 429:
            retry = int(e.headers.get("Retry-After", 30))
            self.rate_limit_until = time.time() + retry
            print(f"Rate limited. Pausing for {retry}s")
