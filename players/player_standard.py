from PIL import Image, ImageDraw

W, H = 64, 64
LYRICS_WIDTH = 60
FADE_MS = 300

class PlayerStandard:
    @staticmethod
    def generate(response, progress_ms, duration_ms, show_play, components, lyrics_mode="off", lyric_transition_time=10.0):
        img = Image.new("RGB", (W, H), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        components.title_scroll.x = 1
        components.title_scroll.y = 1
        components.title_scroll.width = 52

        components.artist_scroll.x = 1
        components.artist_scroll.y = 7
        components.artist_scroll.width = 52

        components.progress_bar.x = 0
        components.progress_bar.y = 62
        components.progress_bar.width = 64
        components.progress_bar.height = 2

        components.album_art.x, components.album_art.y, components.album_art.width, components.album_art.height = 8, 14, 48, 48
        
        components.play_indicator.x, components.play_indicator.y = 56, 3
        components.play_indicator.width, components.play_indicator.height = 4, 6

        components.title_scroll.draw(draw)
        components.artist_scroll.draw(draw)
        components.progress_bar.draw(draw, progress_ms, duration_ms)
        
        draw.rectangle((53, 0, 63, 12), fill=(0, 0, 0))
        draw.rectangle((W - 1, 0, W - 1, 16), fill=(0, 0, 0))

        components.album_art.draw(img, response.art_url)

        if lyrics_mode == 'standard' and response.is_playing and response.lyrics and response.lyrics.get('lyrics', {}).get('syncType') == 'LINE_SYNCED':
            valid_lines = []
            for l in response.lyrics['lyrics'].get('lines', []):
                w = l.get('words', '').strip()
                if w and w != "♪":
                    valid_lines.append({
                        'start_ms': int(l.get('startTimeMs', 0)),
                        'end_ms': int(l.get('endTimeMs', 0)),
                        'text': w
                    })

            bg_alpha = 0.0
            text_alpha = 0.0
            text_to_draw = None

            ms_since_appear = lyric_transition_time * 1000.0
            global_fade_in = max(0.0, min(1.0, ms_since_appear / float(FADE_MS)))

            for i, line in enumerate(valid_lines):
                s = line['start_ms']
                e = line['end_ms']
                if i + 1 < len(valid_lines):
                    next_s = valid_lines[i+1]['start_ms']
                    if e <= s or e > next_s or (next_s - e) < FADE_MS:
                        e = next_s
                else:
                    if e <= s:
                        e = s + 5000

                if progress_ms >= s - FADE_MS and progress_ms <= e:
                    bg_in = min(1.0, (progress_ms - (s - FADE_MS)) / float(FADE_MS))
                    bg_out = min(1.0, (e - progress_ms) / float(FADE_MS))
                    bg_alpha += max(0.0, min(bg_in, bg_out))

                if progress_ms >= s and progress_ms <= e:
                    tf_in = min(1.0, (progress_ms - s) / float(FADE_MS))
                    tf_out = min(1.0, (e - progress_ms) / float(FADE_MS))
                    
                    if i + 1 < len(valid_lines):
                        next_s = valid_lines[i+1]['start_ms']
                        if progress_ms >= next_s:
                            tf_out = 0.0
                        elif next_s - progress_ms < FADE_MS:
                            tf_out = min(tf_out, (next_s - progress_ms) / float(FADE_MS))
                            
                    t_alpha = max(0.0, min(tf_in, tf_out))
                    if t_alpha > text_alpha:
                        text_alpha = t_alpha
                        text_to_draw = line['text']

            bg_alpha = min(1.0, bg_alpha) * global_fade_in
            text_alpha = text_alpha * global_fade_in

            if bg_alpha > 0.01:
                dimmer = Image.new("RGBA", (48, 48), (0, 0, 0, int(160 * bg_alpha)))
                img.paste(dimmer, (8, 14), dimmer)
            
            if text_to_draw and text_alpha > 0.01:
                font = components.title_scroll.font
                words = text_to_draw.split()
                out, cur = [], ""
                for word in words:
                    if font.getlength(f"{cur} {word}".strip()) <= LYRICS_WIDTH:
                        cur = f"{cur} {word}".strip()
                    else:
                        if cur: out.append(cur)
                        cur, rem = "", word
                        while rem:
                            if font.getlength(rem) <= LYRICS_WIDTH:
                                cur = rem
                                break
                            
                            found = False
                            for i_c in range(len(rem) - 1, 0, -1):
                                if rem[i_c] == '-' and font.getlength(rem[:i_c+1]) <= LYRICS_WIDTH:
                                    out.append(rem[:i_c+1])
                                    rem, found = rem[i_c+1:], True
                                    break
                            if found: continue
                            
                            for i_c in range(len(rem) - 1, 0, -1):
                                if font.getlength(rem[:i_c] + "-") <= LYRICS_WIDTH:
                                    out.append(rem[:i_c] + "-")
                                    rem, found = rem[i_c:], True
                                    break
                            if not found:
                                out.append(rem[0])
                                rem = rem[1:]
                if cur: out.append(cur)
                if len(out) > 7: out = out[:7]
                
                total_height = len(out) * 6
                y_start = 14 + (48 - total_height) // 2
                
                text_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                text_draw = ImageDraw.Draw(text_img)
                c_alpha = int(255 * text_alpha)
                
                for i_line, text_line in enumerate(out):
                    w = font.getlength(text_line)
                    x = 2 + (LYRICS_WIDTH - w) // 2
                    text_draw.text((x, y_start + i_line * 6), text_line, fill=(255, 255, 255, c_alpha), font=font)
                    
                img.paste(text_img, (0, 0), text_img)

        draw.rectangle((55, 0, 63, 12), fill=(0, 0, 0))
        state = "Paused" if not response.is_playing else ("Play" if show_play else "Active")
        components.play_indicator.draw(draw, state)

        return img
