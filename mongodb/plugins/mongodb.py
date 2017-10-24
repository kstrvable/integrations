from outlyer_agent.collection import Status, Plugin, PluginTarget, DEFAULT_PLUGIN_EXEC
from typing import Dict, Any
import logging
import pymongo
import pymongo.errors
import re
import time

# TODO: add replication stats
# TODO: add parameter for command metrics (metrics.commands.*.failed|total)
# TODO: MongoClient doesn't seem to be respecting connectTimeoutMS=5000


logger = logging.getLogger(__name__)
REQUIREMENTS = ['pymongo==3.5.1']

RATE_METRICS = [
    "wired_tiger.block_manager.blocks_read",
    "wired_tiger.block_manager.blocks_written",
    "wired_tiger.block_manager.bytes_read",
    "wired_tiger.block_manager.bytes_written",
    "wired_tiger.block_manager.bytes_written_for_checkpoint",
    "wired_tiger.block_manager.mapped_blocks_read",
    "wired_tiger.block_manager.mapped_bytes_read",
    "opcounters.command",
    "opcounters.delete",
    "opcounters.getmore",
    "opcounters.insert",
    "opcounters.query",
    "opcounters.update",
    "opcounters_repl.command",
    "opcounters_repl.delete",
    "opcounters_repl.getmore",
    "opcounters_repl.insert",
    "opcounters_repl.query",
    "opcounters_repl.update",
    "wired_tiger.block_manager.blocks_read",
    "wired_tiger.block_manager.blocks_written",
    "wired_tiger.block_manager.bytes_read",
    "wired_tiger.block_manager.bytes_written",
    "wired_tiger.block_manager.mapped_blocks_read",
    "wired_tiger.block_manager.mapped_bytes_read",
]

GAUGE_METRICS = [
    "connections.available",
    "connections.current",
    "network.bytes_in",
    "network.bytes_out",
    "network.num_requests",
    "network.physical_bytes_in",
    "network.physical_bytes_out",
    "wired_tiger.async.current_work_queue_length",
    "wired_tiger.async.maximum_work_queue_length",
]

COUNTER_METRICS = [
    "connections.total_created",
    "locks._collection.acquire_count.r",
    "locks._database.acquire_count.r",
    "locks._database.acquire_count.w",
    "locks._global.acquire_count.r",
    "locks._global.acquire_count.w",
    "locks._metadata.acquire_count.w",
    "wired_tiger.async.total_allocations",
    "wired_tiger.async.total_compact_calls",
    "wired_tiger.async.total_insert_calls",
    "wired_tiger.async.total_remove_calls",
    "wired_tiger.async.total_search_calls",
    "wired_tiger.async.total_update_calls",
]


def uncamel_name(name: str):
    s1 = re.sub('(.)([A-Z][a-z]+)', r'\1_\2', name)
    s2 = re.sub('([a-z0-9])([A-Z])', r'\1_\2', s1).lower()
    s3 = s2.translate(str.maketrans(' -', '__', '()'))
    return s3


def uncamel_dict(d: Dict[str, Any]):
    better = {}
    for k, v in d.items():
        better[uncamel_name(k)] = v
    return better


def is_number(val: str):
    try:
        float(val)
        return True
    except ValueError:
        return False


def _recursive_flatten(src: Dict[str, Any], dest: Dict[str, Any], prefix: str):
    prefix = prefix + '.' if prefix != '' else ''
    for k, v in src.items():
        if isinstance(v, dict):
            _recursive_flatten(v, dest, prefix + k)
        else:
            dest[prefix + k] = v
    return dest


def flatten_dict(d: Dict[str, Any]):
    better = {}
    _recursive_flatten(d, better, '')

    return better


class MongoPlugin(Plugin):

    def __init__(self, name, deployments, host, executor=DEFAULT_PLUGIN_EXEC):
        super().__init__(name, deployments, host, executor)
        self.last_collect = None

    def collect(self, target: PluginTarget):

        host = target.get('host', 'localhost')
        port = target.get('port', 27017)

        try:
            c = pymongo.MongoClient(host=host, port=port,
                                    connectTimeoutMS=5000, socketTimeoutMS=5000)
            time_now = time.monotonic()

            for db_name in c.database_names():
                db = c.get_database(db_name)
                stats = uncamel_dict(db.command('dbstats'))
                for k, v in stats.items():
                    if is_number(v):
                        target.gauge(k, {'database': db_name}).set(float(v))

            db = c.get_database('admin')
            stats = uncamel_dict(flatten_dict(db.command('serverStatus')))

            for k in RATE_METRICS:
                try:
                    new_val = float(stats[k])
                    old_val = target.counter(k)._value
                    if self.last_collect:
                        elapsed_sec = time_now - self.last_collect
                        per_second = (new_val - old_val) / elapsed_sec
                        target.gauge(k + '_per_sec').set(per_second)
                    target.counter(k).set(new_val)
                except KeyError:
                    pass

            for k in GAUGE_METRICS:
                try:
                    target.gauge(k).set(stats[k])
                except KeyError:
                    pass

            for k in COUNTER_METRICS:
                try:
                    target.counter(k).set(stats[k])
                except KeyError:
                    pass

            c.close()
            self.last_collect = time_now
            return Status.OK

        except pymongo.errors.ConnectionFailure as ex:
            logger.error('Cannot connect to MongoDB: ' + ex.args[0])

            self.last_collect = None
            return Status.CRITICAL

        except Exception as ex:
            logger.exception('Error in plugin', exc_info=ex)

            self.last_collect = None
            return Status.UNKNOWN
