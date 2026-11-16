# CriptoNivel / CryptoLevel — sitio de utilidades cripto (prototipo)

Sitio estático ES/EN que responde preguntas simples sobre 10 criptomonedas, actualizado cada día:
¿está sobre su media de 200 días?, momentum de 30 días, distancia al máximo, percentil de 1 año, volatilidad,
volumen; más una calculadora "¿cuánto valdría hoy?" (una vez o DCA, en USD o CLP).

- `python build.py` descarga datos (Binance, dólar observado de mindicador.cl; cache incremental en `cache/`)
  y genera `site/` (24 páginas + datos JSON para la calculadora + sitemap + robots).
- `python build.py --offline` regenera sin descargar.
- Ver en local: `cd site && python -m http.server 8765` → http://localhost:8765
- Textos en `i18n.py` (agregar idioma = agregar diccionario); monedas en `coins.py`.
- Publicación: `.github/workflows/build.yml` construye cada día y publica en GitHub Pages.
  Falta: dominio (`BASE_URL` en build.py), activar Pages, y reemplazar los `ad-slot` por la red de anuncios.

Información educativa, no recomendación de inversión.
