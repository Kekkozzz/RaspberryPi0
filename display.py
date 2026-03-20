import threading
import time
import textwrap
import logging

logger = logging.getLogger("raspy.display")

try:
    import board
    import busio
    import adafruit_ssd1306
    from PIL import Image, ImageDraw, ImageFont
    _LIBS_AVAILABLE = True
except ImportError:
    _LIBS_AVAILABLE = False


class RaspyDisplay:
    W, H = 128, 64

    TICKS_PER_PAGINA = 10  # 10 × 0.3s = 3 secondi per pagina

    def __init__(self, nome="Raspy"):
        self.nome = nome
        self._stato = "CARICAMENTO"
        self._testo = ""
        self._dots = 0
        self._pagine = []
        self._pagina_corrente = 0
        self._ticks_pagina = 0
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self.oled = None

        if not _LIBS_AVAILABLE:
            logger.warning("Librerie OLED non disponibili, display disabilitato")
            return

        try:
            i2c = busio.I2C(board.SCL, board.SDA)
            self.oled = adafruit_ssd1306.SSD1306_I2C(self.W, self.H, i2c)
            self.oled.fill(0)
            self.oled.show()
        except Exception as e:
            logger.warning(f"Display OLED non disponibile: {e}")
            return

        try:
            self._font_sm = ImageFont.load_default(size=10)
            self._font_md = ImageFont.load_default(size=14)
        except TypeError:
            self._font_sm = ImageFont.load_default()
            self._font_md = self._font_sm

    @property
    def available(self):
        return self.oled is not None

    def set_stato(self, stato, testo=""):
        with self._lock:
            self._stato = stato
            self._testo = testo
            if stato in ("RISPOSTA", "HAI_DETTO"):
                righe = textwrap.wrap(testo, width=21)
                self._pagine = [righe[i:i+3] for i in range(0, max(len(righe), 1), 3)]
                self._pagina_corrente = 0
                self._ticks_pagina = 0

    def start(self):
        if not self.available:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _loop(self):
        while self._running:
            try:
                self._dots = (self._dots + 1) % 4
                if self._stato in ("RISPOSTA", "HAI_DETTO"):
                    self._ticks_pagina += 1
                    if self._ticks_pagina >= self.TICKS_PER_PAGINA:
                        self._ticks_pagina = 0
                        if self._pagina_corrente < len(self._pagine) - 1:
                            self._pagina_corrente += 1
                img = Image.new("1", (self.W, self.H))
                draw = ImageDraw.Draw(img)
                with self._lock:
                    stato = self._stato
                    testo = self._testo
                self._render(draw, stato, testo)
                self.oled.image(img)
                self.oled.show()
            except Exception as e:
                logger.error(f"Errore display: {e}")
            time.sleep(0.3)

    def _draw_indicatore_pagina(self, draw):
        n = len(self._pagine)
        if n <= 1:
            return
        dot_w = 6
        total = n * dot_w
        start_x = (self.W - total) // 2
        for i in range(n):
            x = start_x + i * dot_w + 1
            if i == self._pagina_corrente:
                draw.rectangle([(x, 60), (x + 3, 63)], fill=255)
            else:
                draw.rectangle([(x, 60), (x + 3, 63)], outline=255)

    def _header(self, draw, titolo=None):
        draw.text((0, 0), titolo or self.nome, font=self._font_md, fill=255)
        draw.line([(0, 16), (self.W, 16)], fill=255)

    def _render(self, draw, stato, testo):
        if stato == "CARICAMENTO":
            self._header(draw)
            dots = "." * self._dots
            draw.text((5, 22), f"Caricamento{dots}", font=self._font_sm, fill=255)

        elif stato == "ASCOLTO":
            self._header(draw)
            draw.text((10, 22), "In ascolto...", font=self._font_sm, fill=255)
            draw.text((5, 38), f"Di' \"{self.nome}\"", font=self._font_sm, fill=255)
            draw.text((30, 52), time.strftime("%H:%M"), font=self._font_sm, fill=255)

        elif stato == "WAKE":
            self._header(draw, "  Wake word!")
            draw.text((20, 22), "Rilevata!", font=self._font_md, fill=255)
            draw.text((15, 42), "Parla ora...", font=self._font_sm, fill=255)

        elif stato == "REGISTRAZIONE":
            self._header(draw, "  Registra")
            draw.text((5, 22), "Parla...", font=self._font_sm, fill=255)
            # Barra animata
            bar_w = int((self._dots + 1) * 25)
            draw.rectangle([(5, 36), (123, 48)], outline=255)
            if bar_w > 0:
                draw.rectangle([(5, 36), (5 + bar_w, 48)], fill=255)

        elif stato == "TRASCRIZIONE":
            self._header(draw)
            dots = "." * self._dots
            draw.text((5, 22), f"Trascrivo{dots}", font=self._font_sm, fill=255)

        elif stato == "PENSANDO":
            self._header(draw)
            dots = "." * self._dots
            draw.text((5, 22), f"Sto pensando{dots}", font=self._font_sm, fill=255)

        elif stato == "HAI_DETTO":
            self._header(draw, "  Hai detto:")
            righe = self._pagine[self._pagina_corrente] if self._pagine else []
            for i, riga in enumerate(righe):
                draw.text((2, 20 + i * 14), riga, font=self._font_sm, fill=255)
            self._draw_indicatore_pagina(draw)

        elif stato == "RISPOSTA":
            self._header(draw)
            righe = self._pagine[self._pagina_corrente] if self._pagine else []
            for i, riga in enumerate(righe):
                draw.text((2, 20 + i * 14), riga, font=self._font_sm, fill=255)
            self._draw_indicatore_pagina(draw)

        elif stato == "SPENTA":
            draw.text((15, 20), "Arrivederci!", font=self._font_md, fill=255)
            draw.text((35, 42), ":)", font=self._font_md, fill=255)

    def cleanup(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1)
        if self.available:
            try:
                self.oled.fill(0)
                self.oled.show()
            except Exception:
                pass
