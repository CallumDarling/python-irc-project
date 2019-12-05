import socket
import sys
import re
from datetime import datetime
from random import randrange

# Check to see if right number of command line arguments have been entered
if len(sys.argv) != 3:
    print("Arguments: host:port #channel")
    exit()

# Variables
host = sys.argv[1].split(":")
nick = "ProBot"
user = "PROBot"
real = "Pro Bot"
channel = sys.argv[2]
# Connect.
client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
client.connect((host[0], int(host[1])))

# IRC line regex
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

# if a message has been sent that begins with an !mark this funciton will be called
# It return the response that the bot will give to each specific chat command
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
        content = "American President Calvin Coolidge (1923-1929) used to like Vaseline being rubbed on his head while he ate breakfast in bed"
        with open('facts.txt') as file:
            content = get_random_line(file)

    # If there is a response to the message send it to the user / channel that the original message came from
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
    # print(f"P:{prefix}\nC:{command}\nPa:{params}\nM:{message}")

    if(command=="433"):
        newNick = nick+"_"
        client.send(('NICK ' + newNick + '\r\n').encode())
        client.send(('USER ' + user + ' 0 * :' + real + '\r\n').encode())
        client.send(('JOIN '+ channel + '\r\n').encode())
        return
    
    # calls function depending on message type
    commands = {
        "PING": ping,
        "PRIVMSG": privmsg,
    }
    try:
        return commands[command](me)
    except Exception:
        return "CNS"




# Send User and Nick to server.
client.send(('NICK ' + nick + '\r\n').encode())
client.send(('USER ' + user + ' 0 * :' + real + '\r\n').encode())

# Join channel
client.send(('JOIN '+ channel + '\r\n').encode())


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
