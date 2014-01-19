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
        self.clients[client.username] = client

        print "Client '%s' connecting (%d client registered)" % (client.username, len(self.clients))

    def unregister(self, client):
        del self.clients[client.username]

        print "Client '%s' disconnecting (%d client registered)" % (client.username, len(self.clients))

    def send_all(self, msg, src):
        for client in self.clients.values():
            if not client is src:
                self.send(msg, client)

    def send_to(self, msg, dst):
        self.send(msg, self.clients[dst])

    def send(self, msg, dst):
        try:
            dst.request.sendall(msg)
        except:
            self.unregister(dst)


class ClientHandler(SocketServer.BaseRequestHandler):
    def setup(self):
        self.server = ChatServer()

    def handle(self):
        self.username = self.request.recv(1024).strip()
        if self.username == None:
            return

        self.server.register(self)

        try:
            while True:
                msg = self.request.recv(1024).strip()
                if msg == None:
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
    server.serve_forever()

    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()