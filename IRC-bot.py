import socket
import sys
import re
from datetime import datetime
from random import randrange


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


# take random line from text file, alorithm taken from stackoverflow
# https://stackoverflow.com/questions/40140660/print-random-line-from-txt-file/40140722
def get_random_line(afile, default=None):
    """Return a random line from the file (or default)."""
    line = default
    for i, aline in enumerate(afile, start=1):
        if randrange(i) == 0:  # random int [0..i)
            line = aline
    return line


# executed when ping is received
def ping(me):
    # format and send appropriate pong
    pong_message = "PONG :"+me.group("params")+me.group("message")
    print(pong_message)
    client.send(pong_message.encode())
    return


def get_chat_response(mes):
    if mes.startswith("!time"):
        now = datetime.now()
        return now.strftime("%H:%M:%S")
    elif mes.startswith("!day"):
        today = datetime.today().strftime("%A")
        return today
    return "Command Not Recognised"


# executed when channel message or pm is received
def privmsg(me):
    reply = True
    par = me.group('params')
    mes = me.group('message')
    pref = me.group('prefix')
    # print(f"P: {me.group('params')} \nM: {me.group('message')}")

    # determines if message came from channel or private message
    if par.startswith(" #"):  # channel
        print(f"Message in channel {par}: {mes}")
        recv = par
        if mes.startswith("!"):
            content = get_chat_response(mes)
        else:
            reply = False

    else:  # private message
        print(f"PM from {pref}: {mes}")
        recv = pref.split('!')[0]
        content = "AbCdEfGhIjKlMnOp"
        with open('facts.txt') as file:
            content = get_random_line(file)

    if reply:
        reply = "PRIVMSG " + recv + " :"+content+"\r\n"
        print(reply)
        client.send(reply.encode())
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





