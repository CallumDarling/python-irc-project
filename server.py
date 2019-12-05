import socket
import re
import signal
import sys
import select 
from datetime import datetime
from itertools import zip_longest

USER_MAP = {}
SOCKET_LIST = []
NICK_MAP = {}
CHANNEL_MAP = {}

PORT = 6667
CREATION_DATE = datetime.now()
VERSION = "0.0.1"
SERVERNAME = socket.gethostname()
HOST = socket.gethostbyname(SERVERNAME)
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

RPL_WELCOME = lambda nick, user, uhost: ":{host} 001 {nick} :Welcome to Internet Relay Network\n{nick}!{user}@{uhost}\r\n".format(host=HOST, nick=nick, user=user, uhost=uhost)
RPL_YOURHOST = lambda nick: ":{host} 002 {nick} :Your host is {servername}[{host}], running version {ver}\r\n".format(servername=SERVERNAME, host=HOST, ver=VERSION, nick=nick)
RPL_CREATED = lambda nick: ":{host} 003 {nick} :This server was created {date}\r\n".format(host=HOST, date=CREATION_DATE, nick=nick)
RPL_MYINFO = lambda nick: ":{host} 004 {nick} :{servername} {version} {user_modes} {channel_modes}\r\n".format(host=HOST, nick=nick, servername=SERVERNAME, version=VERSION, user_modes=USER_MODES, channel_modes=CHANNEL_MODES)
RPL_JOIN = lambda nick, user, host, chan: ":{nick}!{user}@{host} JOIN {chan}\r\n".format(nick=nick, user=user, host=host, chan=chan)
RPL_PART = lambda nick, user, host, chan, reason="Leaving": ":{nick}!{user}@{host} PART {chan} :{reason}\r\n".format(nick=nick, user=user, host=host, chan=chan, reason=reason)
RPL_NOTOPIC = lambda nick, chan: ":{host} 331 {nick} {chan} :No topic is set\r\n".format(host=HOST, nick=nick, chan=chan)
RPL_TOPIC = lambda nick, chan, topic: ":{host} 332 {nick} {chan} :{topic}\r\n".format(host=HOST, nick=nick, chan=chan, topic=topic)
RPL_NICK = lambda nick, user, uhost, new_nick: ":{nick}!{user}@{uhost} NICK {new_nick}\r\n".format(nick=nick, user=user, uhost=uhost, new_nick=new_nick)
RPL_PRIVMSG = lambda nick, user, uhost, target, msg: ":{nick}!{user}@{uhost} PRIVMSG {target} :{msg}\r\n".format(nick=nick, user=user, uhost=uhost, target=target, msg=msg)
# Using '=' since we are not supporting private or secret channels
RPL_NAMREPLY = lambda nick, chan, users: ":{host} 353 {nick} = {chan} :{users}\r\n".format(host=HOST, nick=nick, chan=chan, users=users)
RPL_ENDOFNAMES = lambda nick, chan: ":{host} 366 {nick} {chan} :End of NAMES list\r\n".format(host=HOST, nick=nick, chan=chan)

ERR_NOSUCHNICK = lambda nick, target_nick: ":{host} 401 {nick} {target_nick} :No such nick/channel\r\n".format(host=HOST, nick=nick, target_nick=target_nick)
ERR_NOSUCHCHANNEL = lambda nick, chan: ":{host} 403 {nick} {chan} :No such channel\r\n".format(host=HOST, nick=nick, chan=chan)
ERR_CANNOTSENDTOCHAN = lambda nick, chan: ":{host} 404 {nick} {chan} :Cannot send to channel\r\n".format(host=HOST, nick=nick, chan=chan)
ERR_TOOMANYTARGETS = lambda nick, target, err_code, abort_msg: ":{host} 407 {nick} {target} :{err_code} recipients\r\n. {abort_msg}".format(host=HOST, nick=nick, target=target, err_code=err_code, abort_msg=abort_msg)
ERR_NORECIPIENT = lambda nick, command: ":{host} 411 {nick} :No recipient given ({command})\r\n".format(host=HOST, nick=nick, command=command)
ERR_NOTEXTTOSEND = lambda nick: ":{host} 412 {nick} :No text to send\r\n".format(host=HOST, nick=nick)
ERR_NONICKNAMEGIVEN = ":{host} 431 * :No nickname given\r\n".format(host=HOST)
ERR_NICKNAMEINUSE = lambda nick: ":{host} 433 * {nick} :Nickname is already in use\r\n".format(host=HOST, nick=nick)  
ERR_NOTONCHANNEL = lambda nick, chan: ":{host} 442 {nick} {chan} :You're not on that channel\r\n".format(host=HOST, nick=nick, chan=chan)
ERR_NOTREGISTERED = ":{host} 451 * :You have not registered\r\n".format(host=HOST)
ERR_NEEDMOREPARAMS = lambda nick, command: ":{host} 461 {nick} {command} :Not enough parameters\r\n".format(host=HOST, nick=nick, command=command)
ERR_ALREADYREGISTERED = lambda nick: ":{host} 462 {nick} :Unauthorized command (already registered)\r\n".format(host=HOST, nick=nick)
ERR_PASSWDMISMATCH = lambda nick: ":{host} 464 {nick} :Password incorrect\r\n".format(host=HOST, nick=nick)
ERR_BADCHANMASK = lambda nick, chan: ":{host} 476 {nick} {chan} :Bad Channel Mask\r\n".format(host=HOST, nick=nick, chan=chan)

