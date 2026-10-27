"""WSGI entry point, so the same server can run on Azure App Service.

The dashboard is a stdlib HTTP server and its routing lives in server.py. The
App Service Python runtime speaks WSGI, so this module drives that same
handler: it builds the handler's state from the environ, lets the handler write
a normal HTTP response into a buffer, and turns that buffer into the WSGI
triple. No route is defined twice.
"""
import email.message
import io
import json
import os
import types

from server import ROOT, Handler, MAX_REQUEST_BYTES


class _BufferedWriter:
    """The sink the handler writes its response into."""

    def __init__(self):
        self.buffer = bytearray()

    def write(self, data):
        self.buffer.extend(data)
        return len(data)

    def flush(self):
        pass


class _RequestHandler(Handler):
    """The dashboard handler, driven by a request instead of a socket."""

    def __init__(self, method, target, headers, body, writer):
        self.command = method
        self.path = target
        self.headers = headers
        self.rfile = io.BytesIO(body)
        self.wfile = writer
        self.client_address = ('127.0.0.1', 0)
        # The handler reads the port from the server object when it decides
        # whether a request is same-origin.
        self.server = types.SimpleNamespace(server_port=_port_of(headers.get('Host', '')))
        self.request = None
        self.close_connection = True
        self.protocol_version = 'HTTP/1.1'
        self.request_version = 'HTTP/1.1'
        self.requestline = f'{method} {target} HTTP/1.1'
        self.command = method
        # SimpleHTTPRequestHandler takes the document root as a constructor
        # argument; without the socket there is no constructor call.
        self.directory = str(ROOT)

    def log_message(self, *args):
        pass

    def log_error(self, *args):
        pass


def _port_of(host):
    _, _, port = host.rpartition(':')
    return int(port) if port.isdigit() else 80


def _headers_from(environ):
    headers = email.message.Message()
    for key, value in environ.items():
        if key.startswith('HTTP_'):
            headers[key[5:].replace('_', '-').title()] = value
    if environ.get('CONTENT_TYPE'):
        headers['Content-Type'] = environ['CONTENT_TYPE']
    if environ.get('CONTENT_LENGTH'):
        headers['Content-Length'] = environ['CONTENT_LENGTH']
    return headers


def application(environ, start_response):
    method = environ.get('REQUEST_METHOD', 'GET').upper()
    path = environ.get('PATH_INFO', '/') or '/'
    query = environ.get('QUERY_STRING', '')
    target = path + ('?' + query if query else '')
    try:
        length = int(environ.get('CONTENT_LENGTH') or 0)
    except ValueError:
        length = 0
    # Bound the body before WSGI buffers it; Azure/public video intake stays off.
    local_video = path == '/api/video-review/upload' and environ.get('HTTP_HOST','').split(':')[0] in ('127.0.0.1','localhost') and not os.getenv('WEBSITE_INSTANCE_ID') and not os.getenv('WEBSITE_HOSTNAME')
    maximum = 64*1024*1024 if local_video else MAX_REQUEST_BYTES
    if length < 0 or length > maximum:
        payload = b'{"error":"Request body too large"}'
        start_response('413 Payload Too Large',[('Content-Type','application/json'),('Content-Length',str(len(payload)))])
        return [payload]
    body = environ['wsgi.input'].read(length) if length else b''
    writer = _BufferedWriter()
    handler = _RequestHandler(method, target, _headers_from(environ), body, writer)
    try:
        if method == 'GET':
            handler.do_GET()
        elif method == 'POST':
            handler.do_POST()
        elif method == 'HEAD':
            handler.do_HEAD()
        else:
            handler.send_error(405, 'Method not allowed')
    except Exception:
        payload = json.dumps({'error': 'Unable to process the request.'}).encode()
        start_response('500 Internal Server Error',
                       [('Content-Type', 'application/json'), ('Content-Length', str(len(payload)))])
        return [payload]
    raw = bytes(writer.buffer)
    head, _, payload = raw.partition(b'\r\n\r\n')
    lines = head.split(b'\r\n')
    # The handler writes a full HTTP status line; WSGI wants "code message".
    parts = lines[0].decode('latin-1').split(' ', 2) if lines else []
    status = ' '.join(parts[1:]).strip() if len(parts) > 1 else '200 OK'
    # Hop-by-hop headers belong to one connection, not to the WSGI response.
    hop_by_hop = {'connection', 'keep-alive', 'transfer-encoding', 'upgrade'}
    out = []
    for line in lines[1:]:
        name, _, value = line.decode('latin-1').partition(':')
        name = name.strip()
        if name.lower() in hop_by_hop:
            continue
        out.append((name, value.strip()))
    out = [(name, value) for name, value in out if name.lower() != 'content-length']
    out.append(('Content-Length', str(len(payload))))
    start_response(status, out)
    return [payload]

