#!/usr/bin/env python2

import sqlite3
import socket
import threading
import SocketServer
import traceback
import uuid

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
        metadata = {s[0].strip():s[1].strip() for s in [i.split("=") for i in metadata_str.split(",")]}

    return (metadata, content)

def extract_credential(msg):
    return map(str.strip, msg.split(' ')[1:])

class ChatServer(object):
    __metaclass__ = Singleton

    clients = dict()

    def __init__(self):
        self.db_conn = sqlite3.connect('user.db')

    def register(self, client, creds):
        username, pwd = creds

        # Check existing user
        c = self.db_conn.cursor()
        c.execute("SELECT * FROM users WHERE username='%s'" % username)
        user = c.fetchone()
        if user is not None:
            self.send_error('User "%s" already exist' % username, client)
            return

        # Insert new user
        c.execute("INSERT INTO users VALUES('%s', '%s')" % tuple(creds))
        self.db_conn.commit()

        self.send("user-registered '%s'" % username, client)

    def authenticate(self, client, creds):
        # Validate credential
        c = self.db_conn.cursor()
        c.execute("SELECT * FROM users WHERE username='%s' AND pwd='%s'" % tuple(creds))
        user = c.fetchone()
        if user is None:
            self.send_error('Invalid credential', client)
            return

        username, pwd = creds
        print 'auth', username, pwd

        if username in self.clients:
            self.clients[username].close()
            self.send_all('user-disconnect ' + username)
        self.clients[username] = client

        client.is_auth = True
        client.username = username

        self.send("user-auth '%s'" % username, client)
        self.send_all("user-connect '%s'" % client.username)

        print "Client '%s' connecting (%d clients connected)" % (client.username, len(self.clients))

    def disconnect(self, client):
        if not client.was_closed and client.username in self.clients:
            del self.clients[client.username]
            client.request.close()
            self.send_all('user-disconnect ' + client.username)

        print "Client '%s' disconnecting (%d clients connected)" % (client.username, len(self.clients))

    def send_all(self, msg, src=None, metadata={}):
        for client in self.clients.values():
            if not client is src:
                self.send(msg, client, src)

    def send_to(self, msg, dst, src=None, metadata={}):
        self.send(msg, self.clients[dst], src)

    def send_error(self, error, dst):
        self.send("error %s" % error, dst, None)

    def send(self, msg, dst, src=None, metadata={}):
        try:
            metadata["src"] = src.username if src else "server"
            metadata_stamp = "[" + ",".join(map(lambda p: "%s=%s" % p, metadata.iteritems())) + "] "
            dst.request.sendall(metadata_stamp + msg)
        except:
            self.disconnect(dst)

    def handle_msg(self, msg, src):
        if not msg:
            return

        metadata, content = extract_metadata(msg)
        if src.is_auth and "dst" not in metadata:
            self.send_all(content, src, metadata)
        elif src.is_auth and metadata["dst"] in self.clients:
            self.send_to(content, metadata["dst"], src, metadata)
        elif "dst" in metadata and metadata["dst"] == "server":
            self.handle_command(content, src)
        elif src.is_auth:
            self.send_error("User '%s' is not connected" % metadata["dst"], src)
        else:
            self.send_error("You must be authenticated to send message", src)


    def handle_command(self, cmd, src):
        if src.is_auth and cmd == "list":
            self.send("\n".join(self.clients.keys()), src, metadata={"type":"user_list"})
        elif cmd.startswith(("register", "auth")) and not src.is_auth:
            creds = extract_credential(cmd)
            if len(creds) != 2:
                self.send_error("Invalid parameter count. %d given, expecting 2" % len(creds), src)
                return

            if cmd.startswith("register"):
                self.register(src, creds)
            else:
                self.authenticate(src, creds)
        else:
            self.send_error("Unknown command: '%s'" % cmd, src)

class ClientHandler(SocketServer.BaseRequestHandler):
    def setup(self):
        self.server = ChatServer()
        self.was_closed = False
        self.username = str(uuid.uuid4())
        self.is_auth = False

    def handle(self):
        try:
            while not self.was_closed:
                msg = self.request.recv(1024)
                if not msg:
                    break
                print msg
                self.server.handle_msg(msg.strip(), self)
        except:
            pass

        self.server.disconnect(self)

    def close(self):
        print "close %s connection" % self.username
        self.request.shutdown(socket.SHUT_RDWR)
        self.request.close()
        self.was_closed = True



class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass


if __name__ == "__main__":
    HOST, PORT = "0.0.0.0", 31337
    server = ThreadedTCPServer((HOST, PORT), ClientHandler)
    server.serve_forever()