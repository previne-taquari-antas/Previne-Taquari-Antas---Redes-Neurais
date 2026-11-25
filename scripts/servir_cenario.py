#!/usr/bin/env python3
"""Servidor opcional de arquivos e acesso restrito aos tiles Copernicus (mesma origem).
Sem dependências externas: python scripts/servir_cenario.py --port 8000
Não recebe URLs arbitrárias, não grava arquivos e não cadastra dados municipais.
"""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ROOT = Path(__file__).resolve().parents[1]
TILE = re.compile(r'^Copernicus_DSM_COG_10_([NS])(\d{2})_00_([EW])(\d{3})_00_DEM$')


def tile_url(name):
    match = TILE.fullmatch(name)
    if not match or int(match[2]) > 90 or int(match[4]) > 180:
        raise ValueError('Tile Copernicus inválido')
    return f'https://copernicus-dem-30m.s3.amazonaws.com/{name}/{name}.tif'


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed = urlsplit(self.path)
        if parsed.path != '/api/copernicus':
            return super().do_GET()
        try:
            url = tile_url(parse_qs(parsed.query).get('tile', [''])[0])
            headers = {}
            if self.headers.get('Range'):
                value = self.headers['Range']
                if not re.fullmatch(r'bytes=\d+-\d*', value):
                    raise ValueError('Use uma única faixa de bytes')
                headers['Range'] = value
            with urlopen(Request(url, headers=headers), timeout=45) as response:
                length = int(response.headers.get('Content-Length', 0))
                if length > 150 * 1024 * 1024:
                    raise ValueError('Tile maior que 150 MB')
                self.send_response(response.status)
                for key in ('Content-Type', 'Content-Length', 'Content-Range', 'Accept-Ranges'):
                    if response.headers.get(key):
                        self.send_header(key, response.headers[key])
                self.send_header('Cache-Control', 'public, max-age=86400')
                self.end_headers()
                total = 0
                while chunk := response.read(65536):
                    total += len(chunk)
                    if total > 150 * 1024 * 1024:
                        break
                    self.wfile.write(chunk)
        except ValueError as error:
            self.send_error(400, str(error))
        except (HTTPError, URLError, TimeoutError):
            self.send_error(502, 'Fonte Copernicus indisponível')
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8000)
    parser.add_argument('--bind', default='127.0.0.1')
    args = parser.parse_args()
    print(f'Abra http://{args.bind}:{args.port}/cenario_municipal.html', flush=True)
    ThreadingHTTPServer((args.bind, args.port), Handler).serve_forever()
