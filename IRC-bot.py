import socket
import sys

if len(sys.argv) != 5:
    print("Arguments: host:port nickname username realname")
    exit()

host = sys.argv[1].split(":")
nick = sys.argv[2]
user = sys.argv[3]
real = sys.argv[4]


# Parse input.
ping = 'PING '
pong = 'PONG '


# Connect.
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((host[0], int(host[1])))

# Handshake.
client.send(('NICK ' + nick + '\r\n').encode())
client.send(('USER ' + user + ' 0 * :' + real + '\r\n').encode())

# Output and ping/pong.
while True:
    data = client.recv(1024)
    print(data.decode())

    if data.decode().startswith(ping):
        resp = data.strip(ping.encode());
        client.send(pong.encode() + resp)
        print(pong + resp.decode())