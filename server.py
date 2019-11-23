import socket
import re
import signal
import sys
import select 
from datetime import datetime
from itertools import zip_longest

USER_MAP = {}
CHANNEL_MAP = {}
SOCKET_LIST = []
NICKNAME_LIST = []
CHANNEL_MAP = {}

HOST = "127.0.0.1"
PORT = 1234
CREATION_DATE = datetime.now()
VERSION = "0.0.1"
SERVERNAME = socket.gethostname()
USER_MODES="DOQRSZaghilopswz"
CHANNEL_MODES="CFILMPQSbcefgijklmnopqrstvz"


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

RPL_WELCOME = lambda nick, user, uhost: "{host} 001 {nick} :Welcome to Internet Relay Network{nick}!{user}@{uhost}\r\n".format(host=HOST, nick=nick, user=user, uhost=uhost)
RPL_YOURHOST = lambda nick: "{host} 002 {nick} :Your host is {servername}[{host}], running version {ver}\r\n".format(servername=SERVERNAME, host=HOST, ver=VERSION, nick=nick)
RPL_CREATED = lambda nick: "{host} 003 {nick} :This server was created {date}\r\n".format(host=HOST, date=CREATION_DATE, nick=nick)
RPL_MYINFO = lambda nick: "{host} 004 {nick} :{servername} {version} {user_modes} {channel_modes}".format(host=HOST, nick=nick, servername=SERVERNAME, version=VERSION, user_modes=USER_MODES, channel_modes=CHANNEL_MODES)
RPL_JOIN = lambda nick, user, host, chan: "{nick}!{user}@{host} JOIN {chan}\r\n".format(nick=nick, user=user, host=host, chan=chan)
RPL_PART = lambda nick, user, host, chan, reason="Leaving": "{nick}!{user}@{host} PART {chan} :{reason}\r\n".format(nick=nick, user=user, host=host, chan=chan, reason=reason)
RPL_NOTOPIC = lambda nick, chan: "{host} 331 {nick} {chan} :Not topic is set\r\n".format(host=HOST, nick=nick, chan=chan)
RPL_TOPIC = lambda nick, chan, topic: "{host} 332 {nick} {chan} :{topic}\r\n".format(host=HOST, nick=nick, chan=chan, topic=topic)

ERR_NOSUCHCHANNEL = lambda nick, chan: "{host} 403 {nick} {chan} :No such channel\r\n".format(host=HOST, nick=nick, chan=chan)
ERR_TOOMANYTARGETS = lambda nick, target: "{host} 403 {nick}"
ERR_NORECIPIENT = lambda nick, command: "{host} 411 {nick} :No recipient given ({command})".format(host=HOST, nick=nick, command=command)
ERR_NONICKNAMEGIVEN = "{host} 431 * :No nickname given\r\n".format(host=HOST)
ERR_NICKNAMEINUSE = lambda nick: "{host} 433 * {nick} :Nickname is already in use\r\n".format(host=HOST, nick=nick)  
ERR_NOTONCHANNEL = lambda nick, chan: "{host} 442 {nick} {chan} :You're not on that channel\r\n".format(host=HOST, nick=nick, chan=chan)
ERR_NOTREGISTERED = "{host} 451 * :You have not registered\r\n".format(host=HOST)
ERR_NEEDMOREPARAMS = lambda nick, command: "{host} 461 {nick} {command} :Not enough parameters\r\n".format(host=HOST, nick=nick, command=command)
ERR_ALREADYREGISTERED = lambda nick: "{host} 462 {nick} :Unauthorized command (already registered)\r\n".format(host=HOST, nick=nick)
ERR_PASSWDMISMATCH = lambda nick: "{host} 464 {nick} :Password incorrect\r\n".format(host=HOST, nick=nick)
ERR_BADCHANMASK = lambda nick, chan: "{host} 476 {nick} {chan} :Bad Channel Mask\r\n".format(host=HOST, nick=nick, chan=chan)

def privmsg_handler(user: dict, params: list, sock: socket.socket) -> dict:
    if len(params) == 0:
        sock.send(ERR_NORECIPIENT(user["nick"], "PRIVMSG").encode())
        return user
    
    if len(params) > 2:
        sock.send()

    # TODO: Handle ERR_CANNOTSENDTOCHAN ? 

    # Drop all requests where target is host mask
    print(params)


    return user