def quit_handler(user: dict, params: list, sock: socket.socket):
    quit_message = "Leaving"
    if len(params) > 0:
        quit_message = params[0]
    
    # Ignore return value since we are deleting the user
    part_handler(user, ["0", quit_message], sock)

    # Delete user from user map
    USER_MAP.pop(sock.fileno())

    # Delete nickname from nickname list
    NICK_MAP.pop(user["nick"])

    # Delete socket from socket list
    SOCKET_LIST.remove(sock)        


def privmsg_handler(user: dict, params: list, sock: socket.socket):
    if len(params) == 0:
        sock.send(ERR_NORECIPIENT(user["nick"], "PRIVMSG").encode())
        return
    
    if len(params) == 1:
        sock.send(ERR_NOTEXTTOSEND(user["nick"]).encode())
        return

    if len(params) > 2:
        sock.send(ERR_TOOMANYTARGETS( user["nick"], params[0], 
            len(params), "Too many recipients").encode())
        return
    
    target = params[0]
    message = params[1]

    # Check if network or server mask.
    # Since we do not support cross server comms, just drop them
    m = re.match(r'^([\$#]).*\.\w+?$', target)
    if m:
        return

    # Check if user@server or user%server is passed
    # drop it
    m = re.match(r'^\w+[@+].*$', target)
    if m:
        return

    # Only options left are channel and client comms
    m = re.match(r'^(?P<mask>[#@+!&])?\w+', target)
    if not m:
        return
    
    mask = m.group("mask")

    # If no mask, try to send to user
    if not mask:
        target_sock = NICK_MAP.get(target)
        if not target_sock:
            sock.send(ERR_NOSUCHNICK(user["nick"], target).encode())
            return
        # Send the message to the user
        target_sock.send(RPL_PRIVMSG(user["nick"], user["user"], 
                         user["host"], target, message).encode())

    else:
        # Find channel
        channel = CHANNEL_MAP.get(target)
        if not channel:
            sock.send(ERR_CANNOTSENDTOCHAN(user["nick"], target).encode())
            return

        
        users = channel.get("user_sockets", [])
        for s in users:
            # Don't echo back the message to the sender
            if s == sock:
                continue

            s.send(RPL_PRIVMSG(user["nick"], user["user"],
                      user["host"], target, message).encode())


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

        # Notify all the users in the channel that the user has left
        for s in CHANNEL_MAP[channel]["user_sockets"]:
            s.send(RPL_PART(user["nick"], user["user"], user["host"], channel, reason).encode())

        # Remove the channel from user channels
        user["channels"].remove(channel)

        # Remove user nick and socket from channels map
        CHANNEL_MAP[channel]["user_nicks"].remove(user["nick"])
        CHANNEL_MAP[channel]["user_sockets"].remove(sock)

        # If the channel has no users left - destroy it
        if len(CHANNEL_MAP[channel]["user_nicks"]) == 0:
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
        # If channel name does not start with either &, +, !, #
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
            # Set the creator as the first user
            # Even if password was sent - ignore it

            channel = {
                "user_nicks": [user["nick"]],
                "user_sockets": [sock],
            }
        else:
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
                                
        CHANNEL_MAP[ch] = channel

        # Notify other users in the same channel that the person has joined
        # This also includes the newly joined user
        for s in channel["user_sockets"]:
            s.send(RPL_JOIN(user["nick"], user["user"], user["host"], ch).encode())

        # Send back topic if exists
        channel_topic = channel.get("topic")
        if channel_topic:
            sock.send(RPL_TOPIC(user["nick"], ch, channel_topic).encode())
        else:
            sock.send(RPL_NOTOPIC(user["nick"], ch).encode())

        # Send back user list
        user_string = " ".join(channel["user_nicks"])
        sock.send(RPL_NAMREPLY(user["nick"], ch, user_string).encode())
        sock.send(RPL_ENDOFNAMES(user["nick"], ch).encode())
        
    return user

