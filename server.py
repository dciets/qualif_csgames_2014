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

def extract_metadata(msg):
    metadata = {}
    content = msg
    if msg[0] == "[" and msg.find("]") != -1:
        content = msg[msg.find("]") + 1:].strip()
        metadata_str = msg[1:msg.find("]")]
        metadata = {s[0].strip()[1:]:s[1].strip() for s in [i.split("=") for i in metadata_str.split(",")]}

    return (metadata, content)

class ChatServer(object):
    __metaclass__ = Singleton

    clients = dict()

    def register(self, client):
        if client.username in self.clients or client.username == "server":
            self.send_error("Username %s is already taken" % client.username, client)
            return False

        self.clients[client.username] = client

        print "Client '%s' connecting (%d client registered)" % (client.username, len(self.clients))
        return True

    def unregister(self, client):
        del self.clients[client.username]

        print "Client '%s' disconnecting (%d client registered)" % (client.username, len(self.clients))

    def send_all(self, msg, src, metadata={}):
        for client in self.clients.values():
            if not client is src:
                self.send(msg, client, src)

    def send_to(self, msg, dst, src, metadata={}):
        self.send(msg, self.clients[dst], src)

    def send_error(self, error, dst):
        self.send(error, dst, None, {"type": "error"})

    def send(self, msg, dst, src=None, metadata={}):
        try:
            metadata["src"] = src.username if src else "server"
            metadata_stamp = "[" + ",".join(map(lambda p: "@%s=%s" % p, metadata.iteritems())) + "] "
            dst.request.sendall(metadata_stamp + msg)
        except:
            print traceback.format_exc()
            self.unregister(dst)

    def handle_msg(self, msg, src):
        if not msg:
            return

        metadata, content = extract_metadata(msg)
        if "dst" not in metadata:
            self.send_all(content, src, metadata)
        elif metadata["dst"] != "server":
            self.send_to(content, metadata["dst"], src, metadata)
        else:
            self.handle_command(content, src)

    def handle_command(self, cmd, src):
        if cmd == "list":
            self.send("\n".join(self.clients.keys()), src, metadata={"type":"user_list"})
        else:
            self.send_error("Unknown command: %s" % cmd, src)

class ClientHandler(SocketServer.BaseRequestHandler):
    def setup(self):
        self.server = ChatServer()

    def handle(self):
        self.username = self.request.recv(32).strip()
        if not (self.username and self.server.register(self)):
            return

        try:
            while True:
                msg = self.request.recv(1024)
                if not msg:
                    break

                self.server.handle_msg(msg.strip(), self)
        except:
            print traceback.format_exc()

        self.server.unregister(self)


class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass


if __name__ == "__main__":
    HOST, PORT = "0.0.0.0", 31337
    server = ThreadedTCPServer((HOST, PORT), ClientHandler)
    server.serve_forever()