def part_handler(user: dict, params: list, sock: socket.socket) -> dict:
    if len(params) == 0:
        sock.send(ERR_NEEDMOREPARAMS(user["nick"], "PART").encode())
        return user

    channels = params[0].split()
    reason = "Leaving"
    if len(params) >= 2:
        reason = params[1]
    
    for channel in channels:
        # If the channel does not exist, return an error
        if channel not in CHANNEL_MAP:
            sock.send(ERR_NOSUCHCHANNEL(user["nick"], channel).encode())
            continue

        # If user is not on the channel, return an error
        if channel not in user["channels"]:
            sock.send(ERR_NOTONCHANNEL(user["nick"], channel).encode())
            continue

        # Remove the channel from user channels
        user["channels"].remove(channel)

        # Remove user nick and socket from channels map
        CHANNEL_MAP[channel]["user_nicks"].remove(user["nick"])
        CHANNEL_MAP[channel]["user_sockets"].remove(sock)

        # Notify all the users in the channel that the user has left
        for sock in CHANNEL_MAP[channel]["user_sockets"]:
            sock.send(RPL_PART(user["nick"], user["user"], user["host"], channel, reason).encode())

        # If the channel has no users left - destroy it
        if len(CHANNEL_MAP[channel["user_nicks"]]) == 0:
            CHANNEL_MAP.pop(channel)

    return user
    

def join_handler(user: dict, params: list, sock: socket.socket) -> dict: 
    if len(params) == 0:
        sock.send(ERR_NEEDMOREPARAMS(user["nick"], "JOIN").encode())
        return user
                            
    # First come the channels, can be multiple seperated by commas
    channels = params[0].split()

    # Handle JOIN 0. AKA leave all channels
    if channels[0] == "0":
        # Gather all user channels into an array
        params = user["channels"]

        # If user is not in any channels - ignore
        if len(params) == 0:
            return user

        return part_handler(user, params, sock)

    # Passwords are not required, can be multiple seperated by commas
    passwords = []
    if len(params) >= 2:
        passwords = params[1].split()

    for ch, p in zip_longest(channels, passwords, fillvalue=None):
        # If channel name does not start with either & or #
        # return error

        chanmask = r'^(?P<chan>(?P<mask>[&#+!])\w+)$'                         
        m = re.match(chanmask, ch)
        if not m:
            sock.send(ERR_BADCHANMASK(user["nick"], ch).encode())
            continue

        ch = m.group("chan")

        channel = CHANNEL_MAP.get(ch)

        # If the channel does not exist - create it
        if not channel:
            # Set maks for future validations
            # Set the creator as the first user
            # Even if password was sent - ignore it

            channel = {
                "user_nicks": [user["nick"]],
                "user_sockets": [sock],
            }
        else:
            # TODO: Add password checks?

            # If the user is already in the channel - skip it
            if user["nick"] in channel["user_nicks"]:
                continue
            else:
                channel["user_nicks"].append(user["nick"])
                channel["user_sockets"].append(sock)


        # Check if user has any channels
        user_channels = user.get("channels")
        if not user_channels:
            user["channels"] = [ch]
        else:
            user["channels"].append(ch)
                                
        # Finally append the channel to the list
        CHANNEL_MAP[ch] = channel

        # Notify other users in the same channel that the person has joined
        # This also includes the newly joined user
        for sock in channel["user_sockets"]:
            sock.send(RPL_JOIN(user["nick"], user["user"], user["host"], ch).encode())

        # Also send back topic if exists
        channel_topic = channel.get("topic")
        if channel_topic:
            sock.send(RPL_TOPIC(user["nick"], ch, channel_topic).encode())
        else:
            sock.send(RPL_NOTOPIC(user["nick"], ch).encode())

        
    return user


def main():
    main_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    main_socket.bind((HOST, PORT))
    main_socket.listen(5)

    SOCKET_LIST.append(main_socket)
    print("Listening on {}:{}...".format(HOST, PORT))
    while True:
        r2r, _, _ = select.select(SOCKET_LIST, [], [], 0) 

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

                        reply = RPL_WELCOME(user["nick"], user["user"], user["host"]) \
                            + RPL_YOURHOST(user["nick"]) + RPL_CREATED(user["nick"]) \
                            + RPL_MYINFO(user["nick"])
                        sock.send(reply.encode())

                    elif user["state"] == STATE_CONNECTION_REGISTERED:
                        print(prefix)
                        if command == "JOIN":
                            user = join_handler(user, params, sock)
                        elif command == "PART":
                            user = part_handler(user, params, sock)
                        elif command == "PRIVMSG":
                            user = privmsg_handler(user, params, sock)
                    USER_MAP[key] = user


if __name__ == '__main__':
    main()