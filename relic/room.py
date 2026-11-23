"""Process-local match storage. Only a random table ID leaves the server."""
from copy import deepcopy
from threading import Lock
from uuid import uuid4


class Room:
    def __init__(self, game):
        self.game = game
        self.lock = Lock()


class Tables:
    def __init__(self):
        self.rooms = {}
        self.lock = Lock()

    def start(self, game, previous=None):
        key = uuid4().hex
        with self.lock:
            self.rooms.pop(previous, None)
            self.rooms[key] = Room(game)
        return key

    def find(self, key):
        with self.lock:
            return self.rooms.get(key)

    def view(self, key):
        room = self.find(key)
        if room:
            with room.lock:
                return deepcopy(room.game)
        return None

    def act(self, key, revision, action, stat=None):
        room = self.find(key)
        if room:
            # A refresh or concurrent request can't race the revision check.
            with room.lock:
                return room.game.act(revision, action, stat)
        return False

    def close(self, key):
        with self.lock:
            self.rooms.pop(key, None)
