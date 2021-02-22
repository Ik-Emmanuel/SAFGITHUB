import json
import socketserver
import threading
from uuid import uuid4


class EngineRequestsChannel:
    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            with self.request.makefile() as reader:
                with self.request.makefile('w') as writer:
                    try:
                        request = json.loads(reader.readline())
                        request_secret = request.get('host_secret')
                        if request_secret is None or request_secret != self.server.host_secret:
                            writer.write(json.dumps({'result': 'error', 'error': 'Unauthorized'}))
                        else:
                            operation = request['operation']
                            callback = self.server.handlers.get(operation)
                            if callback is None:
                                writer.write(json.dumps({'result': 'error', 'error': 'InvalidOperation'}))
                            else:
                                    callback(request, writer, self.request)
                    except Exception as e:
                        writer.write(json.dumps({'result': 'error', 'error': repr(e)}) + '\n')

    def __init__(self):
        self._handlers = {}
        self._server = socketserver.ThreadingTCPServer(("localhost", 0), EngineRequestsChannel.Handler, False)
        self._server.daemon_threads = True
        # This is the number of requests we can queue up before rejecting connections. Given the engine
        # will be making a request per concurrent partition, 256 gives us enough headroom to handle
        # machines with up to 256 cores.
        self._server.request_queue_size = 256
        self._server.server_bind()
        self._server.server_activate()
        self._server.handlers = self._handlers
        self._server.host_secret = str(uuid4())
        self._server_thread = threading.Thread(target=self._server.serve_forever)
        self._server_thread.daemon = True
        self._server_thread.start()

    @property
    def port(self):
        return self._server.server_address[1]

    @property
    def host_secret(self):
        return self._server.host_secret

    def register_handler(self, message: str, callback):
        self._handlers[message] = callback

    def has_handler(self, message: str) -> bool:
        return message in self._handlers
