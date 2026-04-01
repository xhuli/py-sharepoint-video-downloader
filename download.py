#!/usr/bin/env python3
# ./download.py
import argparse
import os
import shutil
import sys
import yt_dlp
from pathlib import Path
from urllib.parse import parse_qsl
from urllib.parse import urlencode
from urllib.parse import urlparse
from urllib.parse import urlunparse
from yt_dlp.utils import DownloadError

# English/Spanish install hint used in user-facing messages.
# Pista de instalacion en ingles/espanol usada en mensajes visibles.
FFMPEG_INSTALL_HINT = 'sudo apt install ffmpeg'

# User-facing strings in English and Spanish.
# Cadenas visibles para el usuario en ingles y espanol.
MESSAGES = {
    'en': {
        'arg_description': 'Download Teams/Stream recordings',
        'error_prefix': 'Error',
        'warning_prefix': 'Warning',
        'missing_marker': "Could not find 'index&format=dash' in the URL.",
        'manifest_missing': 'Manifest file does not exist: {manifest_file}',
        'manifest_empty': 'Manifest file is empty: {manifest_file}',
        'ffmpeg_required': (
            'ffmpeg is required to merge audio and video, but it is not installed '
            'or not available on PATH. On Ubuntu install it with: {install_hint}'
        ),
        'ffmpeg_download_error': (
            'yt-dlp requires ffmpeg to merge audio and video. '
            'On Ubuntu install it with: {install_hint}'
        ),
        'downloading_from': 'Downloading from: {url}',
        'download_complete': 'Download complete: {output}',
        'download_cancelled': 'Download cancelled by user.',
        'retry_shortened': 'Full manifest failed, retrying with shortened manifest URL.',
        'no_tempauth_warning': (
            'Manifest URL does not contain tempauth. This capture may only work inside the '
            'browser session and may require browser cookies.'
        ),
        'unauthorized_no_tempauth': (
            'Manifest unauthorized (HTTP 401). This capture does not include a portable auth '
            'token (tempauth) and may only work inside the browser session. Refresh the video '
            'page, recapture the request, and prefer a videomanifest whose docid contains '
            'tempauth. You can also try --cookies or --cookies-from-browser.'
        ),
        'unauthorized_with_tempauth': (
            'Manifest unauthorized (HTTP 401). The capture may be expired or tied to a '
            'different browser session. Refresh the video page, recapture the manifest, and '
            'retry right away. You can also try --cookies or --cookies-from-browser.'
        ),
        'cookies_from_browser_help': (
            'Browser to read cookies from, for example chromium, chrome, or '
            'chromium:/path/to/profile'
        ),
        'cookies_file_help': 'Read cookies from a Netscape cookies.txt file',
        'user_agent_help': 'Override the User-Agent sent to yt-dlp requests',
        'no_shorten_fallback_help': 'Disable fallback retry with a shortened manifest URL',
    },
    'es': {
        'arg_description': 'Descarga grabaciones Teams/Stream',
        'error_prefix': 'Error',
        'warning_prefix': 'Aviso',
        'missing_marker': "No se encontro 'index&format=dash' en la URL.",
        'manifest_missing': 'No existe el archivo de manifiesto: {manifest_file}',
        'manifest_empty': 'El archivo de manifiesto esta vacio: {manifest_file}',
        'ffmpeg_required': (
            'ffmpeg es obligatorio para unir audio y video, pero no esta instalado '
            'o no esta en PATH. En Ubuntu instalalo con: {install_hint}'
        ),
        'ffmpeg_download_error': (
            'yt-dlp necesita ffmpeg para unir audio y video. '
            'En Ubuntu instalalo con: {install_hint}'
        ),
        'downloading_from': 'Descargando desde: {url}',
        'download_complete': 'Descarga completada: {output}',
        'download_cancelled': 'Descarga cancelada por el usuario.',
        'retry_shortened': 'La URL completa del manifiesto fallo; reintentando con la URL recortada.',
        'no_tempauth_warning': (
            'La URL del manifiesto no contiene tempauth. Esta captura puede funcionar solo '
            'dentro de la sesion del navegador y puede requerir cookies del navegador.'
        ),
        'unauthorized_no_tempauth': (
            'Manifiesto no autorizado (HTTP 401). Esta captura no incluye un token de '
            'autenticacion portable (tempauth) y puede funcionar solo dentro de la sesion '
            'del navegador. Recarga la pagina del video, vuelve a capturar la peticion y '
            'prioriza un videomanifest cuyo docid contenga tempauth. Tambien puedes probar '
            'con --cookies o --cookies-from-browser.'
        ),
        'unauthorized_with_tempauth': (
            'Manifiesto no autorizado (HTTP 401). La captura puede estar vencida o ligada a '
            'otra sesion del navegador. Recarga la pagina del video, vuelve a capturar el '
            'manifiesto y reintenta enseguida. Tambien puedes probar con --cookies o '
            '--cookies-from-browser.'
        ),
        'cookies_from_browser_help': (
            'Navegador del que se leeran cookies, por ejemplo chromium, chrome o '
            'chromium:/ruta/al/perfil'
        ),
        'cookies_file_help': 'Lee cookies desde un archivo cookies.txt en formato Netscape',
        'user_agent_help': 'Sobrescribe el User-Agent enviado en las peticiones de yt-dlp',
        'no_shorten_fallback_help': 'Desactiva el reintento con una URL de manifiesto recortada',
    },
}


