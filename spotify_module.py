#!/usr/bin/env python3
"""
spotify_module.py: Spotify API integration and authentication for the matrix display.
"""

import os
from dataclasses import dataclass
from queue import LifoQueue
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth

from syrics.api import Spotify as SyricsSpotify

@dataclass
class SpotifyConfig:
    """Configuration for Spotify API."""
    client_id: str
    client_secret: str
    redirect_uri: str
    sp_dc: Optional[str] = None


@dataclass
class PlaybackInfo:
    """Information about current playback."""
    artist: Optional[str]
    title: Optional[str]
    art_url: Optional[str]
    is_playing: bool
    progress_ms: int
    duration_ms: int
    lyrics: Optional[dict] = None
    track_id: Optional[str] = None


class SpotifyModule:
    """Main Spotify integration module."""
    
    def __init__(self, config):
        self.config = config
        self.invalid = False
        self.calls = 0
        self.queue: LifoQueue = LifoQueue()
        self.spotify: Optional[spotipy.Spotify] = None
        self.auth_manager: Optional[SpotifyOAuth] = None
        self.is_playing = False

        self.spl: Optional[SyricsSpotify] = None
        self.last_track_id: Optional[str] = None
        self.last_lyrics: Optional[str] = None
        # Track which track we already retried lyrics for (after reinit) to avoid reinit loops
        self._lyrics_retried_for_track: Optional[str] = None

        spotify_config = self._get_spotify_config()

        self._setup_spotify(spotify_config)
        self._setup_syrics(spotify_config)
    
    def _setup_spotify(self, spotify_config: SpotifyConfig):
        """Setup Spotify authentication and client."""
        try:
            if not spotify_config:
                self.invalid = True
                return
            
            os.environ["SPOTIPY_CLIENT_ID"] = spotify_config.client_id
            os.environ["SPOTIPY_CLIENT_SECRET"] = spotify_config.client_secret
            os.environ["SPOTIPY_REDIRECT_URI"] = spotify_config.redirect_uri
            
            self.auth_manager = SpotifyOAuth(
                scope="user-read-currently-playing, user-read-playback-state",
                open_browser=False
            )
            
            self.spotify = spotipy.Spotify(
                auth_manager=self.auth_manager,
                requests_timeout=10
            )
            
        except Exception as e:
            print(f"Error setting up Spotify module: {e}")
            self.invalid = True
    
    def _setup_syrics(self, spotify_config: SpotifyConfig):
        """Setup SyricsSpotify for lyrics fetching."""
        if spotify_config.sp_dc:
            try:
                self.spl = SyricsSpotify(spotify_config.sp_dc)
            except Exception as e:
                print(f"Warning: Could not initialize SyricsSpotify: {e}")
                self.spl = None
        else:
            print("Warning: sp_dc not provided, lyrics fetching will be disabled")
            self.spl = None

    def _reinit_syrics(self) -> bool:
        """Re-initialize SyricsSpotify (e.g. after token expiry). Returns True if successful."""
        spotify_config = self._get_spotify_config()
        if not spotify_config or not spotify_config.sp_dc:
            return False
        try:
            self.spl = SyricsSpotify(spotify_config.sp_dc)
            print("Lyrics client re-initialized (token/session refreshed).")
            return True
        except Exception as e:
            print(f"Could not re-initialize lyrics client: {e}")
            self.spl = None
            return False

    def _fetch_lyrics_with_retry(self, track_id: str):
        """Fetch lyrics for track_id, re-initializing SyricsSpotify and retrying once on exception."""
        if not self.spl:
            return None
        try:
            result = self.spl.get_lyrics(track_id)
            if result is not None:
                self._lyrics_retried_for_track = None  # success; allow retry for next track
            return result
        except Exception as e:
            print(f"Error fetching lyrics for track {track_id}: {e}")
        # Retry once after re-initializing (handles expired token / stale session)
        self._lyrics_retried_for_track = track_id  # avoid double reinit in _fetch_lyrics_with_retry_on_none
        if self._reinit_syrics():
            try:
                result = self.spl.get_lyrics(track_id)
                if result is not None:
                    self._lyrics_retried_for_track = None
                return result
            except Exception as e2:
                print(f"Error fetching lyrics after reinit: {e2}")
        return None

    def _fetch_lyrics_with_retry_on_none(self, track_id: str):
        """Fetch lyrics; if first attempt returns None, reinit and retry once (handles 401->None)."""
        first = self._fetch_lyrics_with_retry(track_id)
        if first is not None:
            return first
        if self._lyrics_retried_for_track == track_id:
            return None  # already retried for this track (exception path or previous None retry)
        self._lyrics_retried_for_track = track_id
        if self._reinit_syrics():
            try:
                result = self.spl.get_lyrics(track_id)
                if result is not None:
                    self._lyrics_retried_for_track = None
                return result
            except Exception as e:
                print(f"Error fetching lyrics after reinit: {e}")
        return None

    def _get_spotify_config(self) -> Optional[SpotifyConfig]:
        """Extract Spotify configuration from config parser."""
        if not self.config or 'Spotify' not in self.config:
            print("[Spotify Module] Missing Spotify configuration section")
            return None
        
        spotify_section = self.config['Spotify']
        required_fields = ['client_id', 'client_secret', 'redirect_uri']
        
        for field in required_fields:
            if field not in spotify_section:
                print(f"[Spotify Module] Missing required field: {field}")
                return None
            
            value = spotify_section[field].strip()
            if not value:
                print(f"[Spotify Module] Empty value for field: {field}")
                return None
        
        return SpotifyConfig(
            client_id=spotify_section['client_id'],
            client_secret=spotify_section['client_secret'],
            redirect_uri=spotify_section['redirect_uri'],
            sp_dc=spotify_section.get('sp_dc')
        )
    
    def is_device_whitelisted(self, device_name: Optional[str] = None) -> bool:
        """Check if the given device (or current active device) is in the whitelist.

        Prefer passing device_name from the currently-playing response so we whitelist
        the device that is actually playing (e.g. AVR), not the controller (e.g. phone).
        """
        if not self.config or 'Spotify' not in self.config:
            return True

        spotify_section = self.config['Spotify']
        if 'device_whitelist' not in spotify_section:
            return True

        whitelist = self._parse_device_whitelist(spotify_section['device_whitelist'])

        # Use the device from the playback response (the one actually playing)
        if device_name is not None:
            return device_name.strip() in [d.strip() for d in whitelist]

        # Fallback: no playback context, check devices() for an active whitelisted device
        try:
            if not self.spotify:
                return False
            devices = self.spotify.devices()
            return any(
                device['name'] in whitelist and device['is_active']
                for device in devices['devices']
            )
        except Exception as e:
            print(f"Error checking device whitelist: {e}")
            return False
    
    def _parse_device_whitelist(self, device_whitelist):
        """Parse device whitelist from config."""
        if isinstance(device_whitelist, str):
            return [d.strip().strip("'\"") for d in device_whitelist.strip('[]').split(',')]
        return device_whitelist
    
    def get_current_playback(self) -> Optional[PlaybackInfo]:
        """Get current playback information from Spotify."""
        if self.invalid or not self.spotify:
            return None
        
        try:
            track = self.spotify.current_user_playing_track()

            if not track:
                return None

            # Use the device from the playback response (actually playing), not devices() "active"
            playing_device_name = (track.get('device') or {}).get('name')
            if not self.is_device_whitelisted(playing_device_name):
                return None
            
            playback_info = self._create_playback_info(track)
            self.is_playing = track['is_playing']
            self.queue.put(playback_info)
            
            return playback_info
            
        except Exception as e:
            print(f"Error getting current playback: {e}")
            return None
    
    def _create_playback_info(self, track) -> PlaybackInfo:
        """Create PlaybackInfo from Spotify track data."""
        if track['item'] is None:
            return PlaybackInfo(
                artist=None,
                title=None,
                art_url=None,
                is_playing=track['is_playing'],
                progress_ms=track.get('progress_ms', 0),
                duration_ms=0,
                lyrics=None,
                track_id=None
            )
        
        artist = self._format_artist_names(track['item']['artists'])
        title = track['item']['name']
        art_url = self._get_album_art_url(track['item']['album'])
        
        track_id = track['item']['id'] if track['item'] else None
        lyrics = None
        
        # Fetch lyrics if we have a SyricsSpotify instance and a new track
        if self.spl and track_id:
            if track_id != self.last_track_id:
                lyrics_result = self._fetch_lyrics_with_retry_on_none(track_id)
                self.last_lyrics = lyrics_result
                self.last_track_id = track_id
            lyrics = self.last_lyrics
        
        return PlaybackInfo(
            artist=artist,
            title=title,
            art_url=art_url,
            is_playing=track['is_playing'],
            progress_ms=track.get('progress_ms', 0),
            duration_ms=track['item'].get('duration_ms', 0),
            lyrics=lyrics,
            track_id=track_id
        )
    
    def _format_artist_names(self, artists):
        """Format artist names for display."""
        if len(artists) >= 2:
            return f"{artists[0]['name']}, {artists[1]['name']}"
        return artists[0]['name']
    
    def _get_album_art_url(self, album):
        """Extract album art URL from album data."""
        if album['images']:
            return album['images'][0]['url']
        return None
