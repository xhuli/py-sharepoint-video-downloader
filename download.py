#!/usr/bin/env python3
# ./download.py
import argparse
import os
import shutil
import sys
import yt_dlp
from pathlib import Path
from urllib.parse import urlparse
from yt_dlp.utils import DownloadError

# English/Spanish install hint used in user-facing messages.
# Pista de instalacion en ingles/espanol usada en mensajes visibles.
FFMPEG_INSTALL_HINT = "sudo apt install ffmpeg"

# User-facing strings in English and Spanish.
# Cadenas visibles para el usuario en ingles y espanol.
MESSAGES = {
    'en': {
        'arg_description': 'Download Teams/Stream recordings',
        'error_prefix': 'Error',
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
    },
    'es': {
        'arg_description': 'Descarga grabaciones Teams/Stream',
        'error_prefix': 'Error',
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


def shorten_url(url: str) -> str:
    key = 'index&format=dash'
    idx = url.find(key)
    if idx == -1:
        raise ValueError(msg('missing_marker'))
    return url[:idx + len(key)]


def build_downloader_opts(fast: bool):
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
def format_download_error(exc: DownloadError) -> str:
    message = str(exc)
    if 'ffmpeg is not installed' in message:
        return msg('ffmpeg_download_error', install_hint=FFMPEG_INSTALL_HINT)
    return message


def download_with_yt_dlp(url: str, output: str, opts: dict):
    opts = opts | {'outtmpl': output}
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([url])


def main() -> int:
    parser = argparse.ArgumentParser(description=msg('arg_description'))
    parser.add_argument('manifest_file')
    parser.add_argument('-o', '--output', default='output.mp4')
    parser.add_argument('--no-fast', action='store_true')
    args = parser.parse_args()

    try:
        raw_url = read_manifest_url(args.manifest_file)
        short_url = shorten_url(raw_url)

        # Only enable fast mode for *.svc.ms hosts.
        # Solo activamos el modo rapido para hosts *.svc.ms.
        host = urlparse(short_url).hostname or ''
        fast_mode = (not args.no_fast) and host.endswith('svc.ms')

        opts = build_downloader_opts(fast_mode)
        ensure_ffmpeg(opts)

        print(msg('downloading_from', url=short_url))
        download_with_yt_dlp(short_url, args.output, opts)
        print(msg('download_complete', output=args.output))
        return 0
    except FileNotFoundError as exc:
        return fail(str(exc))
    except ValueError as exc:
        return fail(str(exc))
    except RuntimeError as exc:
        return fail(str(exc))
    except DownloadError as exc:
        return fail(format_download_error(exc))
    except KeyboardInterrupt:
        return fail(msg('download_cancelled'), exit_code=130)


if __name__ == '__main__':
    sys.exit(main())