def get_language() -> str:
    """Return the preferred UI language based on terminal locale.

    Devuelve el idioma preferido de la interfaz segun la configuracion regional de la terminal.
    """
    locale_value = (
            os.environ.get('LC_ALL')
            or os.environ.get('LC_MESSAGES')
            or os.environ.get('LANG')
            or ''
    ).lower()

    if locale_value.startswith('es'):
        return 'es'

    return 'en'


# Cache the resolved language once for the process.
# Guardamos el idioma resuelto una sola vez para el proceso.
LANGUAGE = get_language()


def msg(key: str, **kwargs) -> str:
    """Resolve a localized message.

    Resuelve un mensaje localizado.
    """
    template = MESSAGES.get(LANGUAGE, MESSAGES['en'])[key]
    return template.format(**kwargs)


def fail(message: str, exit_code: int = 1) -> int:
    print(f"{msg('error_prefix')}: {message}", file=sys.stderr)
    return exit_code


def warn(message: str):
    print(f"{msg('warning_prefix')}: {message}", file=sys.stderr)


# Shorten the URL only when a legacy manifest capture needs it.
# Recorta la URL solo cuando una captura de manifiesto antigua lo necesita.
def shorten_url(url: str) -> str:
    key = 'index&format=dash'
    idx = url.find(key)
    if idx == -1:
        raise ValueError(msg('missing_marker'))
    return url[:idx + len(key)]


# Detect whether the manifest carries a portable temp auth token.
# Detecta si el manifiesto lleva un token temporal portable de autenticacion.
def has_tempauth(url: str) -> bool:
    return 'tempauth=' in url.lower()


# Build a redacted URL for logs to avoid leaking long auth tokens.
# Construye una URL redactada para logs y evita exponer tokens largos.
def safe_url_for_log(url: str) -> str:
    parsed = urlparse(url)
    keep_keys = {'provider', 'inputFormat', 'action', 'part', 'format', 'providerflags'}
    filtered_items = [(k, v) for k, v in parse_qsl(parsed.query, keep_blank_values=True) if k in keep_keys]
    query = urlencode(filtered_items)
    suffix = f' [tempauth={"yes" if has_tempauth(url) else "no"}]'
    safe_path = parsed.path or '/'
    return urlunparse((parsed.scheme, parsed.netloc, safe_path, '', query, '')) + suffix


# Keep the original manifest first and only use shortened fallback when needed.
# Conserva primero el manifiesto original y usa el recorte solo como reintento.
def build_candidate_urls(raw_url: str, allow_shorten_fallback: bool) -> list[str]:
    candidates = [raw_url]
    if not allow_shorten_fallback:
        return candidates

    try:
        shortened_url = shorten_url(raw_url)
    except ValueError:
        return candidates

    if shortened_url != raw_url:
        candidates.append(shortened_url)

    return candidates


# Support cookies and browser cookies directly through yt-dlp options.
# Soporta cookies y cookies del navegador directamente mediante opciones de yt-dlp.
def build_downloader_opts(
        fast: bool,
        cookies_file: str | None,
        cookies_from_browser: str | None,
        user_agent: str | None,
):
    opts = {
        'format': 'vcopy+audcopy/best',
        'merge_output_format': 'mp4',
        'ignoreerrors': False,
        'retries': 20,
        'fragment_retries': 20,
        'retry_sleep_functions': {'fragment': lambda n: min(2 ** n, 10)},
        'nopart': True,
        # Fragment-level timeouts to avoid hanging requests.
        # Timeouts por fragmento para evitar descargas colgadas.
        'socket_timeout': 30,
    }

    if cookies_file:
        opts['cookiefile'] = cookies_file

    if cookies_from_browser:
        opts['cookiesfrombrowser'] = cookies_from_browser

    if user_agent:
        opts['http_headers'] = {'User-Agent': user_agent}

    if not fast:
        return opts

    opts['concurrent_fragments'] = 4
    opts['prefer_insecure'] = False
    opts['enable_file_urls'] = False
    opts['http_client'] = 'curl_cffi'
    opts['verbose'] = True

    return opts


