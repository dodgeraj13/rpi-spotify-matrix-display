from PIL import Image, ImageDraw
from transitions import SlideTransition, ScaleTransition, ease_out_back

W, H = 64, 64

class PlayerLyrics:
    @staticmethod
    def generate(response, progress_ms, duration_ms, show_play, components, lyrics_frames, max_lyrics_frames, has_lyrics_now, lyric_transition_time, can_show_lyrics):
        img = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        t_total = lyrics_frames / max_lyrics_frames
        art_end = int(max_lyrics_frames * 16 / 28)
        art_t = min(1.0, lyrics_frames / art_end) if art_end > 0 else 1.0

        PlayerLyrics._transition_scrolling_text(components, art_t, t_total)
        PlayerLyrics._transition_album_art(components, art_t)
        PlayerLyrics._transition_play_indicator(components, t_total)
        
        if (lyrics_frames > 0) and has_lyrics_now:
            PlayerLyrics._draw_lyrics_text(draw, response.lyrics, progress_ms, 18, lyrics_frames, components.title_scroll.font, max_lyrics_frames, lyric_transition_time, can_show_lyrics)
        
        # Clear upper UI area to act as an efficient clip mask for the lyrics
        draw.rectangle((0, 0, W, 17), fill=(0, 0, 0))

        components.title_scroll.draw(draw)
        components.artist_scroll.draw(draw)
        
        PlayerLyrics._draw_progress_bar(draw, components, progress_ms, duration_ms, art_t, t_total, lyrics_frames, max_lyrics_frames)

        PlayerLyrics._draw_backgrounds(draw, components, art_t, t_total)
        
        components.album_art.draw(img, response.art_url)

        if t_total < 0.5:
            state = "Paused" if not response.is_playing else ("Play" if show_play else "Active")
        else:
            state = "Active"
        components.play_indicator.draw(draw, state)

        return img

    @staticmethod
    def _transition_scrolling_text(components, art_t, t_total):
        SlideTransition.apply(components.title_scroll, 1, 1, 17, 1, art_t)
        SlideTransition.apply(components.artist_scroll, 1, 7, 17, 7, art_t)
        
        current_right = int(53 + (63 - 53) * art_t)
        
        components.title_scroll.width = current_right - components.title_scroll.x
        components.artist_scroll.width = current_right - components.artist_scroll.x

    @staticmethod
    def _transition_album_art(components, art_t):
        ScaleTransition.apply(components.album_art, 8, 14, 48, 48, 1, 1, 15, 15, art_t)

    @staticmethod
    def _transition_play_indicator(components, t_total):
        if t_total < 0.5:
            sub_t = t_total * 2
            SlideTransition.apply(components.play_indicator, 56, 3, W, 3, sub_t)
        else:
            sub_t = (t_total - 0.5) * 2
            SlideTransition.apply(components.play_indicator, W, 54, 56, 54, sub_t)
        components.play_indicator.width, components.play_indicator.height = 4, 6

    @staticmethod
    def _draw_backgrounds(draw, components, art_t, t_total):
        text_x = components.title_scroll.x
        btn_x = components.play_indicator.x
        btn_y = components.play_indicator.y
        
        if btn_x < W:
            draw.rectangle((btn_x - 3, btn_y - 3, W - 1, btn_y + 9), fill=(0, 0, 0))

        if art_t > 0.5: 
            draw.rectangle((0, 0, text_x - 1, 16), fill=(0, 0, 0))
            
        draw.rectangle((W - 1, 0, W - 1, 16), fill=(0, 0, 0))

    @staticmethod
    def _draw_progress_bar(draw, components, progress_ms, duration_ms, art_t, t_total, lyrics_frames, max_lyrics_frames):
        text_x = components.title_scroll.x
        btn_x = int(56 + (W + 3 - 56) * (1.0 - t_total))
        text_width = btn_x - 3 - text_x - 1
        
        if art_t < 0.5:
            bar_y = 62 + int(art_t * 4)
            if bar_y < 64:
                SlideTransition.apply(components.progress_bar, 0, 62, 0, 66, art_t * 2)
                components.progress_bar.draw(draw, progress_ms, duration_ms)

        bar_width = W - text_x - 1 if t_total > 0 else text_width
        
        bar_start = int(max_lyrics_frames * 16 / 28.0)
        bar_end = int(max_lyrics_frames)
        
        if lyrics_frames > bar_start:
            grow_t = min(1.0, (lyrics_frames - bar_start) / max(1, bar_end - bar_start))
            current_bar_width = int(bar_width * grow_t)
            
            if current_bar_width > 0:
                draw.rectangle((text_x, 14, text_x + current_bar_width - 1, 15), fill=(100, 100, 100))
                
            green_w = round(current_bar_width * progress_ms / duration_ms) if duration_ms > 0 else 0
            if green_w > 0:
                draw.rectangle((text_x, 14, text_x + green_w - 1, 15), fill=(102, 240, 110))
        elif t_total == 1.0:
            components.progress_bar.x, components.progress_bar.y = text_x, 14
            components.progress_bar.width, components.progress_bar.height = bar_width, 2
            components.progress_bar.draw(draw, progress_ms, duration_ms)

    @staticmethod
    def _draw_lyrics_text(draw, lyrics, progress_ms, y_offset, lyrics_frames, font, max_lyrics_frames, lyric_transition_time, can_show_lyrics):
        lyrics_text_start = int(max_lyrics_frames * 23 / 28)
        
        # Determine the initial appearance delay (for rain-in entry).
        if can_show_lyrics:
            ms_since_appear = max(0.0, (lyric_transition_time * 1000.0) - (lyrics_text_start * (1000.0 / 60.0)))
        else:
            ms_since_appear = 10000.0
        
        text = None
        current_line_start_ms = 0
        next_line_start_ms = None
        for line in lyrics['lyrics']['lines']:
            start_ms = int(line['startTimeMs'])
            line_text = line['words'].strip()
            if start_ms <= progress_ms:
                if line_text and line_text != "♪":
                    text = line_text
                    current_line_start_ms = start_ms
            elif line_text and line_text != "♪":
                next_line_start_ms = start_ms
                break
        
        if not text: return
        
        # For lyrics display entry: skip the current lyric if it was already playing
        # and has less than 0.5s left from the moment it first appeared.
        entry_progress_ms = progress_ms - ms_since_appear
        if current_line_start_ms < entry_progress_ms and next_line_start_ms:
            if next_line_start_ms - entry_progress_ms < 500:
                return

        words = text.split()
        out, cur = [], ""
        for word in words:
            if font.getlength(f"{cur} {word}".strip()) <= W - 4:
                cur = f"{cur} {word}".strip()
            else:
                if cur: out.append(cur)
                cur, rem = "", word
                while rem:
                    if font.getlength(rem) <= W - 4:
                        cur = rem
                        break
                    
                    found = False
                    for i in range(len(rem) - 1, 0, -1):
                        if rem[i] == '-' and font.getlength(rem[:i+1]) <= W - 4:
                            out.append(rem[:i+1])
                            rem, found = rem[i+1:], True
                            break
                    if found: continue
                    
                    for i in range(len(rem) - 1, 0, -1):
                        if font.getlength(rem[:i] + "-") <= W - 4:
                            out.append(rem[:i] + "-")
                            rem, found = rem[i:], True
                            break
                    if not found:
                        out.append(rem[0])
                        rem = rem[1:]
        if cur: out.append(cur)

        fade_in_duration_ms = 250
        line_stagger_in_ms = 0
        
        fade_out_duration_ms = 250
        line_stagger_out_ms = 0
        total_out_duration_ms = fade_out_duration_ms + (len(out) - 1) * line_stagger_out_ms if out else fade_out_duration_ms

        exit_fade_duration_ms = 250
        exit_fade_alpha = 1.0
        if not can_show_lyrics:
            trans_ms = lyric_transition_time * 1000.0
            exit_fade_alpha = max(0.0, 1.0 - (trans_ms / exit_fade_duration_ms))

        for i, line in enumerate(out):
            # Anim is relative to min of song timing vs appearance timing
            time_at_target_ms = progress_ms - current_line_start_ms
            line_elapsed_ms = min(time_at_target_ms, ms_since_appear) - (i * line_stagger_in_ms)
            
            line_fade_in_t = max(0.0, min(1.0, line_elapsed_ms / fade_in_duration_ms))
            
            line_fade_out_t = 1.0
            y_offset_anim = 0.0
            
            if line_fade_in_t < 1.0:
                in_progress = line_fade_in_t
                # Quadratic deceleration (ease out) without overshoot
                y_offset_anim += ((1.0 - in_progress) ** 2) * 12.0

            if next_line_start_ms:
                time_until_next = next_line_start_ms - progress_ms
                out_elapsed = total_out_duration_ms - time_until_next
                line_out_elapsed = out_elapsed - (i * line_stagger_out_ms)
                if line_out_elapsed > 0:
                    out_progress = min(1.0, line_out_elapsed / fade_out_duration_ms)
                    line_fade_out_t = 1.0 - out_progress
                    # Quadratic easing (out_progress^2) accelerating upwards
                    y_offset_anim += -((out_progress ** 2) * 12.0)

            # Combine fade-in, next-line fade-out, and exit transition fade-out
            line_alpha = line_fade_in_t * line_fade_out_t * exit_fade_alpha
            fill_c = int(255 * line_alpha)
            fill = (fill_c, fill_c, fill_c)

            y = y_offset + i * 6 + y_offset_anim
            if y + 6 > H: break
            if y > -6 and fill_c > 0:
                draw.text((2, int(y)), line, fill=fill, font=font)


