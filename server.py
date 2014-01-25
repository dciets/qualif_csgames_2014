#!/usr/bin/env python2

import sqlite3
import socket
import threading
import SocketServer
import traceback
import uuid
import logging
import signal
import sys
from simple_websocket_server import WebSocket, WebSocketServer

SERVE_WEBSOCKET = True
TCP_PORT = 31337
WEBSOCKET_PORT = 31338
HOST = '0.0.0.0'

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
        #dict and list comprehension are so sexy
        metadata = {s[0].strip():s[1].strip() for s in [i.split("=") for i in metadata_str.split(",")]}

    return (metadata, content)

def extract_credential(msg):
    return map(str.strip, msg.split(' ')[1:])

class ChatServer(object):
    __metaclass__ = Singleton

    clients = dict()

    def __init__(self):
        self.db_lock = threading.Lock()

    def register(self, client, creds):
        username, pwd = creds

        with self.db_lock:
            db_conn = sqlite3.connect('user.db')
            # Check existing user
            c = db_conn.cursor()
            c.execute("SELECT * FROM users WHERE username='%s'" % username)
            user = c.fetchone()
            if user is not None:
                self.send_error('User "%s" already exist' % username, client)
                db_conn.close()
                return

            # Insert new user
            c.execute("INSERT INTO users VALUES('%s', '%s')" % tuple(creds))
            db_conn.commit()
            db_conn.close()

        self.send("user-registered '%s'" % username, client)

    def authenticate(self, client, creds):
        # Validate credential
        with self.db_lock:
            db_conn = sqlite3.connect('user.db')
            c = db_conn.cursor()
            c.execute("SELECT * FROM users WHERE username='%s' AND pwd='%s'" % tuple(creds))
            user = c.fetchone()
            db_conn.close()

        if user is None:
            self.send_error('Invalid credential', client)
            return

        username, pwd = creds
        logging.debug('auth %s %s' % (username, pwd))

        if username in self.clients:
            self.clients[username].close()
            self.send_all('user-disconnect ' + username)
        self.clients[username] = client

        client.is_auth = True
        client.username = username

        self.send("user-auth '%s'" % client.username, client)
        self.send_all("user-connect '%s'" % client.username)

        logging.info("Client '%s' connecting (%d clients connected)" % (client.username, len(self.clients)))

    def disconnect(self, client):
        if not client.was_closed and client.username in self.clients:
            del self.clients[client.username]
            client.request.close()
            self.send_all('user-disconnect ' + client.username)

        logging.info("Client '%s' disconnecting (%d clients connected)" % (client.username, len(self.clients)))

    def send_all(self, msg, src=None, metadata={}):
        for client in self.clients.values():
            if not client is src:
                self.send(msg, client, src, metadata)

    def send_to(self, msg, dst, src=None, metadata={}):
        self.send(msg, self.clients[dst], src, metadata)

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

        logging.debug('msg: %s', msg)

        metadata, content = extract_metadata(msg)
        if src.is_auth and "dst" not in metadata:
            self.send_all(content, src, metadata)
        elif "dst" in metadata:
            if metadata["dst"] in self.clients:
                self.send_to(content, metadata["dst"], src, metadata)
            if metadata["dst"] == "server":
                self.handle_command(content, src)
        elif src.is_auth:
            self.send_error("User '%s' is not connected" % metadata["dst"], src)
        else:
            self.send_error("You must be authenticated to send message", src)


    def handle_command(self, cmd, src):
        if src.is_auth and cmd == "list":
            self.send(" \n".join(self.clients.keys()), src, metadata={"type":"user_list"})
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
                msg = self.request.recv(1048576)
                if not msg:
                    break
                logging.debug("Msg received: %s" % msg)
                self.server.handle_msg(msg.strip(), self)
        except:
            pass

        self.server.disconnect(self)

    def close(self):
        logging.info("close %s connection" % self.username)
        self.request.shutdown(socket.SHUT_RDWR)
        self.request.close()
        self.was_closed = True

class WebSocketClientHandler():
    def setup(self):
        self.server = ChatServer()
        self.was_closed = False
        self.username = str(uuid.uuid4())
        self.is_auth = False

    def onmessage(self, msg):
        self.server.handle_msg(msg.strip(), self)

    def onclose(self):
        self.server.disconnect(self)

    def close(self):
        logging.info("close %s websocket connection" % self.username)
        self.request.client.shutdown(socket.SHUT_RDWR)
        self.was_closed = True

class ThreadedTCPServer(SocketServer.ThreadingMixIn, SocketServer.TCPServer):
    pass


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")

    if SERVE_WEBSOCKET:
        server = WebSocketServer(HOST, WEBSOCKET_PORT, WebSocketClientHandler)
        server_thread = threading.Thread(target=server.listen, args=[5])
        server_thread.start()

        # Add SIGINT handler for killing the threads
        def signal_handler(signal, frame):
            logging.info("Caught Ctrl+C, shutting down...")
            server.running = False
            sys.exit()

        signal.signal(signal.SIGINT, signal_handler)

    server = ThreadedTCPServer((HOST, TCP_PORT), ClientHandler)
    logging.info("Listening TCP on %s" % TCP_PORT)
    server.serve_forever()