import socket
import threading
import SocketServer

class Singleton(type):
    _instances = {}
    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
        return cls._instances[cls]


class ChatServer(object):
    __metaclass__ = Singleton

    clients = dict()

    def register(self, username, client):
        self.clients[username] = client

    def unregister(self, username):
        del self.clients[username]

    def send_all(self, msg):
        for client in self.client:
            self.clients.sendall(msg)

    def send_to(self, msg, dst):
        self.clients[dst].sendall(msg)


class ClientHandler(SocketServer.BaseRequestHandler):
    def setup(self):
        self.server = ChatServer()

    def handle(self):
        self.username = self.request.recv(1024)
        self.server.register(self.username, self.request)

        try:
            while True:
                msg = self.request.recv(1024)
                self.server.send_all(msg)
        except:
            self.server.unregister(self.username)

class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass


if __name__ == "__main__":
    HOST, PORT = "0.0.0.0", 31337
    server = ThreadedTCPServer((HOST, PORT), ClientHandler)
    server.serve_forever()

    server_thread = threading.Thread(target=server.serve_forever)
    server_thread.daemon = True
    server_thread.start()