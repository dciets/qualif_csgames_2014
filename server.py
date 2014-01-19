import socket
import threading
import SocketServer
import traceback

class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class ChatServer(object):
    __metaclass__ = Singleton

    clients = dict()

    def register(self, client):
        if client.username in self.clients:
            self.send("Username %s is already taken" % client.username, client, None, {"type": "error"})
            return False

        self.clients[client.username] = client

        print "Client '%s' connecting (%d client registered)" % (client.username, len(self.clients))
        return True

    def unregister(self, client):
        del self.clients[client.username]

        print "Client '%s' disconnecting (%d client registered)" % (client.username, len(self.clients))

    def send_all(self, msg, src):
        for client in self.clients.values():
            if not client is src:
                self.send(msg, client, src)

    def send_to(self, msg, dst, src):
        self.send(msg, self.clients[dst], src)

    def send(self, msg, dst, src, metadata={}):
        try:
            metadata["src"] = src.username if src else "server"
            metadata_stamp = "[" + ",".join(map(lambda p: "@%s=%s" % p, metadata.iteritems())) + "] "
            dst.request.sendall(metadata_stamp + msg)
        except:
            print traceback.format_exc()
            self.unregister(dst)

    def handle_command(self, msg, src):
        pass


class ClientHandler(SocketServer.BaseRequestHandler):
    def setup(self):
        self.server = ChatServer()

    def handle(self):
        self.username = self.request.recv(32).strip()
        if not (self.username and self.server.register(self)):
            return

        try:
            while True:
                msg = self.request.recv(1024).strip()
                if not msg:
                    break
                self.server.send_all(msg, self)
        except:
            print traceback.format_exc()

        self.server.unregister(self)


class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass


if __name__ == "__main__":
    HOST, PORT = "0.0.0.0", 31337
    server = ThreadedTCPServer((HOST, PORT), ClientHandler)
    server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.serve_forever()