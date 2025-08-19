#!/usr/bin/env python3
"""
Spotify Module

Handles Spotify API integration and authentication for the matrix display.
"""

import os
import time
from dataclasses import dataclass
from queue import LifoQueue
from typing import Optional

import spotipy
from spotipy.oauth2 import SpotifyOAuth


@dataclass
class SpotifyConfig:
    """Configuration for Spotify API."""
    client_id: str
    client_secret: str
    redirect_uri: str
    scope: str = "user-read-currently-playing, user-read-playback-state, user-modify-playback-state"


@dataclass
class PlaybackInfo:
    """Information about current playback."""
    artist: Optional[str]
    title: Optional[str]
    art_url: Optional[str]
    is_playing: bool
    progress_ms: int
    duration_ms: int


class SpotifyModule:
    """Main Spotify integration module."""
    
    def __init__(self, config):
        self.config = config
        self.invalid = False
        self.calls = 0
        self.queue: LifoQueue = LifoQueue()
        self.sp: Optional[spotipy.Spotify] = None
        self.auth_manager: Optional[SpotifyOAuth] = None
        self.is_playing = False
        
        self._setup_spotify()
    
    def _setup_spotify(self):
        """Setup Spotify authentication and client."""
        try:
            spotify_config = self._get_spotify_config()
            if not spotify_config:
                self.invalid = True
                return
            
            os.environ["SPOTIPY_CLIENT_ID"] = spotify_config.client_id
            os.environ["SPOTIPY_CLIENT_SECRET"] = spotify_config.client_secret
            os.environ["SPOTIPY_REDIRECT_URI"] = spotify_config.redirect_uri
            
            self.auth_manager = SpotifyOAuth(
                scope=spotify_config.scope,
                open_browser=False
            )
            
            auth_url = self.auth_manager.get_authorize_url()
            print(f"Please visit this URL to authorize: {auth_url}")
            
            self.sp = spotipy.Spotify(
                auth_manager=self.auth_manager,
                requests_timeout=10
            )
            
            print("Spotify module initialized successfully")
            
        except Exception as e:
            print(f"Error setting up Spotify module: {e}")
            self.invalid = True
    
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
            redirect_uri=spotify_section['redirect_uri']
        )
    
    def is_device_whitelisted(self) -> bool:
        """Check if current device is in the whitelist."""
        if not self.config or 'Spotify' not in self.config:
            return True
        
        spotify_section = self.config['Spotify']
        if 'device_whitelist' not in spotify_section:
            return True
        
        try:
            if not self.sp:
                return False
            
            devices = self.sp.devices()
            device_whitelist = spotify_section['device_whitelist']
            
            if isinstance(device_whitelist, str):
                whitelist_devices = [d.strip().strip("'\"") for d in device_whitelist.strip('[]').split(',')]
            else:
                whitelist_devices = device_whitelist
            
            for device in devices['devices']:
                if (device['name'] in whitelist_devices and device['is_active']):
                    return True
            
            return False
            
        except Exception as e:
            print(f"Error checking device whitelist: {e}")
            return False
    
    def get_current_playback(self) -> Optional[PlaybackInfo]:
        """Get current playback information from Spotify."""
        if self.invalid or not self.sp:
            return None
        
        try:
            track = self.sp.current_user_playing_track()
            
            if not track or not self.is_device_whitelisted():
                return None
            
            if track['item'] is None:
                playback_info = PlaybackInfo(
                    artist=None,
                    title=None,
                    art_url=None,
                    is_playing=track['is_playing'],
                    progress_ms=track.get('progress_ms', 0),
                    duration_ms=0
                )
            else:
                artists = track['item']['artists']
                if len(artists) >= 2:
                    artist = f"{artists[0]['name']}, {artists[1]['name']}"
                else:
                    artist = artists[0]['name']
                
                title = track['item']['name']
                art_url = track['item']['album']['images'][0]['url'] if track['item']['album']['images'] else None
                
                playback_info = PlaybackInfo(
                    artist=artist,
                    title=title,
                    art_url=art_url,
                    is_playing=track['is_playing'],
                    progress_ms=track.get('progress_ms', 0),
                    duration_ms=track['item'].get('duration_ms', 0)
                )
            
            self.is_playing = track['is_playing']
            self.queue.put(playback_info)
            
            return playback_info
            
        except Exception as e:
            print(f"Error getting current playback: {e}")
            return None
