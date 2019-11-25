import socket
import sys
import re

if len(sys.argv) != 6:
    print("Arguments: host:port nickname username realname #channel")
    exit()

host = sys.argv[1].split(":")
nick = sys.argv[2]
user = sys.argv[3]
real = sys.argv[4]
channel = sys.argv[5]

RE_IRC_LINE = re.compile(
    """
    ^
    (:(?P<prefix>[^\s]+)\s+)?    # Optional prefix (src, nick!host, etc)
                                 # Prefix matches all non-space characters
                                 # Must start with a ":" character
    (?P<command>[^:\s]+)         # Command is required (JOIN, 001, 403)
                                 # Command matches all non-space characters
    (?P<params>(\s+[^:][^\s]*)*) # Optional params after command
                                 # Must have at least one leading space
                                 # Params end at first ":" which starts message
    (?:\s+:(?P<message>.*))?     # Optional message starts after first ":"
                                 # Must have at least one leading space
    $
    """, re.VERBOSE)

# Parse input.

pong = 'PONG '


# Connect.
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((host[0], int(host[1])))

# Handshake.
client.send(('NICK ' + nick + '\r\n').encode())
client.send(('USER ' + user + ' 0 * :' + real + '\r\n').encode())

# Join channel
client.send(('JOIN '+ channel + '\r\n').encode())


# executed when ping is received
def ping(me):
    # format and send appropriate pong
    pong_message = "PONG :"+me.group("params")+me.group("message")
    print(pong_message)
    client.send(pong_message.encode())
    return


# executed when channel message or pm is recived
def privmsg(me):
    # print("whole up")
    par = me.group('params')
    mes = me.group('message')
    # print(f"P: {me.group('params')} \nM: {me.group('message')}")
    # determines if message came from channel or private message
    if par.startswith(" #"):
        print(f"Message in channel {par}: {mes}")
    else:
        print(f"PM from {m.group('prefix')}: {mes}")
    # print("Some charming lad is dming us")

    return


# handles received commands
def command_handler(me):
    # splits regex matched command into components
    prefix = me.group("prefix") or ""
    command = me.group("command")
    params = (me.group("params") or "").split()
    message = me.group("message") or ""
    # print(f"P:{prefix} C:{command} Pa:{params} M:{message}")

    # calls function depending on message type
    switcher = {
        "PING": ping,
        "PRIVMSG": privmsg,
    }
    try:
        return switcher[command](me)
    except Exception:
        return "CNS"


# Output and ping/pong.
while True:
    # receives data from server and splits into messages
    data = client.recv(1024)
    messages = data.decode().split('\r\n')

    # ignores empty messages
    for message in messages:
        if message == "":
            continue


        print(message)
        # checks to see if message is valid using regex
        m = RE_IRC_LINE.match(message)
        if not m:
            print(f"invalid command recieved {message}")
            continue

        command_handler(m)





