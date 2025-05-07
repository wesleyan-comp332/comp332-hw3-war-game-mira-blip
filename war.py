"""
war card game client and server
Iris and Tamiraa
"""
import asyncio
from collections import namedtuple
from enum import Enum
import logging
import random
import socket
import socketserver
import threading
import sys


"""
Namedtuples work like classes, but are much more lightweight so they end
up being faster. It would be a good idea to keep objects in each of these
for each game which contain the game's state, for instance things like the
socket, the cards given, the cards still available, etc.
"""
Game = namedtuple("Game", ["p1", "p2"])

# Stores the clients waiting to get connected to other clients
waiting_clients = asyncio.Queue()
gamenum = 0
class Command(Enum):
    """
    The byte values sent as the first byte of any message in the war protocol.
    """
    WANTGAME = 0
    GAMESTART = 1
    PLAYCARD = 2
    PLAYRESULT = 3


class Result(Enum):
    """
    The byte values sent as the payload byte of a PLAYRESULT message.
    """
    WIN = 0
    DRAW = 1
    LOSE = 2

async def readexactly(sock, numbytes):
    """
    Accumulate exactly `numbytes` from `sock` and return those. If EOF is found
    before numbytes have been received, be sure to account for that here or in
    the caller.
    """
    # TODO
    data = bytearray()
    while len(data) < numbytes:
        remaining_bytes = numbytes - len(data)
        chunk = await sock.read(remaining_bytes)
        
        if not chunk:
            raise EOFError(f"Expected {numbytes} bytes, but only received {len(data)} bytes.")
        
        data.extend(chunk)
    
    return bytes(data)


def kill_game(game):
    """
    TODO: If either client sends a bad message, immediately nuke the game.
    """
    game[0][1].close()
    game[1][1].close()
    return


def compare_cards(card1, card2):
    """
    TODO: Given an integer card representation, return -1 for card1 < card2,
    0 for card1 = card2, and 1 for card1 > card2
    """
    if (card1 % 13) < (card2 % 13):
        return -1
    else:
        return 1
    

def deal_cards():
    """
    TODO: Randomize a deck of cards (list of ints 0..51), and return two
    26 card "hands."
    """
    cards = []
    for c in range(52):
        cards.append(c)
    random.shuffle(cards)
    hand1 = cards[:26]
    hand2 = cards[26:]
    return hand1, hand2

async def new_game(p1, p2, gamenum):
    try:
        p1_msg = await p1[0].readexactly(2)
        p2_msg = await p2[0].readexactly(2)
        if p1_msg != b"\0\0" or p2_msg != b"\0\0":
            kill_game((p1, p2))
        else:
            hand1, hand2 = deal_cards()
            p1[1].write(bytes([1] + hand1))
            p2[1].write(bytes([1] + hand2))
            for round in range (26):
                p1_card = await p1[0].readexactly(2)
                p2_card = await p2[0].readexactly(2)
                result = compare_cards(p1_card[1], p2_card[1])
                # logging.debug("Round {}: P1 - {} || P2 - {} || Winner: Player{}".format(round + 1, p1_card[1], p2_card[1], (1 if result == -1 else 2)))
                if result == -1:
                    
                    p1[1].write(bytes([3 , 2]))
                    p2[1].write(bytes([3 , 0]))
                elif result == 1:
                    p1[1].write(bytes([3 , 0]))
                    p2[1].write(bytes([3 , 2]))
                else:
                    p1[1].write(bytes([3, 1]))
                    p2[1].write(bytes([3, 1]))
            if result == 0:
                logging.debug("Game %s over. Draw.", gamenum)
            else:
                winner = "Player 1" if result > 0 else "Player 2"
                logging.debug("Game %s over. %s won.", gamenum, winner)

    except asyncio.IncompleteReadError as e:
        logging.error(f"IncompleteReadError: {e} - Handling disconnection.")
        kill_game((p1, p2))
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        kill_game((p1, p2))  



async def pair_clients(reader, writer):
    global gamenum
    if waiting_clients.empty():
        await waiting_clients.put((reader, writer))
        logging.debug("Client connected, waiting....")
    else:
        p1 = await waiting_clients.get()
        p2 = (reader, writer)
        gamenum += 1
        logging.debug("Client connected to waiting client. Starting game %s....", gamenum)
        asyncio.create_task(new_game(p1, p2, gamenum))

def serve_game(host, port):
    """
    TODO: Open a socket for listening for new connections on host:port, and
    perform the war protocol to serve a game of war between each client.
    This function should run forever, continually serving clients.
    """
    loop = asyncio.get_event_loop()
    coro = asyncio.start_server(pair_clients, host, port)
    server = loop.run_until_complete(coro)
    logging.debug('Serving on {}'.format(server.sockets[0].getsockname()))
    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
        


async def limit_client(host, port, loop, sem):
    """
    Limit the number of clients currently executing.
    You do not need to change this function.
    """
    async with sem:
        return await client(host, port, loop)

async def client(host, port, loop):
    """
    Run an individual client on a given event loop.
    You do not need to change this function.
    """
    try:
        reader, writer = await asyncio.open_connection(host, port)
        # send want game
        writer.write(b"\0\0")
        card_msg = await reader.readexactly(27)
        myscore = 0
        for card in card_msg[1:]:
            writer.write(bytes([Command.PLAYCARD.value, card]))
            result = await reader.readexactly(2)
            if result[1] == Result.WIN.value:
                myscore += 1
            elif result[1] == Result.LOSE.value:
                myscore -= 1
        if myscore > 0:
            result = "won"
        elif myscore < 0:
            result = "lost"
        else:
            result = "drew"
        logging.debug("Game complete, I %s", result)
        writer.close()
        return 1
    except ConnectionResetError:
        logging.error("ConnectionResetError")
        return 0
    except asyncio.streams.IncompleteReadError:
        logging.error("asyncio.streams.IncompleteReadError")
        return 0
    except OSError:
        logging.error("OSError")
        return 0

def main(args):
    """
    launch a client/server
    """
    host = args[1]
    port = int(args[2])
    if args[0] == "server":
        try:
            # your server should serve clients until the user presses ctrl+c
            serve_game(host, port)
        except KeyboardInterrupt:
            pass
        return
    else:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
        
        asyncio.set_event_loop(loop)
        
    if args[0] == "client":
        loop.run_until_complete(client(host, port, loop))
    elif args[0] == "clients":
        sem = asyncio.Semaphore(1000)
        num_clients = int(args[3])
        clients = [limit_client(host, port, loop, sem)
                   for x in range(num_clients)]
        async def run_all_clients():
            """
            use `as_completed` to spawn all clients simultaneously
            and collect their results in arbitrary order.
            """
            completed_clients = 0
            for client_result in asyncio.as_completed(clients):
                completed_clients += await client_result
            return completed_clients
        res = loop.run_until_complete(
            asyncio.Task(run_all_clients(), loop=loop))
        logging.info("%d completed clients", res)

    loop.close()

if __name__ == "__main__":
    # Changing logging to DEBUG
    logging.basicConfig(level=logging.DEBUG)
    main(sys.argv[1:])
