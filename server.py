import socket
import re
import signal
import sys
import time
import select 
from itertools import zip_longest

USER_MAP = {}
CHANNEL_MAP = {}
SOCKET_LIST = []
NICKNAME_LIST = []
CHANNEL_MAP = {}

HOST = "127.0.0.1"
CREATION_DATE = time.time()
VERSION = "0.0.1"
SERVERNAME = socket.gethostname()


MAX_MSG_LEN=512
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

STATE_CONNECTION_REQUEST = 100
STATE_CONNECTION_NICK_SENT = 102
STATE_CONNECTION_USER_SENT = 103
STATE_CONNECTION_REGISTERED = 104

RPL_WELCOME = lambda nick, user: ":{host} 001 {nick} :Welcome to Internet Relay Network {nick}!{user}@{host}\r\n".format(nick=nick, user=user, host=HOST)
RPL_JOIN = lambda nick, user, host, chan: "{nick}!{user}@{host} JOIN {chan}\r\n".format(nick=nick, user=user, host=host, chan=chan)

ERR_NOSUCHCHANNEL = lambda chan, nick: "{host} 403 {nick} {chan} :No such channel\r\n".format(host=HOST, nick=nick, chan=chan)
ERR_NONICKNAMEGIVEN = "{host} 431 * :No nickname given\r\n".format(host=HOST)
ERR_NICKNAMEINUSE = lambda nick: "{host} 433 * {nick} :Nickname is already in use\r\n".format(host=HOST, nick=nick)  
ERR_NOTREGISTERED = "{host} 451 * :You have not registered\r\n".format(host=HOST)
ERR_NEEDMOREPARAMS = lambda nick, command: "{host} 461 {nick} {command} :Not enough parameters\r\n".format(host=HOST, nick=nick, command=command)
ERR_ALREADYREGISTERED = lambda nick: "{host} 462 {nick} :Unauthorized command (already registered)\r\n".format(host=HOST, nick=nick)
ERR_PASSWDMISMATCH = lambda nick: "{host} 464 {nick} :Password incorrect\r\n".format(host=HOST, nick=nick)
ERR_BADCHANMASK = lambda nick, chan: "{host} 476 {nick} {chan} :Bad Channel Mask\r\n".format(host=HOST, nick=nick, chan=chan)

def main():
    main_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    main_socket.bind(("127.0.0.1", 1234))
    main_socket.listen(5)

    SOCKET_LIST.append(main_socket)
    print("Listening on {}:1234...".format(socket.gethostname()))
    while True:
        r2r, r2w, err = select.select(SOCKET_LIST, [], [], 0) 

        for sock in r2r:
            if  sock == main_socket:
                incoming_socket, incoming_addr = main_socket.accept() 
                SOCKET_LIST.append(incoming_socket)
                USER_MAP[incoming_socket.fileno()] = {
                    "state": STATE_CONNECTION_REQUEST,
                    "host": incoming_addr[0]
                }
                print("Received connection form {}".format(incoming_addr))

            else:
                key = sock.fileno()
                user = USER_MAP[key]

                # Read message from the socket, up to MAX_MSG_LEN 
                message = sock.recv(MAX_MSG_LEN).decode()

                # Split the message by CR-LF
                messages = message.split("\r\n")

                if len(messages) == 0:
                    continue

                for message in messages:
                    # Ignore empty messages and capabilty negotiations
                    if message == "" or "CAP" in message:
                        continue
                    
                    m = RE_IRC_LINE.match(message)
                    if not m:
                        print("Invalid message: {}".format(message))
                        continue
                    
                    prefix = m.group("prefix") or ""
                    command = m.group("command")
                    params = (m.group("params") or "").split()
                    message = m.group("message") or ""
                    if message:
                        params.append(message)
                    
                    if user["state"] == STATE_CONNECTION_REQUEST:
                        if command != "NICK":
                            print("nick error: " + command)
                            sock.send(ERR_NOTREGISTERED.encode())
                            break
                        
                        if len(params) == 0:
                            print("params error in nick")
                            sock.send(ERR_NONICKNAMEGIVEN.encode())
                            break

                        nickname = params[0]
                        # Check if the nickname is in use
                        if nickname in NICKNAME_LIST:
                            sock.send(ERR_NICKNAMEINUSE(nickname).encode())
                            break

                        NICKNAME_LIST.append(nickname)

                        user["nick"] = nickname
                        user["state"] = STATE_CONNECTION_NICK_SENT

                    elif user["state"] == STATE_CONNECTION_NICK_SENT:
                        if command != "USER":
                            print("user error")
                            sock.send(ERR_NOTREGISTERED.encode())
                            break

                        if len(params) <  4:
                            print("params error user error")
                            sock.send(ERR_NEEDMOREPARAMS.encode())
                            break

                        # <user> <mode> <unused> <realname>
                        # We only care about realname and user
                        user["user"] = params[0]
                        user["realname"] = params[3]
                        user["state"] = STATE_CONNECTION_REGISTERED

                        sock.send(RPL_WELCOME(user["nick"], user["user"]).encode())

                    elif user["state"] == STATE_CONNECTION_REGISTERED:
                        if command == "JOIN":
                            if len(params) == 0:
                                sock.send(ERR_NEEDMOREPARAMS.encode())
                                break
                            
                            # TODO: Check if 'JOIN 0' was passed

                            # First come the channels, can be multiple seperated by commas
                            channels = params[0].split()

                            # Passwords are not required, can be multiple seperated by commas
                            passwords = []
                            if len(params) >= 2:
                                passwords = params[1].split()

                            for ch, p in zip_longest(channels, passwords, fillvalue=None):
                                # If channel name does not start with either & or #
                                # return error

                                chanmask = r'^(?P<mask>[&#])(?P<chan>\w+)$'                         
                                m = re.match(chanmask, ch)
                                if not m:
                                    sock.send(ERR_BADCHANMASK(user["nick"], ch).encode())
                                    continue

                                ch = m.group("chan")
                                mask = m.group("mask")

                                channel = CHANNEL_MAP.get(ch)

                                # If the channel does not exist - create it
                                if not channel:
                                    # Set maks for future validations
                                    # Set the creator as the first user
                                    # Even if password was sent - ignore it

                                    channel = {
                                        "mask": mask,
                                        "user_nicks": [user["nick"]],
                                        "user_sockets": [sock],
                                        "topic": "<none>"
                                    }
                                else:
                                    # Since the channel exists, check if the mask is correct
                                    if channel["mask"] != mask:
                                        sock.send(ERR_BADCHANMASK(user["nick"], channel).encode())
                                        continue
                                    
                                    # TODO: Add password checks?

                                    # If the user is already in the channel - skip it
                                    if user["nick"] in channel["user_nicks"]:
                                        continue
                                    else:
                                        channel["user_nicks"].append(user["nick"])
                                        channel["user_sockets"].append(sock)

                                        # Notify other users in the same channel that the person has joined
                                        for sock in channel["user_sockets"]:
                                            sock.send(RPL_JOIN(user["nick"], user["user"], user["host"], mask+ch).encode())

                                # Check if user has any channels
                                user_channels = user.get("channels")
                                if not user_channels:
                                    user["channels"] = [ch]
                                else:
                                    user["channels"].append(ch)
                                
                                # Finally append the channel to the list
                                CHANNEL_MAP[ch] = channel

                    USER_MAP[key] = user


if __name__ == '__main__':
    main()