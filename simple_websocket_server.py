#!/usr/bin/env python2

import time
import struct
import socket
import hashlib
import base64
import sys
from select import select
import logging
from threading import Thread
import signal

# Simple WebSocket server implementation. Handshakes with the client then echos back everything
# that is received. Has no dependencies (doesn't require Twisted etc) and works with the RFC6455
# version of WebSockets. Tested with FireFox 16, though should work with the latest versions of
# IE, Chrome etc.
#
# rich20b@gmail.com
# Adapted from https://gist.github.com/512987 with various functions stolen from other sites, see
# below for full details.
#
# isra017@gmail.com
# Added a way to abstract an handler

# Constants
MAGIC_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"
TEXT = 0x01
BINARY = 0x02

OPCODE_TEXT = 1
OPCODE_CLOSE = 8


# WebSocket implementation
class WebSocket(object):

    handshake = (
        "HTTP/1.1 101 Web Socket Protocol Handshake\r\n"
        "Upgrade: WebSocket\r\n"
        "Connection: Upgrade\r\n"
        "Sec-WebSocket-Accept: %(acceptstring)s\r\n"
        "Server: TestTest\r\n"
        "Access-Control-Allow-Origin: http://localhost\r\n"
        "Access-Control-Allow-Credentials: true\r\n"
        "\r\n"
    )


    # Constructor
    def __init__(self, client, server, handler):
        self.client = client
        self.server = server
        self.handshaken = False
        self.header = ""
        self.data = ""
        self.handler = handler
        self.handler.request = self
        self.handler.setup()

    # Serve this client
    def feed(self, data):

        # If we haven't handshaken yet
        if not self.handshaken:
            logging.debug("No handshake yet")
            self.header += data
            if self.header.find('\r\n\r\n') != -1:
                parts = self.header.split('\r\n\r\n', 1)
                self.header = parts[0]
                if self.dohandshake(self.header, parts[1]):
                    logging.info("Handshake successful")
                    self.handshaken = True

        # We have handshaken
        else:
            logging.debug("Handshake is complete")

            # Decode the data that we received according to section 5 of RFC6455
            recv, opcode = self.decodeCharArray(data)

            # Send our reply
            if opcode == OPCODE_TEXT:
                self.handler.onmessage(''.join(recv).strip());
            elif opcode == OPCODE_CLOSE:
                self.client.shutdown(socket.SHUT_RDWR)


    # Stolen from http://www.cs.rpi.edu/~goldsd/docs/spring2012-csci4220/websocket-py.txt
    def sendMessage(self, s):
        """
        Encode and send a WebSocket message
        """

        # Empty message to start with
        message = ""

        # always send an entire message as one frame (fin)
        b1 = 0x80

        # in Python 2, strs are bytes and unicodes are strings
        if type(s) == unicode:
            b1 |= TEXT
            payload = s.encode("UTF8")

        elif type(s) == str:
            b1 |= TEXT
            payload = s

        # Append 'FIN' flag to the message
        message += chr(b1)

        # never mask frames from the server to the client
        b2 = 0

        # How long is our payload?
        length = len(payload)
        if length < 126:
            b2 |= length
            message += chr(b2)

        elif length < (2 ** 16) - 1:
            b2 |= 126
            message += chr(b2)
            l = struct.pack(">H", length)
            message += l

        else:
            l = struct.pack(">Q", length)
            b2 |= 127
            message += chr(b2)
            message += l

        # Append payload to message
        message += payload

        # Send to the client
        self.client.send(str(message))


    # Stolen from http://stackoverflow.com/questions/8125507/how-can-i-send-and-receive-websocket-messages-on-the-server-side
    def decodeCharArray(self, stringStreamIn):

        # Turn string values into opererable numeric byte values
        byteArray = [ord(character) for character in stringStreamIn]
        datalength = byteArray[1] & 127
        opcode = byteArray[0] & 0xf
        indexFirstMask = 2

        if datalength == 126:
            indexFirstMask = 4
            datalength = struct.unpack('!H', stringStreamIn[2:4])[0]
        elif datalength == 127:
            indexFirstMask = 10
            datalength = struct.unpack('!I', stringStreamIn[2:4])[0]

        # Extract masks
        masks = [m for m in byteArray[indexFirstMask : indexFirstMask+4]]
        indexFirstDataByte = indexFirstMask + 4

        # List of decoded characters
        decodedChars = []

        # Loop through each byte that was received
        for i in xrange(datalength):
            # Unmask this byte and add to the decoded buffer
            decodedChars.append( chr(byteArray[i + indexFirstDataByte] ^ masks[i % 4]) )

        # Return the decoded string
        return (decodedChars, opcode)


    # Handshake with this client
    def dohandshake(self, header, key=None):

        logging.debug("Begin handshake")

        # Get the handshake template
        handshake = self.handshake

        # Step through each header
        for line in header.split('\r\n')[1:]:
            name, value = line.split(': ', 1)

            # If this is the key
            if name.lower() == "sec-websocket-key":

                # Append the standard GUID and get digest
                combined = value + MAGIC_GUID
                response = base64.b64encode(hashlib.sha1(combined).digest())

                # Replace the placeholder in the handshake response
                handshake = handshake % { 'acceptstring' : response }

        logging.debug("Sending handshake")
        self.client.send(handshake)
        return True

    def onmessage(self, data):
        logging.info("Got message: %s" % data)
        pass

    def sendall(self, data):
        self.sendMessage(data)

    def send(self, data):
        self.client.send("\x00%s\xff" % data)

    def close(self):
        self.client.close()


# WebSocket server implementation
class WebSocketServer(object):

    # Constructor
    def __init__(self, bind, port, handler):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.socket.bind((bind, port))
        self.bind = bind
        self.port = port
        self.handler = handler
        self.connections = {}
        self.listeners = [self.socket]

    # Listen for requests
    def listen(self, backlog=5):

        self.socket.listen(backlog)
        logging.info("Listening on %s" % self.port)

        # Keep serving requests
        self.running = True
        while self.running:

            # Find clients that need servicing
            rList, wList, xList = select(self.listeners, [], self.listeners, 1)
            for ready in rList:
                if ready == self.socket:
                    logging.debug("New client connection")
                    client, address = self.socket.accept()
                    fileno = client.fileno()
                    self.listeners.append(fileno)
                    self.connections[fileno] = WebSocket(client, self, self.handler())
                else:
                    logging.debug("Client ready for reading %s" % ready)
                    client = self.connections[ready].client
                    data = client.recv(1048576)
                    fileno = client.fileno()
                    if data:
                        self.connections[fileno].feed(data)
                    else:
                        logging.debug("Closing client %s" % ready)
                        self.connections[fileno].handler.onclose()
                        del self.connections[fileno]
                        self.listeners.remove(ready)

            # Step though and delete broken connections
            for failed in xList:
                if failed == self.socket:
                    logging.error("Socket broke")
                    for fileno, conn in self.connections:
                        conn.close()
                    self.running = False

class ClientHandler():
    def setup(self):
        pass

    def onmessage(self, msg):
        self.request.sendall(msg)

    def onclose(self):
        pass

# Entry point
if __name__ == "__main__":

    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(levelname)s - %(message)s")
    server = WebSocketServer("", 8000, ClientHandler)
    server_thread = Thread(target=server.listen, args=[5])
    server_thread.start()

    # Add SIGINT handler for killing the threads
    def signal_handler(signal, frame):
        logging.info("Caught Ctrl+C, shutting down...")
        server.running = False
        sys.exit()
    signal.signal(signal.SIGINT, signal_handler)

    while True:
        time.sleep(100)