def nick_handler(user: dict, params: list, sock: socket.socket) -> dict or None:
    if len(params) == 0:
        sock.send(ERR_NONICKNAMEGIVEN.encode())
        return None

    nickname = params[0]

    # Check if the nickname is in use
    if nickname in NICK_MAP:
        sock.send(ERR_NICKNAMEINUSE(nickname).encode())
        return None

    elif user.get("nick"):
        # Since it's the user who is chaging the nickname
        # Change nicknames in all server lists if user has any
        user_channels = user.get("channels", [])
        for chan in user_channels:
            channel = CHANNEL_MAP.get(chan)

            if not channel:
                continue
            
            if user["nick"] in channel["user_nicks"]: 
                channel["user_nicks"].remove(user["nick"])
                channel["user_nicks"].append(nickname)
            
            # Notify all users in the channel of users nick change
            for s in channel["user_sockets"]:
                s.send(RPL_NICK(user["nick"], user["user"], user["host"], nickname).encode())
            
        # Update nick list
        if user["nick"] in NICK_MAP:
            NICK_MAP.pop(user["nick"])
            NICK_MAP[nickname] = sock

        # If user was in not any channels reply only to the user
        # so the client can update itself
        if len(user_channels) == 0:
            sock.send(RPL_NICK(user["nick"], user["user"], user["host"], nickname).encode())

        user["nick"] = nickname

    else:
        NICK_MAP[nickname] = sock
        user["nick"] = nickname
        user["state"] = STATE_CONNECTION_NICK_SENT

    return user

def user_handler(user: dict, params: list, sock: socket.socket) -> dict or None:
    if len(params) <  4:
        sock.send(ERR_NEEDMOREPARAMS(user["nick"], "USER").encode())
        return None

    # If user has already registered, return an error
    if user["state"] == STATE_CONNECTION_REGISTERED:
        sock.send(ERR_ALREADYREGISTERED(user["nick"]))
        return None

    # <user> <mode> <unused> <realname>
    # We only care about realname and user
    user["user"] = params[0]
    user["realname"] = params[3]
    user["state"] = STATE_CONNECTION_REGISTERED

    reply = RPL_WELCOME(user["nick"], user["user"], user["host"]) \
        + RPL_YOURHOST(user["nick"]) + RPL_CREATED(user["nick"]) \
        + RPL_MYINFO(user["nick"])
    sock.send(reply.encode())

    return user

def main():
    # Create server socket 
    main_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

    # Use SO_REUSEADDR so when crash occurs the ip is immediately released
    main_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    main_socket.bind((HOST, PORT))
    
    # Listen to 10 connections at the time
    main_socket.listen(10)

    # Appending to the global socket list
    SOCKET_LIST.append(main_socket)
    print("Listening on {}:{}...".format(HOST, PORT))
    while True:

        # Select porvides monitoring to the sockets
        # When socket becomes readable, writeable or an error occurs it is returned
        # Select returns trhee parmeters: ready to read, ready to write and an error list
        # We only care about ready to read; therefore, the other two parameters are ignnored.
        r2r, _, _ = select.select(SOCKET_LIST, [], [], 0) 

        # When a list of sockets is returned, iterate over them and process each of them individually.
        for sock in r2r:

            # If a new connection is incoming, it will be written to the server socket
            if  sock == main_socket:
                incoming_socket, incoming_addr = main_socket.accept() 

                # Appending to the global socket list in order to keep track
                SOCKET_LIST.append(incoming_socket)

                # Since this is the first connection from this socket, we create a new user entry
                # Use socket file descriptor as a unique identifier for a map key.
                USER_MAP[incoming_socket.fileno()] = {
                    "state": STATE_CONNECTION_REQUEST, # Set the state so we can check later on
                    "host": incoming_addr[0] # Set the user host since it's required for some of the replies
                }
                print("Received connection from {}".format(incoming_addr))

            else:

                # Get the key which is fd of socket
                key = sock.fileno()

                # Get the user that is making a request
                user = USER_MAP[key]

                # Read message from the socket, up to MAX_MSG_LEN 
                message = sock.recv(MAX_MSG_LEN)
                message = message.decode()

                # When a socket closes, it sends an empty message
                # In which case, we need to handle it
                if len(message) == 0:
                    quit_handler(user, [], sock)

                # Split the message by CR-LF
                messages = message.split("\r\n")

                if len(messages) == 0:
                    continue

                for message in messages:
                    # Ignore empty messages and capabilty negotiations
                    if message == "" or "CAP" in message:
                        continue
                    
                    # Match IRC regex 
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
                    
                    # Handle quit as top level
                    if command == "QUIT":
                        quit_handler(user, params, sock)
                        break

                    if user["state"] == STATE_CONNECTION_REQUEST:
                        if command != "NICK":
                            sock.send(ERR_NOTREGISTERED.encode())
                            break
                        
                        user = nick_handler(user, params, sock)
                        if not user:
                            break

                        USER_MAP[key] = user

                    elif user["state"] == STATE_CONNECTION_NICK_SENT:
                        if command != "USER":
                            sock.send(ERR_NOTREGISTERED.encode())
                            break
                        
                        user = user_handler(user, params, sock)
                        if not user:
                            break
                        
                        USER_MAP[key] = user

                    elif user["state"] == STATE_CONNECTION_REGISTERED:
                        if command == "JOIN":
                            USER_MAP[key] = join_handler(user, params, sock)
                        elif command == "PART":
                            USER_MAP[key] = part_handler(user, params, sock)
                        elif command == "PRIVMSG":
                            privmsg_handler(user, params, sock)
                        elif command == "NICK":
                            USER_MAP[key] = nick_handler(user, params, sock)
                        elif command == "USER":
                            USER_MAP[key] = nick_handler(user, params, sock)

if __name__ == '__main__':
    main()