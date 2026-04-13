from PIL import Image, ImageDraw

W, H = 64, 64
LYRICS_WIDTH = 60

class PlayerStandard:
    @staticmethod
    def generate(response, progress_ms, duration_ms, show_play, components, lyrics_mode="off"):
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
            text = None
            for line in response.lyrics['lyrics'].get('lines', []):
                start_ms = int(line.get('startTimeMs', 0))
                end_ms = int(line.get('endTimeMs', 0))
                line_text = line.get('words', '').strip()
                if start_ms <= progress_ms:
                    if not line_text or line_text == "♪":
                        text = None
                    elif end_ms > 0 and progress_ms > end_ms:
                        text = None
                    else:
                        text = line_text
                elif line_text and line_text != "♪":
                    break
            
            if text:
                dimmer = Image.new("RGBA", (48, 48), (0, 0, 0, 160))
                img.paste(dimmer, (8, 14), dimmer)
                
                font = components.title_scroll.font
                words = text.split()
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
                            for i in range(len(rem) - 1, 0, -1):
                                if rem[i] == '-' and font.getlength(rem[:i+1]) <= LYRICS_WIDTH:
                                    out.append(rem[:i+1])
                                    rem, found = rem[i+1:], True
                                    break
                            if found: continue
                            
                            for i in range(len(rem) - 1, 0, -1):
                                if font.getlength(rem[:i] + "-") <= LYRICS_WIDTH:
                                    out.append(rem[:i] + "-")
                                    rem, found = rem[i:], True
                                    break
                            if not found:
                                out.append(rem[0])
                                rem = rem[1:]
                if cur: out.append(cur)
                if len(out) > 7: out = out[:7]
                
                total_height = len(out) * 6
                y_start = 14 + (48 - total_height) // 2
                
                for i, line in enumerate(out):
                    w = font.getlength(line)
                    x = 2 + (LYRICS_WIDTH - w) // 2
                    draw.text((x, y_start + i * 6), line, fill=(255, 255, 255), font=font)

        draw.rectangle((55, 0, 63, 12), fill=(0, 0, 0))
        state = "Paused" if not response.is_playing else ("Play" if show_play else "Active")
        components.play_indicator.draw(draw, state)

        return img
