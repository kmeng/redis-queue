#   Copyright 2010 O'Reilly Media Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import redis
import threading

redis_connections = threading.local()


class RedisQueue(object):
    """Implements the same interface as collections.dequeue, except for creation.

    This is thread-safe; redis 1.34.1 is NOT."""

    def __init__(self, redis_conn, key):
        """Create a Queue backed by redis.

        Parameters:
        - key: The redis key to store the queue's backing list in.
        - remaining arguments: how to construct our redis connection."""
        self.redis_conn = redis_conn
        self.key = key

    # @property
    # def _redis(self):
    #     if hasattr(redis_connections, str(self.redis_parameters)):
    #         return getattr(redis_connections, str(self.redis_parameters))
    #     else:
    #         r = redis.Redis(**self.redis_parameters)
    #         setattr(redis_connections, str(self.redis_parameters), r)
    #         return r

    def append(self, x):
        self.redis_conn.rpush(self.key, x)

    def appendleft(self, x):
        self.redis_conn.lpush(self.key, x)

    def clear(self):
        self.redis_conn.delete(self.key)

    def extend(self, iterable):
        """Non-atomic. append each of the items from iterable in turn."""
        for item in iterable:
            self.append(item)

    def extendleft(self, iterable):
        """Non-atomic. appendleft each of the items from iterable in turn."""
        for item in iterable:
            self.appendleft(item)

    def pop(self, timeout=None):
        if timeout is not None:
            item = self.redis_conn.brpop(self.key, timeout)
        else:
            item = self.redis_conn.rpop(self.key)
        return item

    def popleft(self, timeout=None):
        if timeout is not None:
            item = self.redis_conn.blpop(self.key, timeout)
        else:
            item = self.redis_conn.lpop(self.key)
        return item

    def remove(self, value):
        num_removed = self.redis_conn.lrem(self.key, value)
        if num_removed == 0:
            raise ValueError()

    def rotate(self):
        """rotates the queue one step only."""
        self.redis_conn.poppush(self.key, self.key)

    # Membership
    def __contains__(self, item):
        # This could stand to be a lot more efficient.
        # Why doesn't redis support this on the server side?
        members = self.redis_conn.lrange(self.key, 0, -1)
        return None if members is None else item in members

    # Length
    def __len__(self):
        return self.redis_conn.llen(self.key)

    # Subscript
    def __getitem__(self, key):
        item = self.redis_conn.lindex(self.key, key)
        return item

    def __setitem__(self, key, value):
        try:
            self.redis_conn.lset(self.key, key, value)
        except redis.ResponseError as e:
            raise IndexError(e)

    # Iteration
    def __iter__(self):
        members = self.redis_conn.lrange(self.key, 0, -1)
        return iter(members)


class ExclusiveQueue(RedisQueue):
    """A queue that implements exclusivity (a given thing can only be in the
    queue once. This is not at all atomic; it pops something off then removes
    all other instances from the queue."""

    def append(self, x):
        if x not in self:
            self.redis_conn.rpush(self.key, x)

    def appendleft(self, x):
        if x not in self:
            self.redis_conn.lpush(self.key, x)

    def pop(self, timeout=None):
        """pop and return the rightmost item in the queue, then delete all other
        instances of this item from the queue.

        While both of the operations used are atomic, this method itself is not."""
        item = super(ExclusiveQueue, self).pop(timeout)
        try:
            self.remove(item)
        except ValueError:
            pass
        return item

    def popleft(self, timeout=None):
        """pop and return the leftmost item in the queue, then delete all other
        instances of this item from the queue.

        While both of the operations used are atomic, this method itself is not."""
        item = super(ExclusiveQueue, self).popleft(timeout)
        try:
            self.remove(item)
        except ValueError:
            pass
        return item
