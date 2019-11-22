import socket
import re
import signal
import sys

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind((socket.gethostname(), 1234))
s.listen(5)

connected_clients = {}

MAX_MSG_LEN=512
USER_MESSAGE_TEMPLATE = r"USER (?P<username>\w+) (?P<hostname>\w+) (?P<servername>\w+) :(?P<realname>\w+)"
NICK_MESSAGE_TEMPLATE = r"NICK (?P<nickname>\w{1,9})"


while True:
    try:
        clientsocket, address = s.accept()
        print("Received connection from: {}".format(address))
        clientsocket.send(b"Successfully connected")
        
        while True:
            identification = clientsocket.recv(1024).decode()
            print(identification)
            
            m = re.match(USER_MESSAGE_TEMPLATE, identification)
            if m is None:
                clientsocket.send(b"Ivalid user command. Disconnected...")
                clientsocket.shutdown(1)
                clientsocket.close()

        

    except Exception as e:
        print(e)
        s.shutdown(1)
        s.close()
        break

def signal_handler(sig, frame):
    s.shutdown(1)
    s.close()
    exit(0)

signal.signal(signal.SIGINT, signal_handler)