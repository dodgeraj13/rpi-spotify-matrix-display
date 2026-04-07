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
from lyrics_fetcher import LyricsFetcher


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
        self.lyrics_fetcher = LyricsFetcher(config)
        self.device_whitelist = self._parse_whitelist(config)
        self.rate_limit_until = 0.0
        self._device_cache: bool = True
        self._last_device_check: float = 0.0
        
        self._setup_spotify()

    def _setup_spotify(self):
        try:
            cfg = self.config['Spotify']
            os.environ["SPOTIPY_CLIENT_ID"] = cfg['client_id']
            os.environ["SPOTIPY_CLIENT_SECRET"] = cfg['client_secret']
            os.environ["SPOTIPY_REDIRECT_URI"] = "http://127.0.0.1:8080/callback"
            
            self.spotify = spotipy.Spotify(
                auth_manager=SpotifyOAuth(
                    scope="user-read-currently-playing, user-read-playback-state",
                    open_browser=False
                ),
                requests_timeout=10
            )
        except Exception as e:
            print(f"Spotify setup failed: {e}")



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
            if getattr(e, 'http_status', 0) == 401 and self.spotify:
                try:
                    token_info = self.spotify.auth_manager.cache_handler.get_cached_token()
                    if token_info and 'refresh_token' in token_info:
                        print("Spotify 401 - Forcing token refresh")
                        self.spotify.auth_manager.refresh_access_token(token_info['refresh_token'])
                except Exception as refresh_err:
                    print(f"Failed to force token refresh: {refresh_err}")
            self._handle_rate_limit(e)
            return None
        except Exception as e:
            return None

    def _process_track(self, track) -> PlaybackInfo:
        item = track['item']
        if not item:
             return PlaybackInfo(None, None, None, track['is_playing'], track.get('progress_ms', 0), 0)

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
            lyrics=self.lyrics_fetcher.get_lyrics(item['id']),
            track_id=item['id']
        )

    def _is_whitelisted_device(self) -> bool:
        if not self.device_whitelist:
            return True

        now = time.time()
        if now - self._last_device_check < 5.0:
            return self._device_cache

        try:
             devices = self.spotify.devices()
             self._last_device_check = now
             for d in devices.get('devices', []):
                 if d.get('is_active') and d.get('name') in self.device_whitelist:
                     self._device_cache = True
                     return True
             self._device_cache = False
             return False
        except Exception:
            return self._device_cache

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