# ffmpeg is required whenever yt-dlp must merge separate streams.
# ffmpeg es obligatorio cuando yt-dlp debe unir streams separados.
def requires_ffmpeg(opts: dict) -> bool:
    fmt = str(opts.get('format', ''))
    return '+' in fmt or bool(opts.get('merge_output_format'))


# Fail early when ffmpeg is missing.
# Falla antes cuando falta ffmpeg.
def ensure_ffmpeg(opts: dict):
    if not requires_ffmpeg(opts):
        return

    if shutil.which('ffmpeg') is None:
        raise RuntimeError(msg('ffmpeg_required', install_hint=FFMPEG_INSTALL_HINT))


# Read the manifest URL from a plain text file.
# Lee la URL del manifiesto desde un archivo de texto plano.
def read_manifest_url(manifest_file: str) -> str:
    manifest_path = Path(manifest_file)
    if not manifest_path.is_file():
        raise FileNotFoundError(msg('manifest_missing', manifest_file=manifest_file))

    raw_url = manifest_path.read_text(encoding='utf-8').strip()
    if not raw_url:
        raise ValueError(msg('manifest_empty', manifest_file=manifest_file))

    return raw_url


# Convert noisy yt-dlp exceptions into clearer guidance.
# Convierte excepciones ruidosas de yt-dlp en mensajes mas claros.
def format_download_error(exc: DownloadError, url: str) -> str:
    message = str(exc)
    lowered = message.lower()
    if 'ffmpeg is not installed' in lowered:
        return msg('ffmpeg_download_error', install_hint=FFMPEG_INSTALL_HINT)
    if '401' in lowered or 'unauthorized' in lowered:
        if has_tempauth(url):
            return msg('unauthorized_with_tempauth')
        return msg('unauthorized_no_tempauth')
    return message


# Try each manifest variant until one succeeds.
# Prueba cada variante del manifiesto hasta que una funcione.
def download_with_yt_dlp(urls: list[str], output: str, opts: dict):
    last_error = None
    for index, url in enumerate(urls):
        if index == 1:
            warn(msg('retry_shortened'))

        print(msg('downloading_from', url=safe_url_for_log(url)))
        attempt_opts = opts | {'outtmpl': output}
        try:
            with yt_dlp.YoutubeDL(attempt_opts) as ydl:
                ydl.download([url])
            return url
        except DownloadError as exc:
            last_error = (exc, url)
            if index + 1 < len(urls):
                continue
            raise

    if last_error is not None:
        raise last_error[0]


# Decide whether the fast mode should be enabled for this host.
# Decide si el modo rapido debe activarse para este host.
def is_fast_mode_enabled(url: str, no_fast: bool) -> bool:
    host = urlparse(url).hostname or ''
    return (not no_fast) and host.endswith('svc.ms')


def main() -> int:
    parser = argparse.ArgumentParser(description=msg('arg_description'))
    parser.add_argument('manifest_file')
    parser.add_argument('-o', '--output', default='output.mp4')
    parser.add_argument('--no-fast', action='store_true')
    parser.add_argument('--cookies', help=msg('cookies_file_help'))
    parser.add_argument('--cookies-from-browser', help=msg('cookies_from_browser_help'))
    parser.add_argument('--user-agent', help=msg('user_agent_help'))
    parser.add_argument('--no-shorten-fallback', action='store_true', help=msg('no_shorten_fallback_help'))
    args = parser.parse_args()

    try:
        raw_url = read_manifest_url(args.manifest_file)
        candidate_urls = build_candidate_urls(raw_url, allow_shorten_fallback=not args.no_shorten_fallback)

        if not has_tempauth(raw_url):
            warn(msg('no_tempauth_warning'))

        opts = build_downloader_opts(
            fast=is_fast_mode_enabled(candidate_urls[0], args.no_fast),
            cookies_file=args.cookies,
            cookies_from_browser=args.cookies_from_browser,
            user_agent=args.user_agent,
        )
        ensure_ffmpeg(opts)

        used_url = download_with_yt_dlp(candidate_urls, args.output, opts)
        print(msg('download_complete', output=args.output))

        if used_url != raw_url and not has_tempauth(raw_url):
            warn(msg('no_tempauth_warning'))
        return 0
    except FileNotFoundError as exc:
        return fail(str(exc))
    except ValueError as exc:
        return fail(str(exc))
    except RuntimeError as exc:
        return fail(str(exc))
    except DownloadError as exc:
        failed_url = candidate_urls[-1] if 'candidate_urls' in locals() else ''
        return fail(format_download_error(exc, failed_url))
    except KeyboardInterrupt:
        return fail(msg('download_cancelled'), exit_code=130)


if __name__ == '__main__':
    sys.exit(main())
